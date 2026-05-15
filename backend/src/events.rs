use sqlx::PgPool;
use serde_json;

use crate::meet_parser::ParsedMeet;

pub async fn load_from_parsed(pool: &PgPool, meet: &ParsedMeet) -> Result<i32, sqlx::Error> {
    let mut count = 0;
    for ev in meet.all_events() {
        let round_int = if ev.is_prelim() {
            2
        } else if ev.round == "TIM" {
            1
        } else {
            9
        };
        let row: (i32,) = sqlx::query_as(
            "INSERT INTO events (splash_event_id, style_uid, style_name, distance, relay_count, gender, event_number, round, masters, fee_cents)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id"
        )
        .bind(ev.eventid)
        .bind(ev.swimstyleid)
        .bind(&ev.style_name)
        .bind(ev.distance)
        .bind(ev.relaycount)
        .bind(ev.gender_int())
        .bind(ev.number)
        .bind(round_int)
        .bind(ev.is_masters())
        .bind(ev.fee_cents)
        .fetch_one(pool)
        .await?;

        for ag in &ev.agegroups {
            let code = age_range_to_code(ag.agemin, ag.agemax);
            sqlx::query(
                "INSERT INTO age_groups (event_id, splash_agegroup_id, code, age_min, age_max) VALUES ($1, $2, $3, $4, $5)"
            )
            .bind(row.0)
            .bind(ag.agegroupid)
            .bind(&code)
            .bind(ag.agemin)
            .bind(ag.agemax)
            .execute(pool)
            .await?;
        }
        count += 1;
    }

    // Cache style names in app_config so they survive meet flush
    let mut style_map: std::collections::HashMap<i32, String> = std::collections::HashMap::new();
    for ev in meet.all_events() {
        if !ev.style_name.is_empty() {
            style_map.entry(ev.swimstyleid).or_insert_with(|| ev.style_name.clone());
        }
    }
    if !style_map.is_empty() {
        // Merge with existing cache
        let existing: Option<(String,)> = sqlx::query_as(
            "SELECT value FROM app_config WHERE key = 'style_names_json'"
        ).fetch_optional(pool).await.unwrap_or(None);
        let mut merged: std::collections::HashMap<i32, String> = existing
            .and_then(|r| serde_json::from_str(&r.0).ok())
            .unwrap_or_default();
        for (k, v) in style_map {
            merged.insert(k, v);
        }
        let json_str = serde_json::to_string(&merged).unwrap_or_default();
        sqlx::query(
            "INSERT INTO app_config (key, value) VALUES ('style_names_json', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        ).bind(&json_str).execute(pool).await.ok();
    }

    Ok(count)
}

pub async fn load_events_if_empty(pool: &PgPool, lxf_path: &std::path::Path) -> Result<i32, String> {
    let exists: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM events")
        .fetch_one(pool)
        .await
        .map_err(|e| e.to_string())?;
    if exists.0 > 0 {
        return Ok(0);
    }
    let data = std::fs::read(lxf_path).map_err(|e| e.to_string())?;
    let meet = crate::meet_parser::parse_meet_lxf(&data)?;
    load_from_parsed(pool, &meet).await.map_err(|e| e.to_string())
}

fn age_range_to_code(agemin: i32, agemax: i32) -> String {
    match (agemin, agemax) {
        (_, -1) => "Open".to_string(),
        (0, max) if max <= 10 => "10-".to_string(),
        (1, max) if max <= 10 => "10-".to_string(),
        (11, 12) => "11-12".to_string(),
        (13, 14) => "13-14".to_string(),
        (15, 18) => "15-18".to_string(),
        (15, _) => "15-18".to_string(),
        (19, _) | (0, 99) | (0, 0) => "Open".to_string(),
        (min, _) if min >= 25 => "Masters".to_string(),
        (min, max) => format!("{min}-{max}"),
    }
}
