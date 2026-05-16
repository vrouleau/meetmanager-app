use chrono::NaiveDate;
use quick_xml::events::Event as XmlEvent;
use quick_xml::Reader;
use rand::Rng;
use serde::Serialize;
use sqlx::PgPool;

use crate::meet_parser::extract_lef_from_zip;

#[derive(Debug, Clone)]
struct ClubData {
    name: String,
    code: String,
    nation: String,
    email: String,
    athletes: Vec<AthleteData>,
}

#[derive(Debug, Clone)]
struct AthleteData {
    first_name: String,
    last_name: String,
    gender: String,
    birthdate: Option<NaiveDate>,
    license: String,
    exception: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct SeedResult {
    pub clubs_added: i32,
    pub athletes_added: i32,
}

fn parse_lxf(data: &[u8]) -> Result<Vec<ClubData>, String> {
    let xml = extract_lef_from_zip(data)?;
    parse_clubs_xml(&xml)
}

fn parse_clubs_xml(xml: &[u8]) -> Result<Vec<ClubData>, String> {
    let mut reader = Reader::from_reader(xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut clubs: Vec<ClubData> = Vec::new();
    let mut current_club: Option<ClubData> = None;
    let mut in_meet = false;
    let mut in_clubs = false;
    let mut in_club = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(XmlEvent::Eof) => break,
            Ok(XmlEvent::Start(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_uppercase();
                match tag.as_str() {
                    "MEET" => in_meet = true,
                    "CLUBS" if in_meet => in_clubs = true,
                    "CLUB" if in_clubs => {
                        in_club = true;
                        let mut club = ClubData { name: String::new(), code: String::new(), nation: String::new(), email: String::new(), athletes: Vec::new() };
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_lowercase();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "name" => club.name = val,
                                "code" => club.code = val,
                                "nation" => club.nation = val,
                                _ => {}
                            }
                        }
                        current_club = Some(club);
                    }
                    "ATHLETE" if in_club => {
                        if let Some(ath) = parse_athlete_attrs(e) {
                            if let Some(ref mut club) = current_club {
                                club.athletes.push(ath);
                            }
                        }
                    }
                    "CONTACT" if in_club => {
                        if let Some(ref mut club) = current_club {
                            for attr in e.attributes().flatten() {
                                let key = String::from_utf8_lossy(attr.key.as_ref()).to_lowercase();
                                let val = String::from_utf8_lossy(&attr.value).to_string();
                                if key == "email" || key == "e-mail" {
                                    club.email = val;
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(XmlEvent::Empty(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_uppercase();
                match tag.as_str() {
                    "CLUB" if in_clubs => {
                        let mut club = ClubData { name: String::new(), code: String::new(), nation: String::new(), email: String::new(), athletes: Vec::new() };
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_lowercase();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "name" => club.name = val,
                                "code" => club.code = val,
                                "nation" => club.nation = val,
                                _ => {}
                            }
                        }
                        clubs.push(club);
                    }
                    "ATHLETE" if in_club => {
                        if let Some(ath) = parse_athlete_attrs(e) {
                            if let Some(ref mut club) = current_club {
                                club.athletes.push(ath);
                            }
                        }
                    }
                    "CONTACT" if in_club => {
                        if let Some(ref mut club) = current_club {
                            for attr in e.attributes().flatten() {
                                let key = String::from_utf8_lossy(attr.key.as_ref()).to_lowercase();
                                let val = String::from_utf8_lossy(&attr.value).to_string();
                                if key == "email" || key == "e-mail" {
                                    club.email = val;
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(XmlEvent::End(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_uppercase();
                match tag.as_str() {
                    "CLUB" if in_club => {
                        if let Some(club) = current_club.take() {
                            clubs.push(club);
                        }
                        in_club = false;
                    }
                    "CLUBS" => in_clubs = false,
                    "MEET" => in_meet = false,
                    _ => {}
                }
            }
            Err(e) => return Err(format!("XML parse error: {e}")),
            _ => {}
        }
        buf.clear();
    }
    Ok(clubs)
}

fn parse_athlete_attrs(e: &quick_xml::events::BytesStart) -> Option<AthleteData> {
    let mut ath = AthleteData {
        first_name: String::new(),
        last_name: String::new(),
        gender: "M".to_string(),
        birthdate: None,
        license: String::new(),
        exception: None,
    };
    for attr in e.attributes().flatten() {
        let key = String::from_utf8_lossy(attr.key.as_ref()).to_lowercase();
        let val = String::from_utf8_lossy(&attr.value).to_string();
        match key.as_str() {
            "firstname" => ath.first_name = val.trim().trim_end_matches(',').to_string(),
            "lastname" => ath.last_name = val.trim().trim_end_matches(',').to_string(),
            "gender" => ath.gender = val,
            "birthdate" => ath.birthdate = NaiveDate::parse_from_str(&val, "%Y-%m-%d").ok(),
            "license" => ath.license = val,
            "exception" => ath.exception = Some(val),
            _ => {}
        }
    }
    Some(ath)
}

pub async fn seed_from_lxf(pool: &PgPool, data: &[u8]) -> Result<SeedResult, String> {
    let clubs_data = parse_lxf(data)?;
    let mut clubs_added = 0;
    let mut athletes_added = 0;

    for cd in &clubs_data {
        let club_id: i32 = if !cd.code.is_empty() {
            let row: Option<(i32,)> = sqlx::query_as("SELECT id FROM clubs WHERE code = $1")
                .bind(&cd.code)
                .fetch_optional(pool)
                .await
                .map_err(|e| e.to_string())?;
            match row {
                Some((id,)) => {
                    // Update existing
                    sqlx::query("UPDATE clubs SET nation = COALESCE(NULLIF($1, ''), nation) WHERE id = $2")
                        .bind(&cd.nation)
                        .bind(id)
                        .execute(pool)
                        .await
                        .map_err(|e| e.to_string())?;
                    if !cd.email.is_empty() {
                        sqlx::query("UPDATE clubs SET email = COALESCE(email, $1) WHERE id = $2")
                            .bind(&cd.email)
                            .bind(id)
                            .execute(pool)
                            .await
                            .map_err(|e| e.to_string())?;
                    }
                    id
                }
                None => {
                    let pin = generate_pin();
                    let email: Option<&str> = if cd.email.is_empty() { None } else { Some(&cd.email) };
                    let row: (i32,) = sqlx::query_as(
                        "INSERT INTO clubs (name, code, nation, pin, email) VALUES ($1, $2, $3, $4, $5) RETURNING id"
                    )
                    .bind(&cd.name)
                    .bind(&cd.code)
                    .bind(&cd.nation)
                    .bind(&pin)
                    .bind(email)
                    .fetch_one(pool)
                    .await
                    .map_err(|e| e.to_string())?;
                    clubs_added += 1;
                    row.0
                }
            }
        } else {
            let row: Option<(i32,)> = sqlx::query_as("SELECT id FROM clubs WHERE name = $1")
                .bind(&cd.name)
                .fetch_optional(pool)
                .await
                .map_err(|e| e.to_string())?;
            match row {
                Some((id,)) => id,
                None => {
                    let pin = generate_pin();
                    let row: (i32,) = sqlx::query_as(
                        "INSERT INTO clubs (name, code, nation, pin) VALUES ($1, $2, $3, $4) RETURNING id"
                    )
                    .bind(&cd.name)
                    .bind(&cd.code)
                    .bind(&cd.nation)
                    .bind(&pin)
                    .fetch_one(pool)
                    .await
                    .map_err(|e| e.to_string())?;
                    clubs_added += 1;
                    row.0
                }
            }
        };

        for ad in &cd.athletes {
            let exists: Option<(i32,)> = sqlx::query_as(
                "SELECT id FROM athletes WHERE first_name = $1 AND last_name = $2 AND club_id = $3"
            )
            .bind(&ad.first_name)
            .bind(&ad.last_name)
            .bind(club_id)
            .fetch_optional(pool)
            .await
            .map_err(|e| e.to_string())?;

            if exists.is_none() {
                let gender = if ad.gender == "F" { "F" } else { "M" };
                sqlx::query(
                    "INSERT INTO athletes (first_name, last_name, gender, birthdate, license, exception, club_id) VALUES ($1, $2, $3::gender, $4, $5, $6, $7)"
                )
                .bind(&ad.first_name)
                .bind(&ad.last_name)
                .bind(gender)
                .bind(ad.birthdate)
                .bind(&ad.license)
                .bind(&ad.exception)
                .bind(club_id)
                .execute(pool)
                .await
                .map_err(|e| e.to_string())?;
                athletes_added += 1;
            }
        }
    }

    Ok(SeedResult {
        clubs_added,
        athletes_added,
    })
}

fn generate_pin() -> String {
    let mut rng = rand::thread_rng();
    (0..6).map(|_| rng.gen_range(0..10).to_string()).collect()
}
