# Authentication Schema Diagram

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USERS (Profile)                             │
│─────────────────────────────────────────────────────────────────────────│
│ PK  user_id          BIGINT                                             │
│     username         VARCHAR(150)  UNIQUE, NOT NULL                     │
│     email            VARCHAR(255)  UNIQUE, NULLABLE                     │
│     full_name        VARCHAR(255)  NULLABLE                             │
│     avatar_url       VARCHAR(512)  NULLABLE                             │
│     is_active        BOOLEAN       NOT NULL DEFAULT TRUE                │
│     is_superuser     BOOLEAN       NOT NULL DEFAULT FALSE               │
│     created_at       TIMESTAMP     NOT NULL                             │
│     updated_at       TIMESTAMP     NOT NULL                             │
│                                                                          │
│  NOTE: No authentication secrets stored here!                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    △
                                    │ (1:N)
                   ┌────────────────┼────────────────┐
                   │                │                │
                   │                │                │
        (1:N)      ▼                ▼       (1:1)   ▼
┌──────────────────────────┐ ┌──────────────────────────────┐
│  OAUTH_IDENTITIES        │ │  PASSWORD_CREDENTIALS        │
│──────────────────────────│ │──────────────────────────────│
│ PK  oauth_identity_id    │ │ PK  user_id (FK)             │
│ FK  user_id              │ │     email        UNIQUE      │
│     provider  (enum)     │ │     password_hash            │
│     provider_subject     │ │     email_verified           │
│     provider_email       │ │     email_verified_at        │
│     provider_name        │ │     last_password_change_at  │
│     access_token         │ │     created_at               │
│     refresh_token        │ │     updated_at               │
│     token_expires_at     │ │                              │
│     created_at           │ │  SECURITY:                   │
│     updated_at           │ │  • Hashed passwords only     │
│                          │ │  • 1:1 with users            │
│  UNIQUE (provider,       │ └──────────────────────────────┘
│          provider_subject│
│  )                       │
│                          │         (1:N)
│  SECURITY:               │           │
│  • Multiple OAuth per    │           ▼
│    user supported        │ ┌──────────────────────────────┐
│  • Tokens encrypted      │ │  VERIFICATION_CODES          │
│    at rest              │ │──────────────────────────────│
└──────────────────────────┘ │ PK  verification_code_id     │
                             │ FK  user_id                  │
                             │     code_type (enum)         │
                             │     code_hash                │
                             │     expires_at               │
                             │     used_at                  │
                             │     new_email (optional)     │
                             │     created_at               │
                             │                              │
                             │  SECURITY:                   │
                             │  • Hashed codes only         │
                             │  • Time-limited validity     │
                             │  • One-time use              │
                             └──────────────────────────────┘
```

## Table Relationships

### Users → OAuth Identities (1:N)
- One user can have multiple OAuth identities
- Each OAuth identity belongs to exactly one user
- Example: User links both Google and GitHub accounts

### Users → Password Credentials (1:1)
- One user can have at most one password credential
- Password credential belongs to exactly one user
- Optional: Users with OAuth-only don't have password credentials

### Users → Verification Codes (1:N)
- One user can have multiple verification codes
- Each code belongs to exactly one user
- Codes for different purposes (email verify, password reset, change email)

## Authentication Flow Diagrams

### OAuth Login Flow
```
User                OAuth Provider           Database
  │                      │                      │
  │──Register/Login──────────────────────────────▶│
  │                      │                      │
  │                      │◀─OAuth Redirect──────┤
  │─────────────────────▶│                      │
  │                      │                      │
  │◀─OAuth Callback──────┤                      │
  │                      │                      │
  │──────────────────────────Get/Create User────▶│
  │                      │                      │
  │                      │        ┌─────────────┤
  │                      │        │ users       │
  │                      │        │ oauth_      │
  │                      │        │ identities  │
  │◀─────────────────────────────┴─────────────┤
  │  Authenticated                              │
```

### Email/Password Registration Flow
```
User                 Server               Database
  │                    │                     │
  │──Register─────────▶│                     │
  │                    │──Create User────────▶│
  │                    │                     │ users
  │                    │──Create Password────▶│ password_credentials
  │                    │──Create Code────────▶│ verification_codes
  │◀─Verification Email┤                     │
  │                    │                     │
  │──Submit Code──────▶│                     │
  │                    │──Verify Code────────▶│
  │                    │──Mark Verified──────▶│
  │◀─Email Verified────┤                     │
```

### Password Reset Flow
```
User                 Server               Database
  │                    │                     │
  │──Forgot Password──▶│                     │
  │                    │──Find User──────────▶│
  │                    │──Create Code────────▶│ verification_codes
  │◀─Reset Email───────┤                     │
  │                    │                     │
  │──Submit Code──────▶│                     │
  │   + New Password   │                     │
  │                    │──Verify Code────────▶│
  │                    │──Update Password────▶│ password_credentials
  │                    │──Mark Used──────────▶│
  │◀─Password Reset────┤                     │
```

## Data Flow Examples

### Example 1: OAuth-Only User
```
INSERT INTO users (username, full_name, is_active)
VALUES ('john_doe', 'John Doe', TRUE);
-- Returns user_id = 1

INSERT INTO oauth_identities (
    user_id, provider, provider_subject, 
    provider_email, access_token
)
VALUES (
    1, 'google', 'google-user-123', 
    'john@example.com', 'encrypted_token'
);

-- Query user with OAuth info
SELECT u.*, o.provider, o.provider_email
FROM users u
JOIN oauth_identities o ON u.user_id = o.user_id
WHERE u.user_id = 1;
```

### Example 2: Email/Password User
```
INSERT INTO users (username, email, full_name, is_active)
VALUES ('jane_smith', 'jane@example.com', 'Jane Smith', TRUE);
-- Returns user_id = 2

INSERT INTO password_credentials (
    user_id, email, password_hash, email_verified
)
VALUES (
    2, 'jane@example.com', 
    '$2b$12$hashed_password_here', FALSE
);

INSERT INTO verification_codes (
    user_id, code_type, code_hash, expires_at
)
VALUES (
    2, 'email_verification',
    'sha256_hashed_code_here',
    NOW() + INTERVAL '24 hours'
);
```

### Example 3: User with Both OAuth and Password
```
-- User can have BOTH OAuth and password auth

-- First create user and OAuth identity
INSERT INTO users (username, email, full_name)
VALUES ('alice', 'alice@example.com', 'Alice Wonder');
-- user_id = 3

INSERT INTO oauth_identities (
    user_id, provider, provider_subject
)
VALUES (3, 'google', 'google-alice-456');

-- Later, user adds email/password
INSERT INTO password_credentials (
    user_id, email, password_hash, email_verified
)
VALUES (3, 'alice@example.com', '$2b$12$...', TRUE);

-- Now alice can login via:
-- 1. Google OAuth
-- 2. Email/password
```

## Index Strategy

### oauth_identities
```sql
-- Primary key index (automatic)
CREATE INDEX ON oauth_identities (oauth_identity_id);

-- Foreign key index for joins
CREATE INDEX ON oauth_identities (user_id);

-- Unique constraint for OAuth lookup
CREATE UNIQUE INDEX ON oauth_identities (provider, provider_subject);
```

### password_credentials
```sql
-- Primary key index (automatic)
CREATE INDEX ON password_credentials (user_id);

-- Email lookup for login
CREATE UNIQUE INDEX ON password_credentials (email);
```

### verification_codes
```sql
-- Primary key index (automatic)
CREATE INDEX ON verification_codes (verification_code_id);

-- Foreign key index
CREATE INDEX ON verification_codes (user_id);

-- Code verification lookup
CREATE UNIQUE INDEX ON verification_codes (code_hash);

-- Combined lookup for active codes
CREATE INDEX ON verification_codes (user_id, code_type);

-- Cleanup query optimization
CREATE INDEX ON verification_codes (expires_at);
```

## Cleanup Queries

### Delete Expired Codes
```sql
-- Run periodically (e.g., daily cron job)
DELETE FROM verification_codes
WHERE expires_at < NOW() 
  AND used_at IS NULL;
```

### Delete Used Codes After Retention Period
```sql
-- Keep used codes for audit (e.g., 30 days)
DELETE FROM verification_codes
WHERE used_at IS NOT NULL
  AND used_at < NOW() - INTERVAL '30 days';
```

## Summary

This schema design provides:

- ✅ **Separation of Concerns**: Profile data vs. authentication credentials
- ✅ **Flexibility**: Support for OAuth, password, or both
- ✅ **Security**: No plaintext secrets, proper hashing
- ✅ **Scalability**: Proper indexes, efficient queries
- ✅ **Extensibility**: Easy to add new OAuth providers or verification types
- ✅ **Best Practices**: Foreign keys, constraints, proper types
