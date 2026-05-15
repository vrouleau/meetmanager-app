use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    routing::{get, post, put},
    Json, Router,
};
use chrono::NaiveDate;
use serde_json::{json, Value};

use crate::auth::{require_admin, require_organizer_or_admin};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/admin/organizer", get(get_organizer))
        .route("/api/admin/set-organizer", post(set_organizer))
        .route("/api/admin/change-pin", post(change_pin))
        .route("/api/closure-date", put(set_closure_date))
        .route("/api/data-management/styles", get(get_styles))
        .route("/api/data-management/merge-clubs", post(merge_clubs))
        .route("/api/data-management/merge-styles", post(merge_styles))
}

async fn get_organizer(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let row: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);

    if let Some((Some(val),)) = row {
        if let Ok(id) = val.parse::<i32>() {
            let club: Option<(String,)> = sqlx::query_as("SELECT name FROM clubs WHERE id = $1")
                .bind(id).fetch_optional(&state.pool).await.unwrap_or(None);
            if let Some((name,)) = club {
                return Ok(Json(json!({"club_id": id, "club_name": name})));
            }
        }
    }
    Ok(Json(json!({"club_id": null, "club_name": null})))
}

async fn set_organizer(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Value>>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;
    let data = body.map(|Json(v)| v).unwrap_or(Value::Null);

    let club_id = data["club_id"].as_i64().ok_or((StatusCode::BAD_REQUEST, "club_id required".to_string()))? as i32;
    let exists: Option<(i32,)> = sqlx::query_as("SELECT id FROM clubs WHERE id = $1")
        .bind(club_id).fetch_optional(&state.pool).await.unwrap_or(None);
    if exists.is_none() {
        return Err((StatusCode::NOT_FOUND, "Club not found".to_string()));
    }

    sqlx::query("INSERT INTO app_config (key, value) VALUES ('organizer_club_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1")
        .bind(club_id.to_string()).execute(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"ok": true, "organizer_club_id": club_id})))
}

async fn change_pin(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Value>>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;
    let data = body.map(|Json(v)| v).unwrap_or(Value::Null);

    let new_pin = data["pin"].as_str().ok_or((StatusCode::UNPROCESSABLE_ENTITY, "pin required".to_string()))?;
    if new_pin.len() < 4 || new_pin.len() > 20 {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, "PIN must be 4-20 characters".to_string()));
    }

    sqlx::query("INSERT INTO app_config (key, value) VALUES ('admin_pin', $1) ON CONFLICT (key) DO UPDATE SET value = $1")
        .bind(new_pin).execute(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"ok": true})))
}

async fn set_closure_date(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Value>>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;
    let data = body.map(|Json(v)| v).unwrap_or(Value::Null);

    let val = data["closure_date"].as_str().unwrap_or("");
    if !val.is_empty() {
        if chrono::NaiveDate::parse_from_str(val, "%Y-%m-%d").is_err() {
            return Err((StatusCode::UNPROCESSABLE_ENTITY, "Invalid date format".to_string()));
        }
    }
    sqlx::query("INSERT INTO app_config (key, value) VALUES ('closure_date', $1) ON CONFLICT (key) DO UPDATE SET value = $1")
        .bind(val).execute(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"closure_date": val})))
}

async fn get_styles(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let uids: Vec<(i32,)> = sqlx::query_as("SELECT DISTINCT style_uid FROM best_times")
        .fetch_all(&state.pool).await.unwrap_or_default();

    let mut result = Vec::new();
    for (uid,) in &uids {
        let name: Option<(Option<String>,)> = sqlx::query_as("SELECT style_name FROM events WHERE style_uid = $1 LIMIT 1")
            .bind(uid).fetch_optional(&state.pool).await.unwrap_or(None);
        let n = name.and_then(|r| r.0).unwrap_or_else(|| format!("ID{uid}"));
        result.push(json!({"uid": uid, "name": n}));
    }
    result.sort_by_key(|v| v["uid"].as_i64().unwrap_or(0));

    Ok(Json(json!(result)))
}

async fn merge_clubs(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Value>>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;
    let data = body.map(|Json(v)| v).unwrap_or(Value::Null);

    let merges = data["merges"].as_array().ok_or((StatusCode::BAD_REQUEST, "merges required".to_string()))?;
    let mut merged = 0;

    for m in merges {
        let from_id = m["from_id"].as_i64().unwrap_or(0) as i32;
        let to_id = m["to_id"].as_i64().unwrap_or(0) as i32;
        if from_id == to_id || from_id == 0 || to_id == 0 { continue; }

        // Move athletes that don't conflict
        sqlx::query(
            "UPDATE athletes SET club_id = $1 WHERE club_id = $2 AND NOT EXISTS (SELECT 1 FROM athletes a2 WHERE a2.club_id = $1 AND a2.first_name = athletes.first_name AND a2.last_name = athletes.last_name)"
        ).bind(to_id).bind(from_id).execute(&state.pool).await.ok();

        // Delete remaining (conflicting) athletes' registrations and best times, then the athletes
        sqlx::query("DELETE FROM registrations WHERE athlete_id IN (SELECT id FROM athletes WHERE club_id = $1)")
            .bind(from_id).execute(&state.pool).await.ok();
        sqlx::query("DELETE FROM best_times WHERE athlete_id IN (SELECT id FROM athletes WHERE club_id = $1)")
            .bind(from_id).execute(&state.pool).await.ok();
        sqlx::query("DELETE FROM athletes WHERE club_id = $1")
            .bind(from_id).execute(&state.pool).await.ok();
        sqlx::query("DELETE FROM clubs WHERE id = $1")
            .bind(from_id).execute(&state.pool).await.ok();
        merged += 1;
    }

    Ok(Json(json!({"merged": merged})))
}

async fn merge_styles(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Value>>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;
    let data = body.map(|Json(v)| v).unwrap_or(Value::Null);

    let merges = data["merges"].as_array().ok_or((StatusCode::BAD_REQUEST, "merges required".to_string()))?;
    let mut merged_rows = 0i64;

    for m in merges {
        let from_uid = m["from_uid"].as_i64().unwrap_or(0) as i32;
        let to_uid = m["to_uid"].as_i64().unwrap_or(0) as i32;
        if from_uid == to_uid || from_uid == 0 { continue; }

        // Move non-conflicting
        let result = sqlx::query(
            "UPDATE best_times SET style_uid = $1 WHERE style_uid = $2 AND NOT EXISTS (SELECT 1 FROM best_times b2 WHERE b2.athlete_id = best_times.athlete_id AND b2.style_uid = $1 AND b2.course = best_times.course)"
        ).bind(to_uid).bind(from_uid).execute(&state.pool).await;
        if let Ok(r) = result { merged_rows += r.rows_affected() as i64; }

        // Delete remaining conflicts
        let result = sqlx::query("DELETE FROM best_times WHERE style_uid = $1")
            .bind(from_uid).execute(&state.pool).await;
        if let Ok(r) = result { merged_rows += r.rows_affected() as i64; }
    }

    Ok(Json(json!({"merged_rows": merged_rows})))
}
