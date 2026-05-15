use axum::{
    extract::State,
    http::{header, HeaderMap, StatusCode},
    response::IntoResponse,
    routing::get,
    Router,
};
use std::path::PathBuf;

use crate::auth::{require_admin, require_organizer_or_admin};
use crate::export;
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/export", get(export_registrations))
        .route("/api/export/entries", get(export_entries))
        .route("/api/export/meet-smb", get(export_meet_smb))
}

async fn export_registrations(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let lxf_bytes = export::generate_lxf(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;

    // Bundle into zip with scripts
    let scripts_dir = PathBuf::from(
        std::env::var("SCRIPTS_DIR").unwrap_or_else(|_| "/app/scripts".to_string()),
    );

    let mut zip_buf = std::io::Cursor::new(Vec::new());
    {
        let mut zip = zip::ZipWriter::new(&mut zip_buf);
        zip.start_file("inscriptions.lxf", zip::write::SimpleFileOptions::default())
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        std::io::Write::write_all(&mut zip, &lxf_bytes)
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

        for name in ["simulate_results.vbs", "simulate_results.bat"] {
            let p = scripts_dir.join(name);
            if p.exists() {
                zip.start_file(name, zip::write::SimpleFileOptions::default()).ok();
                if let Ok(data) = std::fs::read(&p) {
                    std::io::Write::write_all(&mut zip, &data).ok();
                }
            }
        }
        zip.finish().map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }

    Ok((
        [
            (header::CONTENT_TYPE, "application/zip".to_string()),
            (header::CONTENT_DISPOSITION, "attachment; filename=inscriptions_bundle.zip".to_string()),
        ],
        zip_buf.into_inner(),
    ))
}

async fn export_entries(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let data = export::generate_entries_lxf(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;

    Ok((
        [
            (header::CONTENT_TYPE, "application/zip".to_string()),
            (header::CONTENT_DISPOSITION, "attachment; filename=entries.lxf".to_string()),
        ],
        data,
    ))
}

async fn export_meet_smb(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let template = std::env::var("MEET_TEMPLATE").unwrap_or_else(|_| "/app/templates/meet.smb".to_string());
    let path = PathBuf::from(&template);
    if !path.exists() {
        return Err((StatusCode::NOT_FOUND, "Meet template not found".to_string()));
    }
    let data = std::fs::read(&path).map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let fname = path.file_name().unwrap_or_default().to_string_lossy().to_string();
    let disposition = format!("attachment; filename={fname}");

    Ok((
        [
            (header::CONTENT_TYPE, "application/octet-stream".to_string()),
            (header::CONTENT_DISPOSITION, disposition),
        ],
        data,
    ))
}
