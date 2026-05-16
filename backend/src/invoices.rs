use serde::Serialize;
use sqlx::PgPool;
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize)]
pub struct LineItem {
    pub event_number: Option<i32>,
    pub event_name: String,
    pub description: String,
    pub qty: i32,
    pub unit_cents: i32,
}

pub async fn meet_fees(pool: &PgPool) -> HashMap<String, i32> {
    let row: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'meet_fees_json'")
            .fetch_optional(pool)
            .await
            .unwrap_or(None);
    match row {
        Some((Some(val),)) => serde_json::from_str(&val).unwrap_or_default(),
        _ => HashMap::new(),
    }
}

pub async fn meet_name(pool: &PgPool) -> String {
    let row: Option<(Option<String>,)> =
        sqlx::query_as("SELECT value FROM app_config WHERE key = 'meet_name'")
            .fetch_optional(pool)
            .await
            .unwrap_or(None);
    row.and_then(|r| r.0).unwrap_or_else(|| "Compétition".to_string())
}

pub async fn club_line_items(pool: &PgPool, club_id: i32, fees: &HashMap<String, i32>) -> Vec<LineItem> {
    // Per-event fees
    let rows: Vec<(i32, Option<i32>, Option<String>, Option<i32>, i32, String, String)> = sqlx::query_as(
        r#"SELECT e.id, e.event_number, e.style_name, e.fee_cents, e.relay_count, a.last_name, a.first_name
           FROM registrations r
           JOIN events e ON r.event_id = e.id
           JOIN athletes a ON r.athlete_id = a.id
           WHERE a.club_id = $1
           ORDER BY e.event_number, a.last_name"#,
    )
    .bind(club_id)
    .fetch_all(pool)
    .await
    .unwrap_or_default();

    let mut event_items: Vec<LineItem> = Vec::new();
    let mut relay_seen: HashMap<i32, usize> = HashMap::new();

    for row in &rows {
        let fee = row.3.unwrap_or(0);
        if fee <= 0 {
            continue;
        }
        if row.4 == 1 {
            // Individual
            event_items.push(LineItem {
                event_number: row.1,
                event_name: row.2.clone().unwrap_or_default(),
                description: format!("{}, {}", row.5.to_uppercase(), row.6),
                qty: 1,
                unit_cents: fee,
            });
        } else {
            // Relay: one line per event
            if !relay_seen.contains_key(&row.0) {
                let idx = event_items.len();
                relay_seen.insert(row.0, idx);
                event_items.push(LineItem {
                    event_number: row.1,
                    event_name: row.2.clone().unwrap_or_default(),
                    description: "Relais".to_string(),
                    qty: 1,
                    unit_cents: fee,
                });
            }
        }
    }

    // Meet-level fees
    let mut meet_items: Vec<LineItem> = Vec::new();
    if !fees.is_empty() {
        let athlete_count: (i64,) = sqlx::query_as(
            "SELECT COUNT(DISTINCT a.id) FROM athletes a JOIN registrations r ON r.athlete_id = a.id WHERE a.club_id = $1",
        )
        .bind(club_id)
        .fetch_one(pool)
        .await
        .unwrap_or((0,));

        let relay_count: (i64,) = sqlx::query_as(
            r#"SELECT COUNT(DISTINCT e.id) FROM events e
               JOIN registrations r ON r.event_id = e.id
               JOIN athletes a ON r.athlete_id = a.id
               WHERE a.club_id = $1 AND e.relay_count > 1"#,
        )
        .bind(club_id)
        .fetch_one(pool)
        .await
        .unwrap_or((0,));

        let qty_for: HashMap<&str, i32> = [
            ("CLUB", 1),
            ("ATHLETE", athlete_count.0 as i32),
            ("RELAY", relay_count.0 as i32),
            ("TEAM", 1),
            ("LATEFEE", 1),
            ("LSCMEETFEE", 1),
        ]
        .into_iter()
        .collect();

        let labels: HashMap<&str, &str> = [
            ("CLUB", "Frais de club"),
            ("ATHLETE", "Frais par athlète"),
            ("RELAY", "Frais par relais"),
            ("TEAM", "Frais d'équipe"),
            ("LATEFEE", "Inscription tardive"),
            ("LSCMEETFEE", "Frais LSC"),
        ]
        .into_iter()
        .collect();

        for (ftype, cents) in fees {
            if *cents <= 0 {
                continue;
            }
            let qty = qty_for.get(ftype.as_str()).copied().unwrap_or(1);
            if qty <= 0 {
                continue;
            }
            meet_items.push(LineItem {
                event_number: None,
                event_name: labels.get(ftype.as_str()).unwrap_or(&ftype.as_str()).to_string(),
                description: String::new(),
                qty,
                unit_cents: *cents,
            });
        }
    }

    meet_items.extend(event_items);
    meet_items
}

/// Stripe invoice creation via API (uses reqwest since there's no official Rust SDK)
pub async fn create_stripe_invoice(
    pool: &PgPool,
    club_id: i32,
    stripe_account: Option<&str>,
) -> Result<serde_json::Value, String> {
    let api_key = std::env::var("STRIPE_API_KEY").map_err(|_| "STRIPE_API_KEY not configured")?;
    let fees = meet_fees(pool).await;
    let items = club_line_items(pool, club_id, &fees).await;
    if items.is_empty() {
        return Err("No billable items for this club".to_string());
    }

    let club_name: Option<(String, Option<String>)> =
        sqlx::query_as("SELECT name, email FROM clubs WHERE id = $1")
            .bind(club_id)
            .fetch_optional(pool)
            .await
            .map_err(|e| e.to_string())?;
    let (name, email) = club_name.ok_or("Club not found")?;
    let mname = meet_name(pool).await;

    let client = reqwest::Client::new();
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert("Authorization", format!("Bearer {api_key}").parse().unwrap());
    if let Some(acct) = stripe_account {
        headers.insert("Stripe-Account", acct.parse().unwrap());
    }

    // Create customer
    let mut params = vec![("name", name.clone())];
    if let Some(ref e) = email {
        if !e.is_empty() {
            params.push(("email", e.clone()));
        }
    }
    let resp = client
        .post("https://api.stripe.com/v1/customers")
        .headers(headers.clone())
        .form(&params)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let customer: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let customer_id = customer["id"].as_str().ok_or("Failed to create customer")?;

    // Create invoice
    let invoice_params = vec![
        ("customer", customer_id.to_string()),
        ("auto_advance", "false".to_string()),
        ("currency", "cad".to_string()),
        ("collection_method", "send_invoice".to_string()),
        ("days_until_due", "30".to_string()),
        ("description", format!("{mname} — Inscriptions")),
        ("pending_invoice_items_behavior", "exclude".to_string()),
    ];
    let resp = client
        .post("https://api.stripe.com/v1/invoices")
        .headers(headers.clone())
        .form(&invoice_params)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let invoice: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let invoice_id = invoice["id"].as_str().ok_or("Failed to create invoice")?;

    // Add line items
    for it in &items {
        let desc = format!(
            "{}{}{}",
            it.event_number.map(|n| format!("#{n} — ")).unwrap_or_default(),
            it.event_name,
            if it.description.is_empty() { String::new() } else { format!(" — {}", it.description) }
        );
        let item_params = vec![
            ("customer", customer_id.to_string()),
            ("invoice", invoice_id.to_string()),
            ("currency", "cad".to_string()),
            ("amount", (it.unit_cents * it.qty).to_string()),
            ("description", desc),
        ];
        client
            .post("https://api.stripe.com/v1/invoiceitems")
            .headers(headers.clone())
            .form(&item_params)
            .send()
            .await
            .map_err(|e| e.to_string())?;
    }

    let total: i32 = items.iter().map(|it| it.unit_cents * it.qty).sum();
    Ok(serde_json::json!({
        "club": name,
        "invoice_id": invoice_id,
        "total_cents": total,
    }))
}
