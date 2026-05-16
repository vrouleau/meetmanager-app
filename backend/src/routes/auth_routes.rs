use axum::{
    extract::{ConnectInfo, Path, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde_json::{json, Value};
use std::net::SocketAddr;

use crate::auth::{get_admin_pin, resolve_role, Role};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/auth", post(auth))
        .route("/api/secret/:token", post(reveal_secret))
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

async fn reveal_secret(
    State(state): State<AppState>,
    Path(token): Path<String>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let row: Option<(i32, String, i32, bool, chrono::NaiveDateTime)> = sqlx::query_as(
        "SELECT id, pin_encrypted, club_id, viewed, expires_at FROM secret_links WHERE token = $1"
    )
    .bind(&token)
    .fetch_optional(&state.pool)
    .await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let (link_id, pin_encrypted, club_id, viewed, expires_at) = row
        .ok_or((StatusCode::NOT_FOUND, "Link invalid or expired".to_string()))?;

    if viewed {
        return Err((StatusCode::GONE, "Link already used".to_string()));
    }
    if chrono::Utc::now().naive_utc() > expires_at {
        return Err((StatusCode::GONE, "Link expired".to_string()));
    }

    // Decrypt PIN
    use sha2::{Sha256, Digest};
    use base64::Engine;
    use aes_gcm::{Aes256Gcm, KeyInit, aead::Aead};
    use aes_gcm::Nonce;

    let secret_key = std::env::var("SECRET_KEY").unwrap_or_default();
    let hash = Sha256::digest(secret_key.as_bytes());
    let cipher = Aes256Gcm::new_from_slice(&hash)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Decryption error".to_string()))?;
    let combined = base64::engine::general_purpose::URL_SAFE.decode(&pin_encrypted)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Decryption error".to_string()))?;
    if combined.len() < 12 {
        return Err((StatusCode::INTERNAL_SERVER_ERROR, "Decryption error".to_string()));
    }
    let (nonce_bytes, ciphertext) = combined.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);
    let pin_bytes = cipher.decrypt(nonce, ciphertext)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Decryption error".to_string()))?;
    let pin = String::from_utf8(pin_bytes)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Decryption error".to_string()))?;

    // Mark as viewed
    sqlx::query("UPDATE secret_links SET viewed = TRUE WHERE id = $1")
        .bind(link_id)
        .execute(&state.pool)
        .await
        .ok();

    // Get club name
    let club_name: Option<String> = sqlx::query_scalar("SELECT name FROM clubs WHERE id = $1")
        .bind(club_id)
        .fetch_optional(&state.pool)
        .await
        .unwrap_or(None);

    Ok(Json(json!({"pin": pin, "club": club_name.unwrap_or_default()})))
}
