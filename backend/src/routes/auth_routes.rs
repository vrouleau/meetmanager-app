use axum::{
    extract::{ConnectInfo, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde_json::{json, Value};
use std::net::SocketAddr;

use crate::auth::{get_admin_pin, resolve_role, Role};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new().route("/api/auth", post(auth))
}

async fn auth(
    State(state): State<AppState>,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let ip = addr.ip().to_string();
    state
        .rate_limiter
        .check(&ip)
        .map_err(|_| (StatusCode::TOO_MANY_REQUESTS, "Too many attempts. Try again later.".to_string()))?;

    let pin = data["pin"].as_str().unwrap_or("");
    let admin_pin = get_admin_pin(&state.pool).await;

    if pin == admin_pin {
        return Ok(Json(json!({"role": "admin", "club_id": null, "club_name": "Admin"})));
    }

    let row: Option<(i32, String)> =
        sqlx::query_as("SELECT id, name FROM clubs WHERE pin = $1")
            .bind(pin)
            .fetch_optional(&state.pool)
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let (club_id, club_name) = match row {
        Some(r) => r,
        None => return Err((StatusCode::UNAUTHORIZED, "Invalid PIN".to_string())),
    };

    let org: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
            .fetch_optional(&state.pool)
            .await
            .unwrap_or(None);

    let role = if let Some((Some(val),)) = org {
        if val == club_id.to_string() { "organizer" } else { "coach" }
    } else {
        "coach"
    };

    Ok(Json(json!({"role": role, "club_id": club_id, "club_name": club_name})))
}
