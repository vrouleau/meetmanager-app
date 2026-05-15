use chrono::{NaiveDate, NaiveDateTime};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, sqlx::Type)]
#[sqlx(type_name = "gender", rename_all = "UPPERCASE")]
pub enum Gender {
    M,
    F,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct Club {
    pub id: i32,
    pub name: String,
    pub code: Option<String>,
    pub nation: Option<String>,
    pub pin: Option<String>,
    pub admin_email: Option<String>,
    pub stripe_account_id: Option<String>,
    pub invite_send_count: i32,
    pub stripe_send_count: i32,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct Athlete {
    pub id: i32,
    pub first_name: String,
    pub last_name: String,
    pub gender: Gender,
    pub birthdate: Option<NaiveDate>,
    pub license: Option<String>,
    pub exception: Option<String>,
    pub club_id: i32,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct Event {
    pub id: i32,
    pub splash_event_id: i32,
    pub style_uid: i32,
    pub style_name: Option<String>,
    pub distance: Option<i32>,
    pub relay_count: i32,
    pub gender: Option<i32>,
    pub event_number: Option<i32>,
    pub round: Option<i32>,
    pub masters: bool,
    pub fee_cents: i32,
    pub session_id: Option<i32>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct AgeGroup {
    pub id: i32,
    pub event_id: i32,
    pub splash_agegroup_id: i32,
    pub age_min: i32,
    pub age_max: i32,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct Registration {
    pub id: i32,
    pub athlete_id: i32,
    pub event_id: i32,
    pub age_code: String,
    pub entry_time_ms: Option<i32>,
    pub created_at: Option<NaiveDateTime>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct BestTime {
    pub id: i32,
    pub athlete_id: i32,
    pub style_uid: i32,
    pub time_ms: i32,
    pub course: String,
    pub source: Option<String>,
    pub recorded_on: Option<NaiveDate>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct SecretLink {
    pub id: i32,
    pub token: String,
    pub club_id: i32,
    pub pin_encrypted: String,
    pub expires_at: NaiveDateTime,
    pub viewed: bool,
    pub lang: Option<String>,
    pub created_at: Option<NaiveDateTime>,
}

#[derive(Debug, Clone, FromRow, Serialize)]
pub struct AppConfig {
    pub key: String,
    pub value: Option<String>,
}
