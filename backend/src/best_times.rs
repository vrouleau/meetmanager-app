use chrono::NaiveDate;
use quick_xml::events::Event as XmlEvent;
use quick_xml::Reader;
use serde::Serialize;
use sqlx::PgPool;
use std::collections::HashMap;

use crate::meet_parser::extract_lef_from_zip;

#[derive(Debug, Serialize)]
pub struct BestTimesResult {
    pub times_updated: i32,
    pub athletes_skipped: i32,
    pub athletes_created: i32,
}

/// Convert Lenex time string to milliseconds
fn lenex_time_to_ms(t: &str) -> Option<i32> {
    if t.is_empty() || t == "NT" {
        return None;
    }
    // HH:MM:SS.hh
    if let Some(caps) = regex_match_4(t) {
        return Some(caps.0 * 3600000 + caps.1 * 60000 + caps.2 * 1000 + caps.3 * 10);
    }
    // MM:SS.hh
    if let Some(caps) = regex_match_3(t) {
        return Some(caps.0 * 60000 + caps.1 * 1000 + caps.2 * 10);
    }
    // SS.hh
    if let Some(caps) = regex_match_2(t) {
        return Some(caps.0 * 1000 + caps.1 * 10);
    }
    None
}

fn regex_match_4(t: &str) -> Option<(i32, i32, i32, i32)> {
    let parts: Vec<&str> = t.splitn(2, '.').collect();
    if parts.len() != 2 {
        return None;
    }
    let cs: i32 = parts[1].parse().ok()?;
    let time_parts: Vec<&str> = parts[0].split(':').collect();
    if time_parts.len() != 3 {
        return None;
    }
    Some((
        time_parts[0].parse().ok()?,
        time_parts[1].parse().ok()?,
        time_parts[2].parse().ok()?,
        cs,
    ))
}

fn regex_match_3(t: &str) -> Option<(i32, i32, i32)> {
    let parts: Vec<&str> = t.splitn(2, '.').collect();
    if parts.len() != 2 {
        return None;
    }
    let cs: i32 = parts[1].parse().ok()?;
    let time_parts: Vec<&str> = parts[0].split(':').collect();
    if time_parts.len() != 2 {
        return None;
    }
    Some((
        time_parts[0].parse().ok()?,
        time_parts[1].parse().ok()?,
        cs,
    ))
}

fn regex_match_2(t: &str) -> Option<(i32, i32)> {
    let parts: Vec<&str> = t.splitn(2, '.').collect();
    if parts.len() != 2 {
        return None;
    }
    Some((parts[0].parse().ok()?, parts[1].parse().ok()?))
}

async fn upsert_best_time(
    pool: &PgPool,
    athlete_id: i32,
    style_uid: i32,
    time_ms: i32,
    course: &str,
    source: &str,
    recorded_on: Option<NaiveDate>,
) -> Result<bool, sqlx::Error> {
    let existing: Option<(i32, i32, Option<NaiveDate>)> = sqlx::query_as(
        "SELECT id, time_ms, recorded_on FROM best_times WHERE athlete_id = $1 AND style_uid = $2 AND course = $3",
    )
    .bind(athlete_id)
    .bind(style_uid)
    .bind(course)
    .fetch_optional(pool)
    .await?;

    let improved = if let Some((id, existing_ms, existing_date)) = existing {
        if time_ms < existing_ms {
            sqlx::query("UPDATE best_times SET time_ms = $1, source = $2, recorded_on = COALESCE($3, recorded_on) WHERE id = $4")
                .bind(time_ms)
                .bind(source)
                .bind(recorded_on)
                .bind(id)
                .execute(pool)
                .await?;
            true
        } else {
            if recorded_on.is_some() && existing_date.is_none() {
                sqlx::query("UPDATE best_times SET recorded_on = $1 WHERE id = $2")
                    .bind(recorded_on)
                    .bind(id)
                    .execute(pool)
                    .await?;
            }
            false
        }
    } else {
        sqlx::query(
            "INSERT INTO best_times (athlete_id, style_uid, time_ms, course, source, recorded_on) VALUES ($1, $2, $3, $4, $5, $6)",
        )
        .bind(athlete_id)
        .bind(style_uid)
        .bind(time_ms)
        .bind(course)
        .bind(source)
        .bind(recorded_on)
        .execute(pool)
        .await?;
        true
    };

    // Sync recorded_on to sibling course
    if let Some(date) = recorded_on {
        let sibling_course = if course == "LCM" { "SCM" } else { "LCM" };
        sqlx::query("UPDATE best_times SET recorded_on = $1 WHERE athlete_id = $2 AND style_uid = $3 AND course = $4")
            .bind(date)
            .bind(athlete_id)
            .bind(style_uid)
            .bind(sibling_course)
            .execute(pool)
            .await?;
    }

    Ok(improved)
}

pub async fn load_best_times(pool: &PgPool, data: &[u8], source: &str) -> Result<BestTimesResult, String> {
    let xml = extract_lef_from_zip(data)?;
    let mut reader = Reader::from_reader(xml.as_slice());
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();

    let mut course = "LCM".to_string();
    let mut recorded_on: Option<NaiveDate> = None;
    let mut event_style: HashMap<String, i32> = HashMap::new();
    let mut updated = 0i32;
    let mut skipped = 0i32;

    // First pass: get meet-level course and date, and build event->style map
    // We'll do a single-pass approach with state tracking
    let mut in_club = false;
    let mut in_athlete = false;
    let mut in_event_def = false;
    let mut current_club_code = String::new();
    let mut current_club_name = String::new();
    let mut current_ath_first = String::new();
    let mut current_ath_last = String::new();
    let mut current_ath_license = String::new();

    // We need two passes: first to get event_style map, then to process athletes
    // Let's collect everything in one pass using state

    // Actually, let's do a simpler two-pass approach
    drop(reader);

    // Pass 1: extract metadata
    let mut reader = Reader::from_reader(xml.as_slice());
    reader.config_mut().trim_text(true);
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(XmlEvent::Eof) => break,
            Ok(XmlEvent::Start(ref e)) | Ok(XmlEvent::Empty(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                match tag.as_str() {
                    "MEET" => {
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "course" => {
                                    if val == "LCM" || val == "SCM" {
                                        course = val;
                                    }
                                }
                                "startdate" | "date" => {
                                    if recorded_on.is_none() {
                                        recorded_on = NaiveDate::parse_from_str(
                                            &val[..10.min(val.len())],
                                            "%Y-%m-%d",
                                        )
                                        .ok();
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                    "SESSION" => {
                        if recorded_on.is_none() {
                            for attr in e.attributes().flatten() {
                                let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                                let val = String::from_utf8_lossy(&attr.value).to_string();
                                if key == "date" {
                                    recorded_on = NaiveDate::parse_from_str(
                                        &val[..10.min(val.len())],
                                        "%Y-%m-%d",
                                    )
                                    .ok();
                                }
                            }
                        }
                    }
                    "EVENT" => {
                        let mut eid = String::new();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            if key == "eventid" {
                                eid = val;
                            }
                        }
                        if !eid.is_empty() {
                            // Look for SWIMSTYLE in next events
                            // Store eid for when we find SWIMSTYLE
                            current_club_code = eid; // reuse variable temporarily
                            in_event_def = true;
                        }
                    }
                    "SWIMSTYLE" if in_event_def => {
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            if key == "swimstyleid" {
                                if let Ok(uid) = val.parse::<i32>() {
                                    event_style.insert(current_club_code.clone(), uid);
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(XmlEvent::End(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                if tag == "EVENT" {
                    in_event_def = false;
                }
            }
            Err(e) => return Err(format!("XML error: {e}")),
            _ => {}
        }
        buf.clear();
    }

    if recorded_on.is_none() {
        recorded_on = Some(chrono::Local::now().date_naive());
    }

    // Pass 2: process athletes and their times
    buf.clear();
    let mut reader = Reader::from_reader(xml.as_slice());
    reader.config_mut().trim_text(true);
    in_club = false;
    in_athlete = false;
    current_club_code = String::new();
    current_club_name = String::new();

    #[derive(Default)]
    struct AthEntries {
        first: String,
        last: String,
        license: String,
        // (eventid, course, time_ms, date)
        times: Vec<(String, String, i32, Option<NaiveDate>)>,
    }
    let mut current_ath = AthEntries::default();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(XmlEvent::Eof) => break,
            Ok(XmlEvent::Start(ref e)) | Ok(XmlEvent::Empty(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                match tag.as_str() {
                    "CLUB" => {
                        in_club = true;
                        current_club_code = String::new();
                        current_club_name = String::new();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "code" => current_club_code = val,
                                "name" => current_club_name = val,
                                _ => {}
                            }
                        }
                    }
                    "ATHLETE" if in_club => {
                        in_athlete = true;
                        current_ath = AthEntries::default();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "firstname" => current_ath.first = val,
                                "lastname" => current_ath.last = val,
                                "license" => current_ath.license = val,
                                _ => {}
                            }
                        }
                    }
                    "ENTRY" if in_athlete => {
                        let mut eid = String::new();
                        let mut etime = String::new();
                        let mut ecourse = course.clone();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "eventid" => eid = val,
                                "entrytime" => etime = val,
                                "entrycourse" => {
                                    if val == "LCM" || val == "SCM" {
                                        ecourse = val;
                                    }
                                }
                                _ => {}
                            }
                        }
                        if let Some(ms) = lenex_time_to_ms(&etime) {
                            if !eid.is_empty() {
                                current_ath.times.push((eid, ecourse, ms, None));
                            }
                        }
                    }
                    "RESULT" if in_athlete => {
                        let mut eid = String::new();
                        let mut stime = String::new();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "eventid" => eid = val,
                                "swimtime" => stime = val,
                                _ => {}
                            }
                        }
                        if let Some(ms) = lenex_time_to_ms(&stime) {
                            if !eid.is_empty() {
                                current_ath.times.push((eid, course.clone(), ms, recorded_on));
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(XmlEvent::End(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                match tag.as_str() {
                    "ATHLETE" if in_athlete => {
                        // Process this athlete's times
                        let ath_id = find_athlete(pool, &current_ath.first, &current_ath.last, &current_ath.license).await;
                        if let Some(aid) = ath_id {
                            // Group by (eventid, course) and take best
                            let mut best_per_event: HashMap<(String, String), (i32, Option<NaiveDate>)> = HashMap::new();
                            for (eid, ec, ms, date) in &current_ath.times {
                                let key = (eid.clone(), ec.clone());
                                let entry = best_per_event.entry(key).or_insert((*ms, *date));
                                if *ms < entry.0 {
                                    *entry = (*ms, *date);
                                }
                            }
                            for ((eid, ec), (ms, date)) in &best_per_event {
                                if let Some(&uid) = event_style.get(eid) {
                                    let d = date.or(recorded_on);
                                    match upsert_best_time(pool, aid, uid, *ms, ec, source, d).await {
                                        Ok(true) => updated += 1,
                                        Ok(false) => {}
                                        Err(_) => {}
                                    }
                                }
                            }
                        } else {
                            skipped += 1;
                        }
                        in_athlete = false;
                    }
                    "CLUB" => in_club = false,
                    _ => {}
                }
            }
            Err(e) => return Err(format!("XML error: {e}")),
            _ => {}
        }
        buf.clear();
    }

    Ok(BestTimesResult {
        times_updated: updated,
        athletes_skipped: skipped,
        athletes_created: 0,
    })
}

async fn find_athlete(pool: &PgPool, first: &str, last: &str, license: &str) -> Option<i32> {
    if !license.is_empty() {
        let row: Option<(i32,)> = sqlx::query_as("SELECT id FROM athletes WHERE license = $1")
            .bind(license)
            .fetch_optional(pool)
            .await
            .ok()?;
        if let Some((id,)) = row {
            return Some(id);
        }
    }
    let row: Option<(i32,)> =
        sqlx::query_as("SELECT id FROM athletes WHERE first_name = $1 AND last_name = $2")
            .bind(first)
            .bind(last)
            .fetch_optional(pool)
            .await
            .ok()?;
    row.map(|(id,)| id)
}
