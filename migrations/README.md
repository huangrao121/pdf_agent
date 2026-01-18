# Authentication Schema Documentation

## Overview

This migration introduces a clean and extensible authentication system with separation of concerns:

1. **users** table - User profile information only (no auth secrets)
2. **oauth_identities** - Third-party OAuth login identities
3. **password_credentials** - Email/password authentication
4. **verification_codes** - Unified verification token system

## Design Principles

### Security First
- **Never store plaintext passwords**: Only bcrypt/argon2 hashes in `password_credentials`
- **Never store plaintext tokens**: Verification codes are hashed with SHA256
- **Time-limited tokens**: All verification codes have expiration timestamps
- **Single-use tokens**: Track usage via `used_at` timestamp

### Separation of Concerns
- User profile data is completely separate from authentication credentials
- Multiple authentication methods can coexist for the same user
- Each auth method has its dedicated table with appropriate constraints

### Extensibility
- Easy to add new OAuth providers (just add rows)
- Easy to add new verification types (just add enum values)
- Metadata fields allow storing additional context without schema changes

## Table Details

### users (existing - no changes)
Already clean! Contains only:
- `user_id` - Primary key
- `username` - Unique username
- `email` - Unique email (optional)
- `full_name` - Display name
- `is_active` - Account status
- `is_superuser` - Admin flag

### oauth_identities

Stores OAuth provider identities for third-party login.

**Key Design Points:**
- A user can have multiple OAuth identities (Google + GitHub)
- `(provider, provider_subject)` is unique - prevents duplicate bindings
- OAuth tokens are optional (stored encrypted for API access)
- Cascades on user deletion

**Example Row:**
```
user_id: 123
provider: 'google'
provider_subject: '1234567890'
provider_email: 'user@gmail.com'
```

**Supported Authentication Flows:**
- OAuth-only user (no password)
- Binding additional OAuth providers to existing account
- Unbinding OAuth providers

### password_credentials

Stores hashed passwords for email/password authentication.

**Key Design Points:**
- One-to-one relationship with users (user_id is PK)
- Only stores password hashes (bcrypt/argon2)
- Tracks email verification status
- Records password change history

**Example Row:**
```
user_id: 123
password_hash: '$2b$12$...' (bcrypt hash)
email_verified: true
email_verified_at: '2026-01-15 10:30:00'
```

**Supported Authentication Flows:**
- Email/password registration
- Email/password login
- Password change
- Email verification

### verification_codes

Unified table for all verification/reset tokens.

**Key Design Points:**
- Supports multiple verification types via `code_type` enum:
  - `email_verification` - Verify new user email
  - `password_reset` - Reset forgotten password
  - `change_email` - Verify new email address
- Codes are hashed with SHA256 (never stored plaintext)
- Time-limited via `expires_at` (typically 15-30 minutes)
- Single-use via `used_at` timestamp
- Metadata field for additional context (e.g., new email address)

**Example Rows:**
```
# Email verification for new user
user_id: 123
code_type: 'email_verification'
code_hash: 'sha256_hash_of_random_token'
expires_at: '2026-01-18 10:00:00'
used_at: NULL

# Password reset
user_id: 456
code_type: 'password_reset'
code_hash: 'sha256_hash_of_random_token'
expires_at: '2026-01-18 10:30:00'
used_at: '2026-01-18 10:15:00'

# Email change request
user_id: 789
code_type: 'change_email'
code_hash: 'sha256_hash_of_random_token'
expires_at: '2026-01-18 11:00:00'
used_at: NULL
metadata: '{"new_email": "newemail@example.com"}'
```

**Supported Authentication Flows:**
- Email verification after registration
- Password reset via email
- Email address change verification

## Supported Authentication Flows

### 1. Email/Password Registration
1. Create user in `users` table
2. Create password hash in `password_credentials` (email_verified=false)
3. Generate verification code in `verification_codes` (type=email_verification)
4. Send verification email with token
5. User clicks link, mark code as used, update email_verified=true

### 2. Email/Password Login
1. Look up user by email in `users`
2. Fetch password_hash from `password_credentials`
3. Verify password against hash
4. Check email_verified flag
5. Issue session/JWT

### 3. OAuth Registration/Login
1. Receive OAuth callback with provider_subject
2. Look up in `oauth_identities` by (provider, provider_subject)
3. If exists: Log in existing user
4. If not: Create user in `users` + create entry in `oauth_identities`

### 4. Password Reset
1. User requests reset via email
2. Generate code in `verification_codes` (type=password_reset)
3. Send reset email with token
4. User submits new password + token
5. Verify token, update password_hash, mark code as used

### 5. Email Change
1. User requests email change
2. Generate code in `verification_codes` (type=change_email, metadata=new_email)
3. Send verification email to NEW email
4. User clicks link
5. Verify token, update email in `users`, mark code as used

### 6. Bind OAuth Provider
1. User is logged in with email/password
2. User initiates OAuth flow for GitHub
3. Receive OAuth callback
4. Create new entry in `oauth_identities` linking to existing user_id

## Indexes and Performance

### oauth_identities
- `idx_oauth_user_id` - Fast lookup of all OAuth identities for a user
- `idx_oauth_provider_subject` (unique) - Fast OAuth login lookup

### verification_codes
- `idx_verification_user_id` - Fast lookup of codes for a user
- `idx_verification_user_type_used` - Fast lookup of unused codes by type
- `idx_verification_expires_at` - Efficient cleanup of expired codes

## Security Considerations

### Password Storage
- Use bcrypt (work factor 12+) or argon2id
- Never log or display password hashes
- Force password change on suspicious activity

### Token Generation
- Use cryptographically secure random generators (secrets.token_urlsafe)
- Tokens should be at least 32 bytes (256 bits)
- Hash tokens before storage using SHA256

### Token Expiration
- Email verification: 24-48 hours
- Password reset: 15-30 minutes
- Email change: 15-30 minutes

### Cleanup Strategy
- Regularly delete expired verification codes (e.g., daily cron job)
- Consider soft-deleting users instead of hard-deleting (keep audit trail)

## Migration Strategy

### Fresh Installation
Run `001_authentication_schema.sql` to create all tables.

### Existing Installation
If users table already exists:
1. Backup database
2. Run migration (will skip existing tables with IF NOT EXISTS)
3. Test all authentication flows
4. Monitor for issues

### Rollback
To rollback this migration:
```sql
DROP TABLE IF EXISTS verification_codes;
DROP TABLE IF EXISTS password_credentials;
DROP TABLE IF EXISTS oauth_identities;
```

## Future Enhancements

Potential additions (out of current scope):
- Multi-factor authentication (TOTP/SMS)
- Security questions
- Login history/audit log
- Rate limiting table
- OAuth token refresh logic
- Account recovery questions

## Testing Checklist

- [ ] Create user with OAuth only (no password)
- [ ] Create user with password only (no OAuth)
- [ ] Create user with both OAuth and password
- [ ] Bind multiple OAuth providers to same user
- [ ] Generate email verification code
- [ ] Generate password reset code
- [ ] Generate email change code
- [ ] Verify expired codes are rejected
- [ ] Verify used codes cannot be reused
- [ ] Test unique constraint on (provider, provider_subject)
- [ ] Test cascade deletion when user is deleted
- [ ] Run migrations on clean database
- [ ] Verify all indexes are created
- [ ] Check table comments are applied
