#![allow(unused_imports, unused_variables, dead_code, unused_assignments, unused_mut)]

mod auth;
mod best_times;
mod db;
mod events;
mod export;
mod invoices;
mod meet_parser;
mod models;
mod routes;
mod seed;
mod state;

use std::net::SocketAddr;
use std::path::Path;
use std::sync::Arc;

use tower_http::cors::{Any, CorsLayer};
use tracing_subscriber::EnvFilter;

use crate::auth::RateLimiter;
use crate::state::AppState;

#[tokio::main]
async fn main() {
    dotenvy::dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive("info".parse().unwrap()))
        .init();

    // Validate SECRET_KEY
    let secret = std::env::var("SECRET_KEY").unwrap_or_else(|_| "change-me-to-a-random-string".to_string());
    if secret == "change-me-to-a-random-string" {
        eprintln!("ERROR: SECRET_KEY must be changed from the default value");
        std::process::exit(1);
    }

    let pool = db::create_pool().await;
    db::run_migrations(&pool).await;

    // Load events from stored meet if table is empty
    let meet_storage = std::env::var("MEET_STORAGE").unwrap_or_else(|_| "/app/data/meet.lxf".to_string());
    let meet_path = Path::new(&meet_storage);
    if meet_path.exists() {
        match events::load_events_if_empty(&pool, meet_path).await {
            Ok(count) if count > 0 => tracing::info!("Loaded {count} events from {meet_storage}"),
            Ok(_) => {}
            Err(e) => tracing::warn!("Failed to load events: {e}"),
        }
    }

    let cors_origin = std::env::var("APP_BASE_URL").unwrap_or_else(|_| "http://localhost:8001".to_string());
    let cors = CorsLayer::new()
        .allow_origin(cors_origin.parse::<axum::http::HeaderValue>().unwrap())
        .allow_methods(Any)
        .allow_headers(Any);

    let state = AppState {
        pool,
        rate_limiter: Arc::new(RateLimiter::new()),
    };

    let app = routes::api_router(state)
        .layer(cors)
        .into_make_service_with_connect_info::<SocketAddr>();

    let addr = SocketAddr::from(([0, 0, 0, 0], 8000));
    tracing::info!("Listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
