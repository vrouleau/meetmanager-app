use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;

pub async fn create_pool() -> PgPool {
    let url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgres://meetmgr:meetmgr@localhost/meetmgr".to_string());
    PgPoolOptions::new()
        .max_connections(10)
        .connect(&url)
        .await
        .expect("Failed to connect to database")
}

pub async fn run_migrations(pool: &PgPool) {
    sqlx::raw_sql(
        r#"
        DO $$ BEGIN
            CREATE TYPE gender AS ENUM ('M', 'F');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;

        CREATE TABLE IF NOT EXISTS clubs (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            code VARCHAR(20) UNIQUE,
            nation VARCHAR(3),
            pin VARCHAR(6),
            email VARCHAR(200),
            stripe_account_id VARCHAR(100),
            invite_send_count INTEGER NOT NULL DEFAULT 0,
            stripe_send_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS athletes (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            gender gender NOT NULL,
            birthdate DATE,
            license VARCHAR(20),
            exception VARCHAR(1),
            club_id INTEGER NOT NULL REFERENCES clubs(id),
            UNIQUE(first_name, last_name, club_id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            splash_event_id INTEGER NOT NULL UNIQUE,
            style_uid INTEGER NOT NULL,
            style_name VARCHAR(100),
            distance INTEGER,
            relay_count INTEGER NOT NULL DEFAULT 1,
            gender INTEGER,
            event_number INTEGER,
            round INTEGER,
            masters BOOLEAN NOT NULL DEFAULT FALSE,
            fee_cents INTEGER NOT NULL DEFAULT 0,
            session_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS age_groups (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            splash_agegroup_id INTEGER NOT NULL,
            code TEXT NOT NULL DEFAULT '',
            age_min INTEGER NOT NULL,
            age_max INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id),
            event_id INTEGER NOT NULL REFERENCES events(id),
            age_code VARCHAR(10) NOT NULL DEFAULT 'OPEN',
            entry_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(athlete_id, event_id, age_code)
        );

        CREATE TABLE IF NOT EXISTS best_times (
            id SERIAL PRIMARY KEY,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id),
            style_uid INTEGER NOT NULL,
            time_ms INTEGER NOT NULL,
            course VARCHAR(3) NOT NULL DEFAULT 'LCM',
            source VARCHAR(100),
            recorded_on DATE,
            UNIQUE(athlete_id, style_uid, course)
        );

        CREATE TABLE IF NOT EXISTS secret_links (
            id SERIAL PRIMARY KEY,
            token VARCHAR(36) NOT NULL UNIQUE,
            club_id INTEGER NOT NULL REFERENCES clubs(id),
            pin_encrypted VARCHAR(200) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            viewed BOOLEAN NOT NULL DEFAULT FALSE,
            lang VARCHAR(2) DEFAULT 'fr',
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS app_config (
            key VARCHAR(50) PRIMARY KEY,
            value TEXT
        );
        "#,
    )
    .execute(pool)
    .await
    .expect("Failed to run migrations");
}
