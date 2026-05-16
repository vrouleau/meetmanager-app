use axum::{
    extract::{Multipart, State},
    http::{HeaderMap, StatusCode},
    routing::post,
    Json, Router,
};
use rand::Rng;
use serde_json::{json, Value};
use std::path::PathBuf;

use crate::auth::{require_admin, require_organizer_or_admin};
use crate::events::load_from_parsed;
use crate::meet_parser::parse_meet_lxf;
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/upload/meet", post(upload_meet))
        .route("/api/upload/entries", post(upload_entries))
        .route("/api/upload/results", post(upload_results))
}

async fn extract_file(mut multipart: Multipart) -> Result<(String, Vec<u8>), (StatusCode, String)> {
    while let Some(field) = multipart.next_field().await.map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))? {
        let filename = field.file_name().unwrap_or("upload.lxf").to_string();
        let data = field.bytes().await.map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?;
        if !data.is_empty() {
            return Ok((filename, data.to_vec()));
        }
    }
    Err((StatusCode::BAD_REQUEST, "No file uploaded".to_string()))
}

async fn upload_meet(
    State(state): State<AppState>,
    headers: HeaderMap,
    multipart: Multipart,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let (filename, content) = extract_file(multipart).await?;
    if content.len() > 10 * 1024 * 1024 {
        return Err((StatusCode::PAYLOAD_TOO_LARGE, "File too large (max 10MB)".to_string()));
    }

    let meet = parse_meet_lxf(&content)
        .map_err(|e| (StatusCode::BAD_REQUEST, format!("Invalid meet .lxf: {e}")))?;

    let storage = std::env::var("MEET_STORAGE").unwrap_or_else(|_| "/app/data/meet.lxf".to_string());
    let path = PathBuf::from(&storage);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    std::fs::write(&path, &content).map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    sqlx::query("DELETE FROM registrations").execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM age_groups").execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM events").execute(&state.pool).await.ok();

    let count = load_from_parsed(&state.pool, &meet)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let now = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%S").to_string();
    let fees_json = serde_json::to_string(&meet.meet_fees).unwrap_or_default();

    for (key, val) in [
        ("meet_filename", filename.as_str()),
        ("meet_uploaded_at", &now),
        ("meet_name", &meet.meet_name),
        ("meet_course", &meet.course),
        ("meet_masters", if meet.masters { "T" } else { "F" }),
        ("meet_currency", &meet.currency),
        ("meet_fees_json", &fees_json),
        ("age_base_date", &meet.age_base_date),
    ] {
        sqlx::query("INSERT INTO app_config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2")
            .bind(key).bind(val).execute(&state.pool).await.ok();
    }

    sqlx::query("INSERT INTO app_config (key, value) VALUES ('closure_date', '') ON CONFLICT (key) DO UPDATE SET value = ''")
        .execute(&state.pool).await.ok();

    let clubs: Vec<(i32,)> = sqlx::query_as("SELECT id FROM clubs")
        .fetch_all(&state.pool).await.unwrap_or_default();
    let pins: Vec<String> = clubs.iter().map(|_| {
        let mut rng = rand::thread_rng();
        (0..6).map(|_| rng.gen_range(0..10).to_string()).collect()
    }).collect();
    for (i, (id,)) in clubs.iter().enumerate() {
        sqlx::query("UPDATE clubs SET pin = $1 WHERE id = $2")
            .bind(&pins[i]).bind(id).execute(&state.pool).await.ok();
    }

    Ok(Json(json!({"events_loaded": count, "filename": filename})))
}

async fn upload_entries(
    State(state): State<AppState>,
    headers: HeaderMap,
    multipart: Multipart,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let (filename, content) = extract_file(multipart).await?;
    if content.len() > 10 * 1024 * 1024 {
        return Err((StatusCode::PAYLOAD_TOO_LARGE, "File too large".to_string()));
    }

    let seed_result = crate::seed::seed_from_lxf(&state.pool, &content).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;
    let times_result = crate::best_times::load_best_times(&state.pool, &content, &filename).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;

    let event_count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM events")
        .fetch_one(&state.pool).await.unwrap_or((0,));
    let mut events_loaded = 0;
    if event_count.0 == 0 {
        if let Ok(meet) = parse_meet_lxf(&content) {
            if !meet.all_events().is_empty() {
                events_loaded = load_from_parsed(&state.pool, &meet).await.unwrap_or(0);
            }
        }
    }

    Ok(Json(json!({
        "clubs_added": seed_result.clubs_added,
        "athletes_added": seed_result.athletes_added,
        "times_updated": times_result.times_updated,
        "athletes_skipped": times_result.athletes_skipped,
        "events_loaded": events_loaded,
    })))
}

async fn upload_results(
    State(state): State<AppState>,
    headers: HeaderMap,
    multipart: Multipart,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let (filename, content) = extract_file(multipart).await?;

    let seed_result = crate::seed::seed_from_lxf(&state.pool, &content).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;
    let times_result = crate::best_times::load_best_times(&state.pool, &content, &filename).await
        .map_err(|e| (StatusCode::BAD_REQUEST, e))?;

    Ok(Json(json!({
        "clubs_added": seed_result.clubs_added,
        "athletes_added": seed_result.athletes_added,
        "times_updated": times_result.times_updated,
        "athletes_skipped": times_result.athletes_skipped,
    })))
}
