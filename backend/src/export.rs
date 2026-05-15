use quick_xml::events::{BytesDecl, BytesEnd, BytesStart, BytesText, Event as XmlEvent};
use quick_xml::Writer;
use sqlx::PgPool;
use std::io::Cursor;
use zip::write::SimpleFileOptions;
use zip::ZipWriter;

use crate::meet_parser::{parse_meet_lxf, ParsedMeet};

fn ms_to_lenex(ms: Option<i32>) -> String {
    match ms {
        None | Some(0) => "NT".to_string(),
        Some(ms) => {
            let h = ms / 3600000;
            let m = (ms % 3600000) / 60000;
            let s = (ms % 60000) / 1000;
            let cs = (ms % 1000) / 10;
            format!("{h:02}:{m:02}:{s:02}.{cs:02}")
        }
    }
}

pub async fn generate_lxf(pool: &PgPool) -> Result<Vec<u8>, String> {
    let meet_storage =
        std::env::var("MEET_STORAGE").unwrap_or_else(|_| "/app/data/meet.lxf".to_string());
    let meet_data = std::fs::read(&meet_storage).map_err(|e| format!("Cannot read meet file: {e}"))?;
    let meet = parse_meet_lxf(&meet_data)?;

    // Fetch registrations with joins
    let rows: Vec<(i32, i32, String, Option<i32>, i32, String, String, String, Option<chrono::NaiveDate>, Option<String>, Option<String>, i32, i32, Option<String>, Option<String>, Option<i32>)> = sqlx::query_as(
        r#"SELECT r.id, r.athlete_id, r.age_code, r.entry_time_ms,
                  a.id, a.first_name, a.last_name, a.gender::text, a.birthdate, a.license, a.exception,
                  a.club_id, c.id, c.name, c.code, e.splash_event_id
           FROM registrations r
           JOIN athletes a ON r.athlete_id = a.id
           JOIN clubs c ON a.club_id = c.id
           JOIN events e ON r.event_id = e.id
           ORDER BY c.name, a.last_name, a.first_name"#,
    )
    .fetch_all(pool)
    .await
    .map_err(|e| e.to_string())?;

    // Group by club -> athlete -> entries
    use std::collections::BTreeMap;
    struct EntryData {
        splash_event_id: i32,
        age_code: String,
        entry_time_ms: Option<i32>,
    }
    struct AthData {
        id: i32,
        first_name: String,
        last_name: String,
        gender: String,
        birthdate: Option<chrono::NaiveDate>,
        license: Option<String>,
        exception: Option<String>,
        entries: Vec<EntryData>,
    }
    struct ClubEntries {
        name: String,
        code: Option<String>,
        athletes: BTreeMap<i32, AthData>,
    }

    let mut clubs: BTreeMap<i32, ClubEntries> = BTreeMap::new();
    for row in &rows {
        let club_id = row.11;
        let club = clubs.entry(club_id).or_insert_with(|| ClubEntries {
            name: row.13.clone().unwrap_or_default(),
            code: row.14.clone(),
            athletes: BTreeMap::new(),
        });
        let ath = club.athletes.entry(row.4).or_insert_with(|| AthData {
            id: row.4,
            first_name: row.5.clone(),
            last_name: row.6.clone(),
            gender: row.7.clone(),
            birthdate: row.8,
            license: row.9.clone(),
            exception: row.10.clone(),
            entries: Vec::new(),
        });
        if let Some(splash_eid) = row.15 {
            ath.entries.push(EntryData {
                splash_event_id: splash_eid,
                age_code: row.2.clone(),
                entry_time_ms: row.3,
            });
        }
    }

    // Build XML
    let mut writer = Writer::new(Cursor::new(Vec::new()));
    writer.write_event(XmlEvent::Decl(BytesDecl::new("1.0", Some("UTF-8"), None))).map_err(|e| e.to_string())?;

    let mut lenex = BytesStart::new("LENEX");
    lenex.push_attribute(("version", "3.0"));
    writer.write_event(XmlEvent::Start(lenex)).map_err(|e| e.to_string())?;

    writer.write_event(XmlEvent::Start(BytesStart::new("MEETS"))).map_err(|e| e.to_string())?;
    let mut meet_el = BytesStart::new("MEET");
    meet_el.push_attribute(("name", meet.meet_name.as_str()));
    meet_el.push_attribute(("course", meet.course.as_str()));
    writer.write_event(XmlEvent::Start(meet_el)).map_err(|e| e.to_string())?;

    // Sessions from meet structure
    writer.write_event(XmlEvent::Start(BytesStart::new("SESSIONS"))).map_err(|e| e.to_string())?;
    for ses in &meet.sessions {
        let mut ses_el = BytesStart::new("SESSION");
        ses_el.push_attribute(("number", ses.number.to_string().as_str()));
        ses_el.push_attribute(("course", meet.course.as_str()));
        writer.write_event(XmlEvent::Start(ses_el)).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::Start(BytesStart::new("EVENTS"))).map_err(|e| e.to_string())?;
        for ev in &ses.events {
            let mut ev_el = BytesStart::new("EVENT");
            ev_el.push_attribute(("eventid", ev.eventid.to_string().as_str()));
            ev_el.push_attribute(("number", ev.number.to_string().as_str()));
            ev_el.push_attribute(("gender", ev.gender.as_str()));
            ev_el.push_attribute(("round", ev.round.as_str()));
            writer.write_event(XmlEvent::Start(ev_el)).map_err(|e| e.to_string())?;
            let mut ss = BytesStart::new("SWIMSTYLE");
            ss.push_attribute(("distance", ev.distance.to_string().as_str()));
            ss.push_attribute(("relaycount", ev.relaycount.to_string().as_str()));
            ss.push_attribute(("stroke", "UNKNOWN"));
            writer.write_event(XmlEvent::Empty(ss)).map_err(|e| e.to_string())?;
            writer.write_event(XmlEvent::End(BytesEnd::new("EVENT"))).map_err(|e| e.to_string())?;
        }
        writer.write_event(XmlEvent::End(BytesEnd::new("EVENTS"))).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::End(BytesEnd::new("SESSION"))).map_err(|e| e.to_string())?;
    }
    writer.write_event(XmlEvent::End(BytesEnd::new("SESSIONS"))).map_err(|e| e.to_string())?;

    // Clubs
    writer.write_event(XmlEvent::Start(BytesStart::new("CLUBS"))).map_err(|e| e.to_string())?;
    for (club_id, club_data) in &clubs {
        let mut club_el = BytesStart::new("CLUB");
        club_el.push_attribute(("name", club_data.name.as_str()));
        club_el.push_attribute(("code", club_data.code.as_deref().unwrap_or("")));
        club_el.push_attribute(("nation", "CAN"));
        club_el.push_attribute(("clubid", club_id.to_string().as_str()));
        writer.write_event(XmlEvent::Start(club_el)).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::Start(BytesStart::new("ATHLETES"))).map_err(|e| e.to_string())?;

        for ath in club_data.athletes.values() {
            let mut ath_el = BytesStart::new("ATHLETE");
            ath_el.push_attribute(("athleteid", ath.id.to_string().as_str()));
            ath_el.push_attribute(("firstname", ath.first_name.as_str()));
            ath_el.push_attribute(("lastname", ath.last_name.as_str()));
            ath_el.push_attribute(("gender", ath.gender.as_str()));
            ath_el.push_attribute(("birthdate", ath.birthdate.map(|d| d.to_string()).unwrap_or_default().as_str()));
            ath_el.push_attribute(("license", ath.license.as_deref().unwrap_or("")));
            writer.write_event(XmlEvent::Start(ath_el)).map_err(|e| e.to_string())?;

            writer.write_event(XmlEvent::Start(BytesStart::new("ENTRIES"))).map_err(|e| e.to_string())?;
            for entry in &ath.entries {
                let mut entry_el = BytesStart::new("ENTRY");
                entry_el.push_attribute(("eventid", entry.splash_event_id.to_string().as_str()));
                entry_el.push_attribute(("entrycourse", meet.course.as_str()));
                if let Some(ms) = entry.entry_time_ms {
                    entry_el.push_attribute(("entrytime", ms_to_lenex(Some(ms)).as_str()));
                }
                writer.write_event(XmlEvent::Empty(entry_el)).map_err(|e| e.to_string())?;
            }
            writer.write_event(XmlEvent::End(BytesEnd::new("ENTRIES"))).map_err(|e| e.to_string())?;
            writer.write_event(XmlEvent::End(BytesEnd::new("ATHLETE"))).map_err(|e| e.to_string())?;
        }

        writer.write_event(XmlEvent::End(BytesEnd::new("ATHLETES"))).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::End(BytesEnd::new("CLUB"))).map_err(|e| e.to_string())?;
    }
    writer.write_event(XmlEvent::End(BytesEnd::new("CLUBS"))).map_err(|e| e.to_string())?;

    writer.write_event(XmlEvent::End(BytesEnd::new("MEET"))).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::End(BytesEnd::new("MEETS"))).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::End(BytesEnd::new("LENEX"))).map_err(|e| e.to_string())?;

    let xml_bytes = writer.into_inner().into_inner();

    // Wrap in zip
    let mut zip_buf = Cursor::new(Vec::new());
    {
        let mut zip = ZipWriter::new(&mut zip_buf);
        zip.start_file("meet.lef", SimpleFileOptions::default())
            .map_err(|e| e.to_string())?;
        std::io::Write::write_all(&mut zip, &xml_bytes).map_err(|e| e.to_string())?;
        zip.finish().map_err(|e| e.to_string())?;
    }
    Ok(zip_buf.into_inner())
}

pub async fn generate_entries_lxf(pool: &PgPool) -> Result<Vec<u8>, String> {
    let rows: Vec<(i32, String, String, String, Option<chrono::NaiveDate>, Option<String>, Option<String>, i32, String, Option<String>)> = sqlx::query_as(
        r#"SELECT a.id, a.first_name, a.last_name, a.gender::text, a.birthdate, a.license, a.exception,
                  a.club_id, c.name, c.code
           FROM athletes a JOIN clubs c ON a.club_id = c.id
           ORDER BY c.name, a.last_name"#,
    )
    .fetch_all(pool)
    .await
    .map_err(|e| e.to_string())?;

    let best_times: Vec<(i32, i32, i32, String, Option<chrono::NaiveDate>)> = sqlx::query_as(
        "SELECT athlete_id, style_uid, time_ms, course, recorded_on FROM best_times",
    )
    .fetch_all(pool)
    .await
    .map_err(|e| e.to_string())?;

    // Build XML
    let mut writer = Writer::new(Cursor::new(Vec::new()));
    writer.write_event(XmlEvent::Decl(BytesDecl::new("1.0", Some("UTF-8"), None))).map_err(|e| e.to_string())?;

    let mut lenex = BytesStart::new("LENEX");
    lenex.push_attribute(("version", "3.0"));
    writer.write_event(XmlEvent::Start(lenex)).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::Start(BytesStart::new("MEETS"))).map_err(|e| e.to_string())?;

    let mut meet_el = BytesStart::new("MEET");
    meet_el.push_attribute(("name", "Entries Export"));
    meet_el.push_attribute(("course", "LCM"));
    writer.write_event(XmlEvent::Start(meet_el)).map_err(|e| e.to_string())?;

    writer.write_event(XmlEvent::Start(BytesStart::new("CLUBS"))).map_err(|e| e.to_string())?;

    // Group athletes by club
    use std::collections::BTreeMap;
    let mut clubs_map: BTreeMap<i32, (String, Option<String>, Vec<usize>)> = BTreeMap::new();
    for (i, row) in rows.iter().enumerate() {
        let entry = clubs_map.entry(row.7).or_insert_with(|| (row.8.clone(), row.9.clone(), Vec::new()));
        entry.2.push(i);
    }

    // Index best times by athlete
    let mut bt_map: std::collections::HashMap<i32, Vec<&(i32, i32, i32, String, Option<chrono::NaiveDate>)>> = std::collections::HashMap::new();
    for bt in &best_times {
        bt_map.entry(bt.0).or_default().push(bt);
    }

    for (_club_id, (club_name, club_code, indices)) in &clubs_map {
        let mut club_el = BytesStart::new("CLUB");
        club_el.push_attribute(("name", club_name.as_str()));
        club_el.push_attribute(("code", club_code.as_deref().unwrap_or("")));
        writer.write_event(XmlEvent::Start(club_el)).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::Start(BytesStart::new("ATHLETES"))).map_err(|e| e.to_string())?;

        for &idx in indices {
            let row = &rows[idx];
            let mut ath_el = BytesStart::new("ATHLETE");
            ath_el.push_attribute(("athleteid", row.0.to_string().as_str()));
            ath_el.push_attribute(("firstname", row.1.as_str()));
            ath_el.push_attribute(("lastname", row.2.as_str()));
            ath_el.push_attribute(("gender", row.3.as_str()));
            ath_el.push_attribute(("birthdate", row.4.map(|d| d.to_string()).unwrap_or_default().as_str()));
            ath_el.push_attribute(("license", row.5.as_deref().unwrap_or("")));
            writer.write_event(XmlEvent::Start(ath_el)).map_err(|e| e.to_string())?;

            if let Some(bts) = bt_map.get(&row.0) {
                writer.write_event(XmlEvent::Start(BytesStart::new("ENTRIES"))).map_err(|e| e.to_string())?;
                for bt in bts {
                    let mut entry_el = BytesStart::new("ENTRY");
                    entry_el.push_attribute(("eventid", bt.1.to_string().as_str()));
                    entry_el.push_attribute(("entrycourse", bt.3.as_str()));
                    entry_el.push_attribute(("entrytime", ms_to_lenex(Some(bt.2)).as_str()));
                    writer.write_event(XmlEvent::Empty(entry_el)).map_err(|e| e.to_string())?;
                }
                writer.write_event(XmlEvent::End(BytesEnd::new("ENTRIES"))).map_err(|e| e.to_string())?;
            }

            writer.write_event(XmlEvent::End(BytesEnd::new("ATHLETE"))).map_err(|e| e.to_string())?;
        }

        writer.write_event(XmlEvent::End(BytesEnd::new("ATHLETES"))).map_err(|e| e.to_string())?;
        writer.write_event(XmlEvent::End(BytesEnd::new("CLUB"))).map_err(|e| e.to_string())?;
    }

    writer.write_event(XmlEvent::End(BytesEnd::new("CLUBS"))).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::End(BytesEnd::new("MEET"))).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::End(BytesEnd::new("MEETS"))).map_err(|e| e.to_string())?;
    writer.write_event(XmlEvent::End(BytesEnd::new("LENEX"))).map_err(|e| e.to_string())?;

    let xml_bytes = writer.into_inner().into_inner();

    let mut zip_buf = Cursor::new(Vec::new());
    {
        let mut zip = ZipWriter::new(&mut zip_buf);
        zip.start_file("entries.lef", SimpleFileOptions::default())
            .map_err(|e| e.to_string())?;
        std::io::Write::write_all(&mut zip, &xml_bytes).map_err(|e| e.to_string())?;
        zip.finish().map_err(|e| e.to_string())?;
    }
    Ok(zip_buf.into_inner())
}
