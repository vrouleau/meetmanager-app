pub mod auth_routes;
pub mod clubs;
pub mod athletes;
pub mod events_routes;
pub mod registrations;
pub mod uploads;
pub mod exports;
pub mod admin;
pub mod invoices_routes;

use axum::Router;
use crate::state::AppState;

pub fn api_router(state: AppState) -> Router {
    Router::new()
        .merge(auth_routes::routes())
        .merge(clubs::routes())
        .merge(athletes::routes())
        .merge(events_routes::routes())
        .merge(registrations::routes())
        .merge(uploads::routes())
        .merge(exports::routes())
        .merge(admin::routes())
        .merge(invoices_routes::routes())
        .with_state(state)
}
