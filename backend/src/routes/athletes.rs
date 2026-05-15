use axum::{
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    routing::{delete, get, post, put},
    Json, Router,
};
use chrono::{Datelike, NaiveDate};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::auth::{check_closure, resolve_role, Role};
use crate::state::AppState;

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/api/athletes", get(list_athletes).post(create_athlete))
        .route("/api/athletes/{athlete_id}", delete(delete_athlete).put(update_athlete))
        .route("/api/athletes/{athlete_id}/registration", get(get_registration))
}

#[derive(Deserialize)]
struct AthleteQuery {
    club_id: Option<i32>,
}

async fn list_athletes(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<AthleteQuery>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    let role = resolve_role(pin, &state.pool).await;
    if matches!(role, Role::None) {
        return Err((StatusCode::UNAUTHORIZED, "Authentication required".to_string()));
    }

    let club_id = match role {
        Role::Coach(id) => Some(id),
        _ => params.club_id,
    };

    let athletes: Vec<(i32, String, String, String, Option<NaiveDate>, Option<String>, String, i32)> = if let Some(cid) = club_id {
        sqlx::query_as(
            "SELECT a.id, a.first_name, a.last_name, a.gender::text, a.birthdate, a.license, c.name, a.club_id FROM athletes a JOIN clubs c ON a.club_id = c.id WHERE a.club_id = $1 ORDER BY a.last_name, a.first_name"
        ).bind(cid).fetch_all(&state.pool).await
    } else {
        sqlx::query_as(
            "SELECT a.id, a.first_name, a.last_name, a.gender::text, a.birthdate, a.license, c.name, a.club_id FROM athletes a JOIN clubs c ON a.club_id = c.id ORDER BY a.last_name, a.first_name"
        ).fetch_all(&state.pool).await
    }.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let result: Vec<Value> = athletes.iter().map(|a| json!({
        "id": a.0, "first_name": a.1, "last_name": a.2,
        "gender": a.3, "birthdate": a.4.map(|d| d.to_string()),
        "license": a.5, "club": a.6, "club_id": a.7,
    })).collect();

    Ok(Json(json!(result)))
}

async fn create_athlete(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    check_closure(&state.pool, pin).await?;

    let role = resolve_role(pin, &state.pool).await;
    let club_id = data["club_id"].as_i64().ok_or((StatusCode::BAD_REQUEST, "club_id required".to_string()))? as i32;

    if let Some(caller_club) = role.club_id() {
        if club_id != caller_club {
            return Err((StatusCode::FORBIDDEN, "Cannot create athletes in another club".to_string()));
        }
    }

    let first = data["first_name"].as_str().unwrap_or("").trim();
    let last = data["last_name"].as_str().unwrap_or("").trim();
    if first.is_empty() || last.is_empty() {
        return Err((StatusCode::BAD_REQUEST, "first_name and last_name required".to_string()));
    }
    let gender = data["gender"].as_str().unwrap_or("M");
    let birthdate: Option<NaiveDate> = data["birthdate"].as_str()
        .and_then(|s| NaiveDate::parse_from_str(s, "%Y-%m-%d").ok());
    let license = data["license"].as_str().unwrap_or("");

    let row: (i32,) = sqlx::query_as(
        "INSERT INTO athletes (first_name, last_name, gender, birthdate, license, club_id) VALUES ($1, $2, $3::gender, $4, $5, $6) RETURNING id"
    )
    .bind(first).bind(last).bind(gender).bind(birthdate).bind(license).bind(club_id)
    .fetch_one(&state.pool)
    .await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({"id": row.0})))
}

async fn delete_athlete(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(athlete_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    check_closure(&state.pool, pin).await?;

    let role = resolve_role(pin, &state.pool).await;
    let ath: Option<(i32,)> = sqlx::query_as("SELECT club_id FROM athletes WHERE id = $1")
        .bind(athlete_id).fetch_optional(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let ath_club = ath.ok_or((StatusCode::NOT_FOUND, "Not found".to_string()))?.0;

    if let Some(caller_club) = role.club_id() {
        if ath_club != caller_club {
            return Err((StatusCode::FORBIDDEN, "Cannot delete athletes from another club".to_string()));
        }
    }

    sqlx::query("DELETE FROM registrations WHERE athlete_id = $1").bind(athlete_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM best_times WHERE athlete_id = $1").bind(athlete_id).execute(&state.pool).await.ok();
    sqlx::query("DELETE FROM athletes WHERE id = $1").bind(athlete_id).execute(&state.pool).await.ok();

    Ok(Json(json!({"deleted": true})))
}

async fn update_athlete(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(athlete_id): Path<i32>,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let pin = headers.get("x-club-pin").and_then(|v| v.to_str().ok()).unwrap_or("");
    check_closure(&state.pool, pin).await?;

    let role = resolve_role(pin, &state.pool).await;
    let ath: Option<(i32,)> = sqlx::query_as("SELECT club_id FROM athletes WHERE id = $1")
        .bind(athlete_id).fetch_optional(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let ath_club = ath.ok_or((StatusCode::NOT_FOUND, "Not found".to_string()))?.0;

    if let Some(caller_club) = role.club_id() {
        if ath_club != caller_club {
            return Err((StatusCode::FORBIDDEN, "Cannot modify athletes from another club".to_string()));
        }
    }

    if let Some(v) = data["first_name"].as_str() {
        sqlx::query("UPDATE athletes SET first_name = $1 WHERE id = $2").bind(v).bind(athlete_id).execute(&state.pool).await.ok();
    }
    if let Some(v) = data["last_name"].as_str() {
        sqlx::query("UPDATE athletes SET last_name = $1 WHERE id = $2").bind(v).bind(athlete_id).execute(&state.pool).await.ok();
    }
    if let Some(v) = data["gender"].as_str() {
        sqlx::query("UPDATE athletes SET gender = $1::gender WHERE id = $2").bind(v).bind(athlete_id).execute(&state.pool).await.ok();
    }
    if let Some(v) = data["birthdate"].as_str() {
        let bd = NaiveDate::parse_from_str(v, "%Y-%m-%d").ok();
        sqlx::query("UPDATE athletes SET birthdate = $1 WHERE id = $2").bind(bd).bind(athlete_id).execute(&state.pool).await.ok();
    }
    if let Some(v) = data["license"].as_str() {
        sqlx::query("UPDATE athletes SET license = $1 WHERE id = $2").bind(v).bind(athlete_id).execute(&state.pool).await.ok();
    }

    Ok(Json(json!({"ok": true})))
}

async fn get_registration(
    State(state): State<AppState>,
    Path(athlete_id): Path<i32>,
) -> Result<Json<Value>, (StatusCode, String)> {
    let ath: Option<(i32, String, String, String, Option<NaiveDate>, Option<String>, i32)> = sqlx::query_as(
        "SELECT a.id, a.first_name, a.last_name, a.gender::text, a.birthdate, a.license, a.club_id FROM athletes a WHERE a.id = $1"
    ).bind(athlete_id).fetch_optional(&state.pool).await
    .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let ath = ath.ok_or((StatusCode::NOT_FOUND, "Athlete not found".to_string()))?;

    // Get club name
    let club_name: (String,) = sqlx::query_as("SELECT name FROM clubs WHERE id = $1")
        .bind(ath.6).fetch_one(&state.pool).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    // Get registrations
    let regs: Vec<(i32, i32, String, Option<i32>)> = sqlx::query_as(
        "SELECT id, event_id, age_code, entry_time_ms FROM registrations WHERE athlete_id = $1"
    ).bind(athlete_id).fetch_all(&state.pool).await.unwrap_or_default();

    // Get best times
    let bts: Vec<(i32, i32, String)> = sqlx::query_as(
        "SELECT style_uid, time_ms, course FROM best_times WHERE athlete_id = $1"
    ).bind(athlete_id).fetch_all(&state.pool).await.unwrap_or_default();

    let mut best_lcm: std::collections::HashMap<i32, i32> = std::collections::HashMap::new();
    let mut best_scm: std::collections::HashMap<i32, i32> = std::collections::HashMap::new();
    for bt in &bts {
        if bt.2 == "SCM" { best_scm.insert(bt.0, bt.1); } else { best_lcm.insert(bt.0, bt.1); }
    }

    // Get events
    let events: Vec<(i32, i32, Option<String>, Option<i32>, i32, Option<i32>, Option<i32>, Option<i32>, bool)> = sqlx::query_as(
        "SELECT id, style_uid, style_name, distance, relay_count, gender, event_number, round, masters FROM events ORDER BY event_number"
    ).fetch_all(&state.pool).await.unwrap_or_default();

    // Get age groups
    let age_groups: Vec<(i32, i32, i32)> = sqlx::query_as(
        "SELECT event_id, age_min, age_max FROM age_groups"
    ).fetch_all(&state.pool).await.unwrap_or_default();

    let ath_gender_int = if ath.3 == "M" { 1 } else { 2 };

    // Build style groups
    let mut styles: std::collections::HashMap<i32, Value> = std::collections::HashMap::new();

    for ev in &events {
        if ev.7 == Some(9) { continue; } // skip finals
        if ev.4 == 1 && ev.5.unwrap_or(0) != 0 && ev.5.unwrap_or(0) != ath_gender_int { continue; }

        let event_ags: Vec<&(i32, i32, i32)> = age_groups.iter().filter(|ag| ag.0 == ev.0).collect();
        let mut codes: Vec<String> = Vec::new();
        if ev.8 {
            codes.push("Masters".to_string());
        } else {
            for ag in &event_ags {
                if let Some(code) = age_group_code(ag.1, ag.2) {
                    if !codes.contains(&code) { codes.push(code); }
                }
            }
        }
        if codes.is_empty() { continue; }

        let style = styles.entry(ev.1).or_insert_with(|| json!({
            "style_uid": ev.1,
            "style_name": ev.2,
            "distance": ev.3,
            "relay_count": ev.4,
            "categories": [],
        }));

        let cats = style["categories"].as_array_mut().unwrap();
        for code in &codes {
            if cats.iter().any(|c| c["age_code"].as_str() == Some(code)) { continue; }
            let reg = regs.iter().find(|r| r.1 == ev.0 && r.2 == *code);
            cats.push(json!({
                "event_id": ev.0,
                "age_code": code,
                "registered": reg.is_some(),
                "registration_id": reg.map(|r| r.0),
                "entry_time_ms": reg.and_then(|r| r.3),
            }));
        }
    }

    let mut individual: Vec<Value> = Vec::new();
    let mut relay: Vec<Value> = Vec::new();
    for (uid, mut s) in styles {
        s["best_time_lcm_ms"] = json!(best_lcm.get(&uid));
        s["best_time_scm_ms"] = json!(best_scm.get(&uid));
        if s["relay_count"].as_i64().unwrap_or(1) > 1 {
            relay.push(s);
        } else {
            individual.push(s);
        }
    }

    // Suggested age code
    let suggested = if let Some(bd) = ath.4 {
        let age = 2026 - bd.year();
        match age {
            ..=10 => "10-",
            11..=12 => "11-12",
            13..=14 => "13-14",
            15..=18 => "15-18",
            _ => "Open",
        }
    } else {
        "Open"
    };

    let meet_course: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'meet_course'")
        .fetch_optional(&state.pool).await.unwrap_or(None);
    let closure: Option<(Option<String>,)> = sqlx::query_as("SELECT value FROM app_config WHERE key = 'closure_date'")
        .fetch_optional(&state.pool).await.unwrap_or(None);

    Ok(Json(json!({
        "athlete": {
            "id": ath.0, "first_name": ath.1, "last_name": ath.2,
            "gender": ath.3, "birthdate": ath.4.map(|d| d.to_string()).unwrap_or_default(),
            "license": ath.5.unwrap_or_default(), "club": club_name.0, "club_id": ath.6,
        },
        "suggested_age_code": suggested,
        "meet_course": meet_course.and_then(|r| r.0).unwrap_or_else(|| "LCM".to_string()),
        "closure_date": closure.and_then(|r| r.0),
        "individual_events": individual,
        "relay_events": relay,
        "club_athletes": [],
    })))
}

fn age_group_code(age_min: i32, age_max: i32) -> Option<String> {
    if age_min <= 10 && age_max == 10 { return Some("10-".to_string()); }
    if age_min == 11 && age_max == 12 { return Some("11-12".to_string()); }
    if age_min == 13 && age_max == 14 { return Some("13-14".to_string()); }
    if age_min == 15 && age_max == 18 { return Some("15-18".to_string()); }
    if age_min == 19 && age_max == -1 { return Some("Open".to_string()); }
    None
}
