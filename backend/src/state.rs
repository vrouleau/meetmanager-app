use sqlx::PgPool;
use std::sync::Arc;

use crate::auth::RateLimiter;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub rate_limiter: Arc<RateLimiter>,
}
