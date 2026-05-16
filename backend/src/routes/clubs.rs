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
        .route("/api/clubs/:club_id/send-pin", post(send_pin))
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
    let code = data["code"].as_str().unwrap_or("").trim();
    if code.is_empty() {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, "code required".to_string()));
    }
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

async fn send_pin(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(club_id): Path<i32>,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    crate::auth::require_organizer_or_admin(&state, pin).await.map_err(|(s, m)| (s, m.to_string()))?;

    let club: Option<(i32, String, Option<String>, Option<String>)> =
        sqlx::query_as("SELECT id, name, pin, admin_email FROM clubs WHERE id = $1")
            .bind(club_id)
            .fetch_optional(&state.pool)
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let club = club.ok_or((StatusCode::NOT_FOUND, "Club not found".to_string()))?;
    let club_name = &club.1;
    let club_pin = club.2.as_deref().unwrap_or("");
    let admin_email = club.3.as_deref().unwrap_or("");
    if admin_email.is_empty() {
        return Err((StatusCode::BAD_REQUEST, "No admin email set for this club".to_string()));
    }

    let lang = data["lang"].as_str().unwrap_or("fr");
    let resend_key = std::env::var("RESEND_API_KEY").unwrap_or_default();
    if resend_key.is_empty() {
        return Err((StatusCode::INTERNAL_SERVER_ERROR, "RESEND_API_KEY not configured".to_string()));
    }
    let secret_key = std::env::var("SECRET_KEY").unwrap_or_default();
    if secret_key.is_empty() {
        return Err((StatusCode::INTERNAL_SERVER_ERROR, "SECRET_KEY not configured".to_string()));
    }

    // Encrypt PIN with AES-256-GCM (key derived from SECRET_KEY via SHA-256)
    use sha2::{Sha256, Digest};
    use base64::Engine;
    use aes_gcm::{Aes256Gcm, KeyInit, aead::Aead};
    use aes_gcm::Nonce;
    let hash = Sha256::digest(secret_key.as_bytes());
    let cipher = Aes256Gcm::new_from_slice(&hash)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Invalid key".to_string()))?;
    let nonce_bytes: [u8; 12] = rand::random();
    let nonce = Nonce::from_slice(&nonce_bytes);
    let ciphertext = cipher.encrypt(nonce, club_pin.as_bytes())
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Encryption failed".to_string()))?;
    // Store as base64(nonce + ciphertext)
    let mut combined = nonce_bytes.to_vec();
    combined.extend_from_slice(&ciphertext);
    let pin_encrypted = base64::engine::general_purpose::URL_SAFE.encode(&combined);

    // Create secret link
    let token = uuid::Uuid::new_v4().to_string();
    let expires = chrono::Utc::now() + chrono::Duration::days(7);
    sqlx::query("INSERT INTO secret_links (token, club_id, pin_encrypted, expires_at, lang) VALUES ($1, $2, $3, $4, $5)")
        .bind(&token)
        .bind(club_id)
        .bind(&pin_encrypted)
        .bind(expires.naive_utc())
        .bind(lang)
        .execute(&state.pool)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let base_url = std::env::var("APP_BASE_URL").unwrap_or_else(|_| "http://localhost:8001".to_string());
    let secret_url = format!("{}/secret/{}", base_url, token);

    // Get meet info
    let meet_name: String = sqlx::query_scalar("SELECT value FROM app_config WHERE key = 'meet_name'")
        .fetch_optional(&state.pool).await.unwrap_or(None).unwrap_or_else(|| "Meet".to_string());
    let closure_date: Option<String> = sqlx::query_scalar("SELECT value FROM app_config WHERE key = 'closure_date'")
        .fetch_optional(&state.pool).await.unwrap_or(None);

    // Determine if recipient is the organizer
    let org_club_id: Option<String> = sqlx::query_scalar("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let is_organizer = org_club_id.as_deref() == Some(&club_id.to_string());

    // Organizer info for coach contact note
    let (org_email, org_club_name) = if !is_organizer {
        if let Some(ref oid) = org_club_id {
            if let Ok(oid_int) = oid.parse::<i32>() {
                let row: Option<(String, Option<String>)> = sqlx::query_as(
                    "SELECT name, admin_email FROM clubs WHERE id = $1"
                ).bind(oid_int).fetch_optional(&state.pool).await.unwrap_or(None);
                match row {
                    Some((name, email)) => (email.unwrap_or_default(), name),
                    None => (String::new(), String::new()),
                }
            } else { (String::new(), String::new()) }
        } else { (String::new(), String::new()) }
    } else { (String::new(), String::new()) };

    let support_email = std::env::var("SUPPORT_EMAIL").unwrap_or_default();

    // Build footer
    let mut footer = String::from("<hr style=\"margin-top:20px\">");
    if is_organizer {
        if !support_email.is_empty() {
            if lang == "fr" {
                footer.push_str(&format!("<p>Pour toute question, contactez le support : <a href=\"mailto:{0}\">{0}</a></p>", support_email));
            } else {
                footer.push_str(&format!("<p>If you have questions, contact support: <a href=\"mailto:{0}\">{0}</a></p>", support_email));
            }
        }
    } else {
        let mut lines: Vec<String> = Vec::new();
        if lang == "fr" {
            if !org_email.is_empty() {
                lines.push(format!("Pour toute question sur la compétition, contactez l'organisateur ({}) : <a href=\"mailto:{1}\">{1}</a>", org_club_name, org_email));
            }
            if !support_email.is_empty() {
                lines.push(format!("Pour de l'aide avec le portail d'inscription, contactez le support : <a href=\"mailto:{0}\">{0}</a>", support_email));
            }
        } else {
            if !org_email.is_empty() {
                lines.push(format!("If you have questions about the meet, contact the organizer ({}): <a href=\"mailto:{1}\">{1}</a>", org_club_name, org_email));
            }
            if !support_email.is_empty() {
                lines.push(format!("For help with the registration portal, contact support: <a href=\"mailto:{0}\">{0}</a>", support_email));
            }
        }
        if !lines.is_empty() {
            footer.push_str(&format!("<p>{}</p>", lines.join("<br>")));
        }
    }
    if lang == "fr" {
        footer.push_str("<p style=\"font-size:11px;color:#888\">Ce courriel est envoyé automatiquement. Veuillez ne pas répondre à ce courriel.</p>");
    } else {
        footer.push_str("<p style=\"font-size:11px;color:#888\">This is an automated message. Please do not reply to this email.</p>");
    }

    // Build email HTML
    let (subject, html) = if lang == "fr" {
        let deadline = if let Some(ref cd) = closure_date {
            if !cd.is_empty() {
                format!("<p style=\"color:#c00;font-weight:bold\">⚠️ Date limite d'inscription : {}. Après cette date, vous ne pourrez plus accéder au portail d'inscription.</p>", cd)
            } else { String::new() }
        } else { String::new() };
        let org_line = if !org_club_name.is_empty() { format!(", organisée par <strong>{}</strong>", org_club_name) } else { String::new() };
        (
            format!("Invitation — {}", meet_name),
            format!(
                "<p>Bonjour,</p>\
                <p>Vous êtes invité(e) à inscrire les athlètes de votre équipe <strong>{club_name}</strong> à la compétition <strong>{meet_name}</strong>{org_line}.</p>\
                {deadline}\
                <p><strong>Marche à suivre :</strong></p>\
                <ol>\
                <li><strong>Récupérer votre NIP.</strong> Cliquer sur le lien sécurisé ci-dessous pour afficher votre NIP. <em>Le lien est à usage unique et expire dans 7 jours — prenez le NIP en note immédiatement, il ne pourra plus être affiché par la suite.</em><br><a href=\"{secret_url}\">{secret_url}</a></li>\
                <li><strong>Ouvrir le portail d'inscription</strong> à l'adresse <a href=\"{base_url}\">{base_url}</a> et se connecter avec le NIP de votre équipe.</li>\
                <li><strong>Inscrire vos athlètes.</strong> Sélectionner un athlète, cocher les épreuves, choisir la catégorie (15-18 / Open / Masters) et ajuster le temps d'inscription si nécessaire. Répéter pour chaque athlète à inscrire.</li>\
                </ol>\
                <p>Bonne compétition!</p>\
                {footer}",
            ),
        )
    } else {
        let deadline = if let Some(ref cd) = closure_date {
            if !cd.is_empty() {
                format!("<p style=\"color:#c00;font-weight:bold\">⚠️ Entry deadline: {}. After this date, you will no longer be able to access the registration portal.</p>", cd)
            } else { String::new() }
        } else { String::new() };
        let org_line = if !org_club_name.is_empty() { format!(", organized by <strong>{}</strong>", org_club_name) } else { String::new() };
        (
            format!("Invitation — {}", meet_name),
            format!(
                "<p>Hello,</p>\
                <p>You are invited to register the athletes of your team <strong>{club_name}</strong> for <strong>{meet_name}</strong>{org_line}.</p>\
                {deadline}\
                <p><strong>How to proceed:</strong></p>\
                <ol>\
                <li><strong>Get your PIN.</strong> Click the secure link below to reveal your PIN. <em>The link can only be used once and expires in 7 days — write the PIN down immediately, it will not be shown again.</em><br><a href=\"{secret_url}\">{secret_url}</a></li>\
                <li><strong>Open the registration portal</strong> at <a href=\"{base_url}\">{base_url}</a> and log in with your team's PIN.</li>\
                <li><strong>Register your athletes.</strong> Pick an athlete, check the events, select the category (15-18 / Open / Masters) and adjust the entry time if needed. Repeat for every athlete you want to register.</li>\
                </ol>\
                <p>Good luck!</p>\
                {footer}",
            ),
        )
    };

    // Send via Resend
    let from_email = std::env::var("RESEND_FROM_EMAIL").unwrap_or_else(|_| "noreply@example.com".to_string());
    let client = reqwest::Client::new();
    let resp = client.post("https://api.resend.com/emails")
        .header("Authorization", format!("Bearer {}", resend_key))
        .json(&json!({
            "from": from_email,
            "to": [admin_email],
            "subject": subject,
            "html": html,
        }))
        .send()
        .await
        .map_err(|e| (StatusCode::BAD_GATEWAY, format!("Resend error: {}", e)))?;

    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err((StatusCode::BAD_GATEWAY, format!("Resend error: {}", body)));
    }

    sqlx::query("UPDATE clubs SET invite_send_count = invite_send_count + 1 WHERE id = $1")
        .bind(club_id)
        .execute(&state.pool)
        .await
        .ok();

    Ok(Json(json!({"message": format!("Email sent to {}", admin_email)})))
}

fn generate_pin() -> String {
    let mut rng = rand::thread_rng();
    (0..6).map(|_| rng.gen_range(0..10).to_string()).collect()
}
