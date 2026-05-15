use axum::http::StatusCode;
use sqlx::PgPool;
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

use crate::state::AppState;

#[derive(Debug, Clone, PartialEq)]
pub enum Role {
    Admin,
    Organizer(i32),
    Coach(i32),
    None,
}

impl Role {
    pub fn club_id(&self) -> Option<i32> {
        match self {
            Role::Organizer(id) | Role::Coach(id) => Some(*id),
            _ => None,
        }
    }

    pub fn is_admin(&self) -> bool {
        matches!(self, Role::Admin)
    }

    pub fn is_admin_or_organizer(&self) -> bool {
        matches!(self, Role::Admin | Role::Organizer(_))
    }
}

pub async fn get_admin_pin(pool: &PgPool) -> String {
    let row: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'admin_pin'")
            .fetch_optional(pool)
            .await
            .unwrap_or(None);
    row.and_then(|r| r.0)
        .unwrap_or_else(|| std::env::var("ADMIN_PIN").unwrap_or_else(|_| "000000".to_string()))
}

pub async fn resolve_role(pin: &str, pool: &PgPool) -> Role {
    if pin.is_empty() {
        return Role::None;
    }
    let admin_pin = get_admin_pin(pool).await;
    if pin == admin_pin {
        return Role::Admin;
    }
    let club: Option<(i32,)> = sqlx::query_as("SELECT id FROM clubs WHERE pin = $1")
        .bind(pin)
        .fetch_optional(pool)
        .await
        .unwrap_or(None);
    let club_id = match club {
        Some((id,)) => id,
        None => return Role::None,
    };
    let org: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'organizer_club_id'")
            .fetch_optional(pool)
            .await
            .unwrap_or(None);
    if let Some((Some(val),)) = org {
        if val == club_id.to_string() {
            return Role::Organizer(club_id);
        }
    }
    Role::Coach(club_id)
}

// Rate limiter: 5 attempts per IP per 60s
pub struct RateLimiter {
    attempts: Mutex<HashMap<String, Vec<Instant>>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self {
            attempts: Mutex::new(HashMap::new()),
        }
    }

    pub fn check(&self, ip: &str) -> Result<(), ()> {
        let mut map = self.attempts.lock().unwrap();
        let now = Instant::now();
        let entries = map.entry(ip.to_string()).or_default();
        entries.retain(|t| now.duration_since(*t).as_secs() < 60);
        if entries.len() >= 5 {
            return Err(());
        }
        entries.push(now);
        Ok(())
    }
}

pub async fn require_admin(
    state: &AppState,
    pin: &str,
) -> Result<(), (StatusCode, &'static str)> {
    let admin_pin = get_admin_pin(&state.pool).await;
    if pin != admin_pin {
        return Err((StatusCode::FORBIDDEN, "Admin access required"));
    }
    Ok(())
}

pub async fn require_organizer_or_admin(
    state: &AppState,
    pin: &str,
) -> Result<(), (StatusCode, &'static str)> {
    let role = resolve_role(pin, &state.pool).await;
    if !role.is_admin_or_organizer() {
        return Err((StatusCode::FORBIDDEN, "Organizer or admin access required"));
    }
    Ok(())
}

pub async fn check_closure(pool: &PgPool, pin: &str) -> Result<(), (StatusCode, String)> {
    let admin_pin = get_admin_pin(pool).await;
    if pin == admin_pin {
        return Ok(());
    }
    // Organizer bypasses closure
    let role = resolve_role(pin, pool).await;
    if matches!(role, Role::Organizer(_)) {
        return Ok(());
    }
    let row: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'closure_date'")
            .fetch_optional(pool)
            .await
            .unwrap_or(None);
    if let Some((Some(val),)) = row {
        if !val.is_empty() {
            if let Ok(closure) = chrono::NaiveDate::parse_from_str(&val, "%Y-%m-%d") {
                if chrono::Local::now().date_naive() > closure {
                    return Err((
                        StatusCode::FORBIDDEN,
                        "Inscriptions fermées / Entries closed".to_string(),
                    ));
                }
            }
        }
    }
    Ok(())
}
