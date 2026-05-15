use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    routing::{delete, get, post, put},
    Json, Router,
};
use rand::Rng;
use serde_json::{json, Value};

use crate::auth::{require_admin, resolve_role};
use crate::invoices::{club_line_items, meet_fees};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/clubs", get(list_clubs).post(create_club))
        .route("/api/clubs/:club_id", delete(delete_club).put(update_club))
        .route("/api/clubs/:club_id/reset-pin", post(reset_pin))
        .route("/api/clubs/regenerate-pins", post(regenerate_pins))
}

async fn list_clubs(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    let role = resolve_role(pin, &state.pool).await;

    let clubs: Vec<(i32, String, Option<String>, Option<String>, Option<String>, i32, i32)> =
        sqlx::query_as("SELECT id, name, code, pin, admin_email, invite_send_count, stripe_send_count FROM clubs ORDER BY name")
            .fetch_all(&state.pool)
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let fees = meet_fees(&state.pool).await;
    let mut result = Vec::new();

    for c in &clubs {
        let ath_count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM athletes WHERE club_id = $1")
            .bind(c.0)
            .fetch_one(&state.pool)
            .await
            .unwrap_or((0,));

        let reg_count: (i64,) = sqlx::query_as(
            "SELECT COUNT(DISTINCT a.id) FROM athletes a JOIN registrations r ON r.athlete_id = a.id WHERE a.club_id = $1",
        )
        .bind(c.0)
        .fetch_one(&state.pool)
        .await
        .unwrap_or((0,));

        let items = club_line_items(&state.pool, c.0, &fees).await;
        let total: i32 = items.iter().map(|it| it.unit_cents * it.qty).sum();

        let mut item = json!({
            "id": c.0,
            "name": c.1,
            "code": c.2,
            "athlete_count": ath_count.0,
            "registered_athlete_count": reg_count.0,
            "invite_send_count": c.5,
            "stripe_send_count": c.6,
            "total_fees_cents": total,
        });

        if role.is_admin_or_organizer() {
            item["admin_email"] = json!(c.4.as_deref().unwrap_or(""));
        }
        if role.is_admin() {
            item["pin"] = json!(c.3);
        }
        result.push(item);
    }

    Ok(Json(json!(result)))
}

async fn create_club(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let name = data["name"].as_str().unwrap_or("").trim();
    if name.is_empty() {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, "name required".to_string()));
    }
    let code = data["code"].as_str().unwrap_or("");
    let nation = data["nation"].as_str().unwrap_or("CAN");
    let new_pin = data["pin"].as_str().map(|s| s.to_string()).unwrap_or_else(|| generate_pin());

    let row: (i32,) = sqlx::query_as(
        "INSERT INTO clubs (name, code, nation, pin) VALUES ($1, $2, $3, $4) RETURNING id",
    )
    .bind(name)
    .bind(code)
    .bind(nation)
    .bind(&new_pin)
    .fetch_one(&state.pool)
    .await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"id": row.0, "pin": new_pin})))
}

async fn delete_club(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let exists: Option<(i32,)> = sqlx::query_as("SELECT id FROM clubs WHERE id = $1")
        .bind(club_id)
        .fetch_optional(&state.pool)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    if exists.is_none() {
        return Err((StatusCode::NOT_FOUND, "Not found".to_string()));
    }

    sqlx::query("DELETE FROM registrations WHERE athlete_id IN (SELECT id FROM athletes WHERE club_id = $1)")
        .bind(club_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM best_times WHERE athlete_id IN (SELECT id FROM athletes WHERE club_id = $1)")
        .bind(club_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM athletes WHERE club_id = $1")
        .bind(club_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM secret_links WHERE club_id = $1")
        .bind(club_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM clubs WHERE id = $1")
        .bind(club_id).execute(&state.pool).await.ok();

    Ok(Json(json!({"deleted": true})))
}

async fn update_club(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    if let Some(email) = data["admin_email"].as_str() {
        sqlx::query("UPDATE clubs SET admin_email = $1 WHERE id = $2")
            .bind(email)
            .bind(club_id)
            .execute(&state.pool)
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    Ok(Json(json!({"ok": true})))
}

async fn reset_pin(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let new_pin = generate_pin();
    sqlx::query("UPDATE clubs SET pin = $1 WHERE id = $2")
        .bind(&new_pin)
        .bind(club_id)
        .execute(&state.pool)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"pin": new_pin})))
}

async fn regenerate_pins(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let clubs: Vec<(i32,)> = sqlx::query_as("SELECT id FROM clubs")
        .fetch_all(&state.pool)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    for (id,) in &clubs {
        let new_pin = generate_pin();
        sqlx::query("UPDATE clubs SET pin = $1 WHERE id = $2")
            .bind(&new_pin)
            .bind(id)
            .execute(&state.pool)
            .await
            .ok();
    }

    Ok(Json(json!({"regenerated": clubs.len()})))
}

fn generate_pin() -> String {
    let mut rng = rand::thread_rng();
    (0..6).map(|_| rng.gen_range(0..10).to_string()).collect()
}
