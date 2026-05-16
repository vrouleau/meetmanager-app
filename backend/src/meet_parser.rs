use quick_xml::events::Event as XmlEvent;
use quick_xml::Reader;
use std::collections::HashMap;
use std::io::Read;
use zip::ZipArchive;

#[derive(Debug, Clone)]
pub struct MeetAgeGroup {
    pub agegroupid: i32,
    pub agemin: i32,
    pub agemax: i32,
}

#[derive(Debug, Clone)]
pub struct MeetEvent {
    pub eventid: i32,
    pub number: i32,
    pub gender: String,
    pub round: String,
    pub event_type: String,
    pub swimstyleid: i32,
    pub distance: i32,
    pub relaycount: i32,
    pub style_name: String,
    pub fee_cents: i32,
    pub agegroups: Vec<MeetAgeGroup>,
}

impl MeetEvent {
    pub fn is_masters(&self) -> bool {
        self.event_type == "MASTERS"
    }

    pub fn is_prelim(&self) -> bool {
        self.round == "PRE"
    }

    pub fn gender_int(&self) -> i32 {
        match self.gender.as_str() {
            "M" => 1,
            "F" => 2,
            "X" => 3,
            _ => 0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct MeetSession {
    pub number: i32,
    pub name: String,
    pub events: Vec<MeetEvent>,
}

#[derive(Debug, Clone, Default)]
pub struct ParsedMeet {
    pub meet_name: String,
    pub course: String,
    pub masters: bool,
    pub currency: String,
    pub age_base_date: String,
    pub meet_fees: HashMap<String, i32>,
    pub sessions: Vec<MeetSession>,
}

impl ParsedMeet {
    pub fn all_events(&self) -> Vec<&MeetEvent> {
        self.sessions.iter().flat_map(|s| s.events.iter()).collect()
    }
}

pub fn parse_meet_lxf(data: &[u8]) -> Result<ParsedMeet, String> {
    let xml_bytes = extract_lef_from_zip(data)?;
    parse_meet_xml(&xml_bytes)
}

pub fn extract_lef_from_zip(data: &[u8]) -> Result<Vec<u8>, String> {
    let cursor = std::io::Cursor::new(data);
    let mut archive = ZipArchive::new(cursor).map_err(|e| format!("Invalid zip: {e}"))?;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| format!("Zip error: {e}"))?;
        if file.name().ends_with(".lef") {
            let mut buf = Vec::new();
            file.read_to_end(&mut buf)
                .map_err(|e| format!("Read error: {e}"))?;
            return Ok(buf);
        }
    }
    Err("No .lef file found in archive".to_string())
}

fn parse_meet_xml(xml: &[u8]) -> Result<ParsedMeet, String> {
    let mut reader = Reader::from_reader(xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut meet = ParsedMeet::default();

    // State tracking
    let mut in_session = false;
    let mut in_event = false;
    let mut in_fees = false;
    let mut current_session = MeetSession {
        number: 0,
        name: String::new(),
        events: Vec::new(),
    };
    let mut current_event = new_event();

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
                                "name" => meet.meet_name = val,
                                "course" => meet.course = val,
                                "masters" => meet.masters = val.to_uppercase() == "T",
                                _ => {}
                            }
                        }
                    }
                    "AGEDATE" => {
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            if key == "value" {
                                meet.age_base_date = val;
                            }
                        }
                    }
                    "FEES" => in_fees = true,
                    "FEE" => {
                        let mut ftype = String::new();
                        let mut fval = 0i32;
                        let mut fcur = String::new();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "type" => ftype = val.to_uppercase(),
                                "value" => fval = val.parse().unwrap_or(0),
                                "currency" => fcur = val,
                                _ => {}
                            }
                        }
                        if !ftype.is_empty() {
                            meet.meet_fees.insert(ftype, fval);
                        }
                        if !fcur.is_empty() && meet.currency.is_empty() {
                            meet.currency = fcur;
                        }
                    }
                    "SESSION" => {
                        in_session = true;
                        current_session = MeetSession {
                            number: 0,
                            name: String::new(),
                            events: Vec::new(),
                        };
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "number" => {
                                    current_session.number = val.parse().unwrap_or(0)
                                }
                                "name" => current_session.name = val,
                                _ => {}
                            }
                        }
                    }
                    "EVENT" if in_session => {
                        in_event = true;
                        current_event = new_event();
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "eventid" => {
                                    current_event.eventid = val.parse().unwrap_or(0)
                                }
                                "number" => {
                                    current_event.number = val.parse().unwrap_or(0)
                                }
                                "gender" => current_event.gender = val,
                                "round" => current_event.round = val,
                                "type" => current_event.event_type = val,
                                _ => {}
                            }
                        }
                    }
                    "SWIMSTYLE" if in_event => {
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "swimstyleid" => {
                                    current_event.swimstyleid = val.parse().unwrap_or(0)
                                }
                                "distance" => {
                                    current_event.distance = val.parse().unwrap_or(0)
                                }
                                "relaycount" => {
                                    current_event.relaycount = val.parse().unwrap_or(1)
                                }
                                "name" => current_event.style_name = val,
                                _ => {}
                            }
                        }
                    }
                    "AGEGROUP" if in_event => {
                        let mut ag = MeetAgeGroup {
                            agegroupid: 0,
                            agemin: -1,
                            agemax: -1,
                        };
                        for attr in e.attributes().flatten() {
                            let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                            let val = String::from_utf8_lossy(&attr.value).to_string();
                            match key.as_str() {
                                "agegroupid" => ag.agegroupid = val.parse().unwrap_or(0),
                                "agemin" => ag.agemin = val.parse().unwrap_or(-1),
                                "agemax" => ag.agemax = val.parse().unwrap_or(-1),
                                _ => {}
                            }
                        }
                        current_event.agegroups.push(ag);
                    }
                    _ => {}
                }
                // Handle FEE inside EVENT (event-level fee)
                if tag == "FEE" && in_event {
                    for attr in e.attributes().flatten() {
                        let key = String::from_utf8_lossy(attr.key.as_ref()).to_string();
                        let val = String::from_utf8_lossy(&attr.value).to_string();
                        if key == "value" {
                            current_event.fee_cents = val.parse().unwrap_or(0);
                        }
                    }
                }
            }
            Ok(XmlEvent::End(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).to_string();
                match tag.as_str() {
                    "EVENT" if in_event => {
                        current_session.events.push(current_event.clone());
                        in_event = false;
                    }
                    "SESSION" if in_session => {
                        meet.sessions.push(current_session.clone());
                        in_session = false;
                    }
                    "FEES" => in_fees = false,
                    _ => {}
                }
            }
            Err(e) => return Err(format!("XML parse error: {e}")),
            _ => {}
        }
        buf.clear();
    }
    Ok(meet)
}

fn new_event() -> MeetEvent {
    MeetEvent {
        eventid: 0,
        number: 0,
        gender: String::new(),
        round: "TIM".to_string(),
        event_type: String::new(),
        swimstyleid: 0,
        distance: 0,
        relaycount: 1,
        style_name: String::new(),
        fee_cents: 0,
        agegroups: Vec::new(),
    }
}
