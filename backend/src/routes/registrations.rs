use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    routing::{delete, post},
    Json, Router,
};
use serde_json::{json, Value};

use crate::auth::{check_closure, require_admin, resolve_role};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/registrations", post(create_registration).delete(flush_meet))
        .route("/api/registrations/{reg_id}", delete(delete_registration))
}

async fn create_registration(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    check_closure(&state.pool, pin).await?;

    let role = resolve_role(pin, &state.pool).await;
    let athlete_id = data["athlete_id"].as_i64().ok_or((StatusCode::BAD_REQUEST, "athlete_id required".to_string()))? as i32;
    let event_id = data["event_id"].as_i64().ok_or((StatusCode::BAD_REQUEST, "event_id required".to_string()))? as i32;
    let age_code = data["age_code"].as_str().unwrap_or("Open");
    let entry_time_ms = data["entry_time_ms"].as_i64().map(|v| v as i32);

    // Ownership check
    let ath: Option<(i32,)> = sqlx::query_as("SELECT club_id FROM athletes WHERE id = $1")
        .bind(athlete_id).fetch_optional(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let ath_club = ath.ok_or((StatusCode::NOT_FOUND, "Athlete not found".to_string()))?.0;

    if let Some(caller_club) = role.club_id() {
        if ath_club != caller_club {
            return Err((StatusCode::FORBIDDEN, "Cannot register athletes from another club".to_string()));
        }
    }

    // Check event exists
    let ev: Option<(i32, bool)> = sqlx::query_as("SELECT relay_count, masters FROM events WHERE id = $1")
        .bind(event_id).fetch_optional(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let (relay_count, _masters) = ev.ok_or((StatusCode::NOT_FOUND, "Event not found".to_string()))?;

    // Relay lock
    if relay_count > 1 {
        let existing: Option<(i32,)> = sqlx::query_as(
            "SELECT r.id FROM registrations r JOIN athletes a ON r.athlete_id = a.id WHERE r.event_id = $1 AND a.club_id = $2 AND r.athlete_id != $3"
        ).bind(event_id).bind(ath_club).bind(athlete_id)
        .fetch_optional(&state.pool).await.unwrap_or(None);
        if existing.is_some() {
            return Err((StatusCode::CONFLICT, "Relay already has a registration from this club".to_string()));
        }
    }

    // Upsert
    let existing: Option<(i32,)> = sqlx::query_as(
        "SELECT id FROM registrations WHERE athlete_id = $1 AND event_id = $2 AND age_code = $3"
    ).bind(athlete_id).bind(event_id).bind(age_code)
    .fetch_optional(&state.pool).await.unwrap_or(None);

    if let Some((id,)) = existing {
        sqlx::query("UPDATE registrations SET entry_time_ms = $1 WHERE id = $2")
            .bind(entry_time_ms).bind(id).execute(&state.pool).await.ok();
        update_exception(&state.pool, athlete_id).await;
        return Ok(Json(json!({"id": id, "updated": true})));
    }

    let row: (i32,) = sqlx::query_as(
        "INSERT INTO registrations (athlete_id, event_id, age_code, entry_time_ms) VALUES ($1, $2, $3, $4) RETURNING id"
    ).bind(athlete_id).bind(event_id).bind(age_code).bind(entry_time_ms)
    .fetch_one(&state.pool).await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    update_exception(&state.pool, athlete_id).await;
    Ok(Json(json!({"id": row.0, "updated": false})))
}

async fn delete_registration(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(reg_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    check_closure(&state.pool, pin).await?;

    let role = resolve_role(pin, &state.pool).await;
    let reg: Option<(i32,)> = sqlx::query_as("SELECT athlete_id FROM registrations WHERE id = $1")
        .bind(reg_id).fetch_optional(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let athlete_id = reg.ok_or((StatusCode::NOT_FOUND, "Not found".to_string()))?.0;

    if let Some(caller_club) = role.club_id() {
        let ath_club: Option<(i32,)> = sqlx::query_as("SELECT club_id FROM athletes WHERE id = $1")
            .bind(athlete_id).fetch_optional(&state.pool).await.unwrap_or(None);
        if ath_club.map(|c| c.0) != Some(caller_club) {
            return Err((StatusCode::FORBIDDEN, "Cannot modify registrations from another club".to_string()));
        }
    }

    sqlx::query("DELETE FROM registrations WHERE id = $1").bind(reg_id).execute(&state.pool).await.ok();
    update_exception(&state.pool, athlete_id).await;
    Ok(Json(json!({"deleted": true})))
}

async fn flush_meet(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let deleted: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM registrations")
        .fetch_one(&state.pool).await.unwrap_or((0,));
    sqlx::query("DELETE FROM registrations").execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM age_groups").execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM events").execute(&state.pool).await.ok();

    for key in ["meet_filename", "meet_uploaded_at", "meet_name", "meet_course",
                "meet_masters", "meet_currency", "meet_fees_json", "closure_date", "organizer_club_id"] {
        sqlx::query("DELETE FROM app_config WHERE key = $1").bind(key).execute(&state.pool).await.ok();
    }
    sqlx::query("UPDATE clubs SET invite_send_count = 0, stripe_send_count = 0")
        .execute(&state.pool).await.ok();

    Ok(Json(json!({"deleted": deleted.0})))
}

async fn update_exception(pool: &sqlx::PgPool, athlete_id: i32) {
    let has_masters: Option<(i32,)> = sqlx::query_as(
        "SELECT id FROM registrations WHERE athlete_id = $1 AND age_code = 'Masters' LIMIT 1"
    ).bind(athlete_id).fetch_optional(pool).await.unwrap_or(None);

    let exc = if has_masters.is_some() { Some("X") } else { None::<&str> };
    sqlx::query("UPDATE athletes SET exception = $1 WHERE id = $2")
        .bind(exc).bind(athlete_id).execute(pool).await.ok();
}
