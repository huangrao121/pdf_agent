-- Authentication Schema Migration
-- Creates tables for OAuth, password-based auth, and verification codes
-- 
-- This migration adds:
-- 1. oauth_identities - OAuth login credentials
-- 2. password_credentials - Email/password login credentials  
-- 3. verification_codes - Email verification, password reset, change email tokens
-- 4. Updates users table to add avatar_url field
--
-- Design principles:
-- - Users table stores only profile information (no auth secrets)
-- - OAuth and password auth are separate tables
-- - All sensitive data (passwords, tokens) stored as hashes only
-- - Proper foreign keys and indexes for performance

-- ============================================================================
-- OAuth Identities Table
-- ============================================================================
-- Stores OAuth login identities (Google, GitHub, etc.)
-- One user can have multiple OAuth identities linked

CREATE TABLE IF NOT EXISTS oauth_identities (
    oauth_identity_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- OAuth provider information
    provider VARCHAR(50) NOT NULL CHECK (provider IN ('google', 'github', 'microsoft', 'apple')),
    provider_subject VARCHAR(255) NOT NULL,  -- Unique user ID from provider
    provider_email VARCHAR(255),  -- Email from provider (may change)
    provider_name VARCHAR(255),  -- Display name from provider
    
    -- OAuth tokens (should be encrypted at rest in production)
    access_token TEXT,  -- OAuth access token
    refresh_token TEXT,  -- OAuth refresh token
    token_expires_at TIMESTAMP,  -- Access token expiry
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT idx_oauth_provider_subject UNIQUE (provider, provider_subject)
);

CREATE INDEX idx_oauth_identities_user_id ON oauth_identities(user_id);

-- ============================================================================
-- Password Credentials Table
-- ============================================================================
-- Stores email/password login credentials
-- One-to-one relationship with users table

CREATE TABLE IF NOT EXISTS password_credentials (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- Email for login
    email VARCHAR(255) NOT NULL UNIQUE,
    
    -- Password storage (ONLY hashed values - bcrypt/argon2)
    password_hash VARCHAR(255) NOT NULL,
    
    -- Email verification status
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMP,
    
    -- Password management
    last_password_change_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_password_credentials_email ON password_credentials(email);

-- ============================================================================
-- Verification Codes Table
-- ============================================================================
-- Unified table for all verification flows:
-- - Email verification (after registration)
-- - Password reset (forgot password)
-- - Change email (verify new email address)

CREATE TABLE IF NOT EXISTS verification_codes (
    verification_code_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- Verification code information
    code_type VARCHAR(50) NOT NULL CHECK (code_type IN ('email_verification', 'password_reset', 'change_email')),
    code_hash VARCHAR(255) NOT NULL UNIQUE,  -- Hashed code (SHA256)
    
    -- Expiration and usage tracking
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,  -- NULL = not used, set when code is consumed
    
    -- Additional data for specific code types
    new_email VARCHAR(255),  -- For CHANGE_EMAIL type: the new email being verified
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_verification_codes_user_id ON verification_codes(user_id);
CREATE INDEX idx_verification_codes_code_hash ON verification_codes(code_hash);
CREATE INDEX idx_verification_user_type ON verification_codes(user_id, code_type);
CREATE INDEX idx_verification_expires_at ON verification_codes(expires_at);

-- ============================================================================
-- Update Users Table
-- ============================================================================
-- Add avatar_url field to users table for profile pictures

ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512);

-- Update users table comments to reflect new design
COMMENT ON TABLE users IS 'User profile information only - authentication credentials stored in separate tables';
COMMENT ON COLUMN users.email IS 'Email for display purposes - can be NULL for OAuth-only users';
COMMENT ON COLUMN users.username IS 'Unique username - primary user identifier';

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE oauth_identities IS 'OAuth login identities - one user can have multiple OAuth providers linked';
COMMENT ON COLUMN oauth_identities.provider_subject IS 'Unique user identifier from OAuth provider (immutable)';
COMMENT ON COLUMN oauth_identities.access_token IS 'OAuth access token - should be encrypted at rest in production';

COMMENT ON TABLE password_credentials IS 'Email/password credentials - one-to-one with users table';
COMMENT ON COLUMN password_credentials.password_hash IS 'Hashed password using bcrypt or argon2 - NEVER store plaintext';
COMMENT ON COLUMN password_credentials.email IS 'Email used for login - duplicates users.email for auth purposes';

COMMENT ON TABLE verification_codes IS 'Unified verification codes for email verify, password reset, and change email flows';
COMMENT ON COLUMN verification_codes.code_hash IS 'Hashed verification code using SHA256 - NEVER store plaintext';
COMMENT ON COLUMN verification_codes.used_at IS 'Timestamp when code was consumed - NULL means not yet used';

-- ============================================================================
-- Example Usage Patterns
-- ============================================================================

-- Example 1: Create user with OAuth only (no email/password)
-- INSERT INTO users (username, full_name, is_active, is_superuser) 
-- VALUES ('john_doe', 'John Doe', TRUE, FALSE);
-- 
-- INSERT INTO oauth_identities (user_id, provider, provider_subject, provider_email, provider_name)
-- VALUES (1, 'google', 'google-user-123', 'john@example.com', 'John Doe');

-- Example 2: Create user with email/password
-- INSERT INTO users (username, email, full_name, is_active, is_superuser)
-- VALUES ('jane_smith', 'jane@example.com', 'Jane Smith', TRUE, FALSE);
--
-- INSERT INTO password_credentials (user_id, email, password_hash, email_verified)
-- VALUES (2, 'jane@example.com', '$2b$12$...hashed...', FALSE);
--
-- INSERT INTO verification_codes (user_id, code_type, code_hash, expires_at)
-- VALUES (2, 'email_verification', 'sha256-hash...', NOW() + INTERVAL '24 hours');

-- Example 3: Password reset flow
-- INSERT INTO verification_codes (user_id, code_type, code_hash, expires_at)
-- VALUES (2, 'password_reset', 'sha256-hash...', NOW() + INTERVAL '1 hour');

-- Example 4: Change email flow
-- INSERT INTO verification_codes (user_id, code_type, code_hash, expires_at, new_email)
-- VALUES (2, 'change_email', 'sha256-hash...', NOW() + INTERVAL '1 hour', 'newemail@example.com');

-- ============================================================================
-- Cleanup Query for Expired Codes
-- ============================================================================
-- Run periodically to clean up expired verification codes
-- DELETE FROM verification_codes WHERE expires_at < NOW() AND used_at IS NULL;
