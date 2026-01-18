-- Authentication Schema Migration
-- Created: 2026-01-18
-- Purpose: Add authentication-related tables for OAuth, password credentials, and verification codes

-- ============================================================
-- Table: oauth_identities
-- Purpose: Store OAuth provider identities for third-party login
-- ============================================================
CREATE TABLE IF NOT EXISTS oauth_identities (
    oauth_identity_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    
    -- OAuth Provider Information
    provider VARCHAR(50) NOT NULL,  -- e.g., 'google', 'github', 'microsoft'
    provider_subject VARCHAR(255) NOT NULL,  -- OAuth provider's unique user identifier (sub field)
    
    -- OAuth Tokens (encrypted/hashed)
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    
    -- OAuth User Info (from provider)
    provider_email VARCHAR(255),
    provider_name VARCHAR(255),
    provider_avatar TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT fk_oauth_user 
        FOREIGN KEY (user_id) 
        REFERENCES users(user_id) 
        ON DELETE CASCADE,
    CONSTRAINT uq_oauth_provider_subject 
        UNIQUE (provider, provider_subject)
);

-- Indexes for oauth_identities
CREATE INDEX IF NOT EXISTS idx_oauth_user_id ON oauth_identities(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_provider_subject ON oauth_identities(provider, provider_subject);

-- ============================================================
-- Table: password_credentials
-- Purpose: Store hashed passwords for email/password authentication
-- ============================================================
CREATE TABLE IF NOT EXISTS password_credentials (
    user_id BIGINT PRIMARY KEY,
    
    -- Password Information (hashed with bcrypt/argon2)
    password_hash VARCHAR(255) NOT NULL,
    
    -- Email Verification
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMP,
    
    -- Password Change Tracking
    password_changed_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT fk_password_user 
        FOREIGN KEY (user_id) 
        REFERENCES users(user_id) 
        ON DELETE CASCADE
);

-- ============================================================
-- Table: verification_codes
-- Purpose: Unified table for verification tokens (email verify, password reset, change email)
-- ============================================================
CREATE TABLE IF NOT EXISTS verification_codes (
    verification_code_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    
    -- Verification Code Information
    code_type VARCHAR(50) NOT NULL,  -- 'email_verification', 'password_reset', 'change_email'
    code_hash VARCHAR(255) NOT NULL,  -- Hashed verification code (using SHA256)
    
    -- Validity and Usage
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    
    -- Additional Information (JSON format)
    metadata TEXT,  -- e.g., {"new_email": "new@example.com"} for change_email
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT fk_verification_user 
        FOREIGN KEY (user_id) 
        REFERENCES users(user_id) 
        ON DELETE CASCADE,
    CONSTRAINT chk_code_type 
        CHECK (code_type IN ('email_verification', 'password_reset', 'change_email'))
);

-- Indexes for verification_codes
CREATE INDEX IF NOT EXISTS idx_verification_user_id ON verification_codes(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_user_type_used ON verification_codes(user_id, code_type, used_at);
CREATE INDEX IF NOT EXISTS idx_verification_expires_at ON verification_codes(expires_at);

-- ============================================================
-- Comments for Documentation
-- ============================================================
COMMENT ON TABLE oauth_identities IS 'OAuth provider identities for third-party authentication (Google, GitHub, etc.)';
COMMENT ON COLUMN oauth_identities.provider IS 'OAuth provider name (google, github, microsoft, etc.)';
COMMENT ON COLUMN oauth_identities.provider_subject IS 'OAuth provider unique user identifier (sub field from OAuth token)';
COMMENT ON COLUMN oauth_identities.access_token IS 'Encrypted OAuth access token for API access';
COMMENT ON COLUMN oauth_identities.refresh_token IS 'Encrypted OAuth refresh token';

COMMENT ON TABLE password_credentials IS 'Email/password authentication credentials (one-to-one with users)';
COMMENT ON COLUMN password_credentials.password_hash IS 'Hashed password using bcrypt or argon2 - NEVER store plaintext passwords';
COMMENT ON COLUMN password_credentials.email_verified IS 'Whether the user email has been verified';

COMMENT ON TABLE verification_codes IS 'Unified verification token table for email verification, password reset, and email change';
COMMENT ON COLUMN verification_codes.code_type IS 'Type of verification: email_verification, password_reset, or change_email';
COMMENT ON COLUMN verification_codes.code_hash IS 'Hashed verification code using SHA256 - NEVER store plaintext codes';
COMMENT ON COLUMN verification_codes.expires_at IS 'Expiration timestamp (typically 15-30 minutes from creation)';
COMMENT ON COLUMN verification_codes.used_at IS 'Timestamp when code was used (NULL if unused)';
COMMENT ON COLUMN verification_codes.metadata IS 'Additional information in JSON format (e.g., new email for change_email type)';
