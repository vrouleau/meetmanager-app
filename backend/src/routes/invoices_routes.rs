use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use serde_json::{json, Value};

use crate::auth::require_organizer_or_admin;
use crate::invoices::{club_line_items, create_stripe_invoice, meet_fees};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/clubs/{club_id}/invoice-total", get(invoice_total))
        .route("/api/clubs/{club_id}/invoice", post(send_invoice))
        .route("/api/clubs/{club_id}/create-invoice", post(create_invoice))
        .route("/api/stripe/connect", post(stripe_connect))
        .route("/api/stripe/status", get(stripe_status))
        .route("/api/stripe/disconnect", post(stripe_disconnect))
}

async fn invoice_total(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let fees = meet_fees(&state.pool).await;
    let items = club_line_items(&state.pool, club_id, &fees).await;
    let total: i32 = items.iter().map(|it| it.unit_cents * it.qty).sum();

    Ok(Json(json!({"club_id": club_id, "total_cents": total})))
}

async fn send_invoice(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    // Get organizer's stripe account
    let org: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let stripe_acct = if let Some((Some(org_id),)) = org {
        if let Ok(id) = org_id.parse::<i32>() {
            let row: Option<(Option<String>,)> = sqlx::query_as("SELECT stripe_account_id FROM clubs WHERE id = $1")
                .bind(id).fetch_optional(&state.pool).await.unwrap_or(None);
            row.and_then(|r| r.0)
        } else { None }
    } else { None };

    let result = create_stripe_invoice(&state.pool, club_id, stripe_acct.as_deref()).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;

    sqlx::query("UPDATE clubs SET stripe_send_count = stripe_send_count + 1 WHERE id = $1")
        .bind(club_id).execute(&state.pool).await.ok();

    Ok(Json(result))
}

async fn create_invoice(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let result = create_stripe_invoice(&state.pool, club_id, None).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;
    Ok(Json(result))
}

async fn stripe_connect(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let api_key = std::env::var("STRIPE_API_KEY")
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "STRIPE_API_KEY not configured".to_string()))?;

    let org: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let org_id: i32 = org.and_then(|r| r.0).and_then(|v| v.parse().ok())
        .ok_or((StatusCode::BAD_REQUEST, "No organizer club set".to_string()))?;

    let acct: Option<(Option<String>,)> = sqlx::query_as("SELECT stripe_account_id FROM clubs WHERE id = $1")
        .bind(org_id).fetch_optional(&state.pool).await.unwrap_or(None);
    let account_id = if let Some((Some(id),)) = acct {
        id
    } else {
        // Create account via Stripe API
        let client = reqwest::Client::new();
        let resp = client.post("https://api.stripe.com/v1/accounts")
            .header("Authorization", format!("Bearer {api_key}"))
            .form(&[("type", "standard")])
            .send().await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        let body: Value = resp.json().await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        let id = body["id"].as_str().ok_or((StatusCode::INTERNAL_SERVER_ERROR, "Stripe error".to_string()))?.to_string();
        sqlx::query("UPDATE clubs SET stripe_account_id = $1 WHERE id = $2")
            .bind(&id).bind(org_id).execute(&state.pool).await.ok();
        id
    };

    let base_url = std::env::var("APP_BASE_URL").unwrap_or_else(|_| "http://localhost:8001".to_string());
    let client = reqwest::Client::new();
    let resp = client.post("https://api.stripe.com/v1/account_links")
        .header("Authorization", format!("Bearer {api_key}"))
        .form(&[
            ("account", account_id.as_str()),
            ("refresh_url", &format!("{base_url}/organizer?stripe=refresh")),
            ("return_url", &format!("{base_url}/organizer?stripe=success")),
            ("type", "account_onboarding"),
        ])
        .send().await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let body: Value = resp.json().await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let url = body["url"].as_str().unwrap_or("");

    Ok(Json(json!({"url": url})))
}

async fn stripe_status(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let org: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let org_id: Option<i32> = org.and_then(|r| r.0).and_then(|v| v.parse().ok());
    if org_id.is_none() {
        return Ok(Json(json!({"connected": false})));
    }

    let acct: Option<(Option<String>,)> = sqlx::query_as("SELECT stripe_account_id FROM clubs WHERE id = $1")
        .bind(org_id.unwrap()).fetch_optional(&state.pool).await.unwrap_or(None);
    match acct.and_then(|r| r.0) {
        Some(id) => Ok(Json(json!({"connected": true, "account_id": id}))),
        None => Ok(Json(json!({"connected": false}))),
    }
}

async fn stripe_disconnect(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let org: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let org_id: i32 = org.and_then(|r| r.0).and_then(|v| v.parse().ok())
        .ok_or((StatusCode::BAD_REQUEST, "No organizer club set".to_string()))?;

    sqlx::query("UPDATE clubs SET stripe_account_id = NULL WHERE id = $1")
        .bind(org_id).execute(&state.pool).await.ok();

    Ok(Json(json!({"ok": true})))
}
