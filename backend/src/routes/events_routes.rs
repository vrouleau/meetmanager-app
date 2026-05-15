use axum::{
    extract::State,
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde_json::{json, Value};

use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/events", get(list_events))
        .route("/api/meet-info", get(meet_info))
        .route("/api/status", get(status))
}

async fn list_events(
    State(state): State<AppState>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let events: Vec<(i32, i32, Option<String>, Option<i32>, i32, Option<i32>, Option<i32>, Option<i32>, bool)> = sqlx::query_as(
        "SELECT id, style_uid, style_name, distance, relay_count, gender, event_number, round, masters FROM events ORDER BY event_number"
    ).fetch_all(&state.pool).await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let result: Vec<Value> = events.iter().map(|e| json!({
        "id": e.0, "style_uid": e.1, "style_name": e.2,
        "distance": e.3, "relay_count": e.4, "gender": e.5,
        "event_number": e.6, "round": e.7, "masters": e.8,
    })).collect();

    Ok(Json(json!(result)))
}

async fn meet_info(
    State(state): State<AppState>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let keys = ["meet_filename", "meet_uploaded_at", "meet_name", "meet_course",
                "meet_masters", "closure_date", "meet_currency", "meet_fees_json"];
    let mut config: std::collections::HashMap<String, String> = std::collections::HashMap::new();

    for key in keys {
        let row: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = $1")
            .bind(key).fetch_optional(&state.pool).await.unwrap_or(None);
        if let Some((Some(val),)) = row {
            config.insert(key.to_string(), val);
        }
    }

    let meet_fees: serde_json::Value = config.get("meet_fees_json")
        .and_then(|v| serde_json::from_str(v).ok())
        .unwrap_or(json!({}));

    let event_count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM events")
        .fetch_one(&state.pool).await.unwrap_or((0,));

    // Event fees
    let event_fees: Vec<(Option<i32>, Option<String>, Option<i32>, i32, i32)> = sqlx::query_as(
        "SELECT event_number, style_name, distance, relay_count, fee_cents FROM events ORDER BY event_number"
    ).fetch_all(&state.pool).await.unwrap_or_default();

    let ef: Vec<Value> = event_fees.iter().map(|e| json!({
        "event_number": e.0, "style_name": e.1, "distance": e.2,
        "relay_count": e.3, "fee_cents": e.4,
    })).collect();

    Ok(Json(json!({
        "filename": config.get("meet_filename"),
        "uploaded_at": config.get("meet_uploaded_at"),
        "meet_name": config.get("meet_name"),
        "course": config.get("meet_course"),
        "masters": config.get("meet_masters").map(|v| v == "T").unwrap_or(false),
        "events": event_count.0,
        "closure_date": config.get("closure_date"),
        "currency": config.get("meet_currency").cloned().unwrap_or_else(|| "CAD".to_string()),
        "meet_fees": meet_fees,
        "event_fees": ef,
    })))
}

async fn status(
    State(state): State<AppState>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let clubs: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM clubs").fetch_one(&state.pool).await.unwrap_or((0,));
    let athletes: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM athletes").fetch_one(&state.pool).await.unwrap_or((0,));
    let events: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM events").fetch_one(&state.pool).await.unwrap_or((0,));
    let regs: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM registrations").fetch_one(&state.pool).await.unwrap_or((0,));
    let bts: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM best_times").fetch_one(&state.pool).await.unwrap_or((0,));

    Ok(Json(json!({
        "clubs": clubs.0, "athletes": athletes.0, "events": events.0,
        "registrations": regs.0, "best_times": bts.0,
    })))
}
