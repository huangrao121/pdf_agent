# Authentication Database Schema

This document describes the authentication database schema designed for flexible user authentication supporting both OAuth and email/password login methods.

## Overview

The authentication system separates user profile information from authentication credentials, providing a clean and extensible design:

- **users** - User profile information only (no auth secrets)
- **oauth_identities** - OAuth login credentials (Google, GitHub, etc.)
- **password_credentials** - Email/password authentication
- **verification_codes** - Unified table for email verification, password reset, and change email flows

## Schema Design

### 1. Users Table (Profile Only)

The `users` table stores **only user profile information**, with no authentication secrets:

```python
class UserModel(Base, TimestampMixin):
    user_id: int (PK)
    username: str (unique, not null)  # Primary identifier
    email: str (unique, nullable)      # Optional - OAuth users may not have email
    full_name: str (nullable)
    avatar_url: str (nullable)
    is_active: bool (default=True)
    is_superuser: bool (default=False)
    created_at: datetime
    updated_at: datetime
```

**Key Points:**
- No passwords or OAuth tokens stored here
- `email` is optional (OAuth users might not provide email)
- `username` is the primary unique identifier
- Supports both OAuth-only and email/password users

### 2. OAuth Identities Table

The `oauth_identities` table manages OAuth login credentials:

```python
class OAuthIdentityModel(Base, TimestampMixin):
    oauth_identity_id: int (PK)
    user_id: int (FK -> users.user_id)
    provider: str (google, github, microsoft, apple)
    provider_subject: str  # Unique ID from OAuth provider
    provider_email: str (nullable)
    provider_name: str (nullable)
    access_token: str (nullable, should be encrypted)
    refresh_token: str (nullable, should be encrypted)
    token_expires_at: datetime (nullable)
    created_at: datetime
    updated_at: datetime
    
    UNIQUE(provider, provider_subject)
```

**Key Points:**
- One user can have multiple OAuth identities (link Google + GitHub)
- `(provider, provider_subject)` is unique - one OAuth account = one identity
- `provider_subject` is immutable (the OAuth provider's user ID)
- Access/refresh tokens should be encrypted at rest in production
- Supports linking multiple OAuth providers to one account

### 3. Password Credentials Table

The `password_credentials` table manages email/password authentication:

```python
class PasswordCredentialModel(Base, TimestampMixin):
    user_id: int (PK, FK -> users.user_id)  # 1:1 relationship
    email: str (unique, not null)
    password_hash: str (not null)  # Hashed with bcrypt/argon2
    email_verified: bool (default=False)
    email_verified_at: datetime (nullable)
    last_password_change_at: datetime (default=now)
    created_at: datetime
    updated_at: datetime
```

**Key Points:**
- One-to-one relationship with users table
- **ONLY stores hashed passwords** (bcrypt or argon2)
- **NEVER store plaintext passwords**
- Tracks email verification status
- Tracks password change history

### 4. Verification Codes Table

The `verification_codes` table provides a unified approach for all verification flows:

```python
class VerificationCodeModel(Base, CreatedMixin):
    verification_code_id: int (PK)
    user_id: int (FK -> users.user_id)
    code_type: str (email_verification, password_reset, change_email)
    code_hash: str (unique, not null)  # Hashed with SHA256
    expires_at: datetime (not null)
    used_at: datetime (nullable)  # NULL = not used
    new_email: str (nullable)  # For change_email flow only
    created_at: datetime
```

**Key Points:**
- **ONLY stores hashed codes** (SHA256)
- **NEVER store plaintext verification codes**
- Unified table for multiple verification purposes
- Time-limited validity via `expires_at`
- One-time use tracked via `used_at`
- `new_email` field used only for email change flow

## Supported Authentication Flows

### 1. OAuth-Only User Registration

```python
# Create user profile
user = UserModel(username="john_doe", full_name="John Doe")

# Create OAuth identity
oauth_identity = OAuthIdentityModel(
    user_id=user.user_id,
    provider="google",
    provider_subject="google-user-123",
    provider_email="john@example.com"
)
```

### 2. Email/Password User Registration

```python
# Create user profile
user = UserModel(
    username="jane_smith",
    email="jane@example.com",
    full_name="Jane Smith"
)

# Create password credential (with hashed password)
password_cred = PasswordCredentialModel(
    user_id=user.user_id,
    email="jane@example.com",
    password_hash=bcrypt.hashpw(password, bcrypt.gensalt()),
    email_verified=False
)

# Create email verification code
verification = VerificationCodeModel(
    user_id=user.user_id,
    code_type="email_verification",
    code_hash=hashlib.sha256(code.encode()).hexdigest(),
    expires_at=datetime.now() + timedelta(hours=24)
)
```

### 3. Email Verification

```python
# Find verification code (by hashed value)
code_hash = hashlib.sha256(user_provided_code.encode()).hexdigest()
verification = session.query(VerificationCodeModel).filter(
    VerificationCodeModel.code_hash == code_hash,
    VerificationCodeModel.code_type == "email_verification",
    VerificationCodeModel.used_at.is_(None),
    VerificationCodeModel.expires_at > datetime.now()
).first()

if verification:
    # Mark as used
    verification.used_at = datetime.now()
    
    # Update password credential
    password_cred.email_verified = True
    password_cred.email_verified_at = datetime.now()
```

### 4. Password Reset

```python
# Create reset code
reset_code = VerificationCodeModel(
    user_id=user.user_id,
    code_type="password_reset",
    code_hash=hashlib.sha256(code.encode()).hexdigest(),
    expires_at=datetime.now() + timedelta(hours=1)
)

# When user resets password:
# 1. Verify code (same as email verification)
# 2. Update password
password_cred.password_hash = new_hashed_password
password_cred.last_password_change_at = datetime.now()
# 3. Mark code as used
verification.used_at = datetime.now()
```

### 5. Change Email

```python
# Create change email verification
verification = VerificationCodeModel(
    user_id=user.user_id,
    code_type="change_email",
    code_hash=hashlib.sha256(code.encode()).hexdigest(),
    expires_at=datetime.now() + timedelta(hours=1),
    new_email="newemail@example.com"
)

# When user verifies new email:
# 1. Verify code
# 2. Update email in both tables
user.email = verification.new_email
password_cred.email = verification.new_email
password_cred.email_verified = True
password_cred.email_verified_at = datetime.now()
# 3. Mark code as used
verification.used_at = datetime.now()
```

## Security Considerations

### Password Hashing
- **Always** use bcrypt or argon2 for password hashing
- **Never** store plaintext passwords
- Example with bcrypt:
  ```python
  import bcrypt
  password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
  ```

### Verification Code Hashing
- **Always** hash verification codes before storing
- **Never** store plaintext codes
- Example with SHA256:
  ```python
  import hashlib
  code_hash = hashlib.sha256(code.encode()).hexdigest()
  ```

### Token Encryption
- OAuth access/refresh tokens should be encrypted at rest in production
- Consider using application-level encryption or database-level encryption
- Rotate tokens regularly

### Expiration and Cleanup
- Set appropriate expiration times:
  - Email verification: 24 hours
  - Password reset: 1 hour
  - Change email: 1 hour
- Clean up expired codes periodically:
  ```sql
  DELETE FROM verification_codes 
  WHERE expires_at < NOW() AND used_at IS NULL;
  ```

## Indexes

The schema includes indexes for optimal query performance:

### oauth_identities
- `idx_oauth_provider_subject` (UNIQUE on provider, provider_subject)
- `idx_oauth_identities_user_id` (on user_id)

### password_credentials
- `idx_password_credentials_email` (on email)

### verification_codes
- `idx_verification_codes_user_id` (on user_id)
- `idx_verification_codes_code_hash` (on code_hash)
- `idx_verification_user_type` (on user_id, code_type)
- `idx_verification_expires_at` (on expires_at)

## Foreign Key Constraints

All foreign keys use `ON DELETE CASCADE` to maintain referential integrity:

- `oauth_identities.user_id` -> `users.user_id`
- `password_credentials.user_id` -> `users.user_id`
- `verification_codes.user_id` -> `users.user_id`

When a user is deleted, all related authentication data is automatically removed.

## Migration

To apply the schema, run the SQL migration:

```bash
psql -U username -d database_name -f config/database/migrations/001_auth_schema.sql
```

Or use SQLAlchemy to create tables:

```python
from database.models import Base
from database.init_database import _engine

async with _engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

## Testing

The schema supports all required test scenarios:

1. ✅ Create user with OAuth only
2. ✅ Create user with email/password only
3. ✅ Link multiple OAuth providers to one user
4. ✅ Generate verification codes (hashed with expiry)
5. ✅ Support multiple active tokens of different types
6. ✅ One-time use verification codes
7. ✅ Email verification flow
8. ✅ Password reset flow
9. ✅ Change email flow

## Tech Stack

- **SQLAlchemy 2.0+** - ORM and schema definition
- **Python 3.13** - Language version
- **PostgreSQL** - Recommended database (schema is portable)

## Future Enhancements

Potential extensions to the schema:

1. **Multi-factor Authentication (MFA)**
   - Add `mfa_settings` table for TOTP/SMS
   - Add `backup_codes` table

2. **Session Management**
   - Add `user_sessions` table for active sessions
   - Track device/location information

3. **Audit Log**
   - Add `auth_audit_log` table
   - Track login attempts, password changes, etc.

4. **Social Profile Data**
   - Extend `oauth_identities` to cache more provider data
   - Add JSON field for raw OAuth profile

5. **Password History**
   - Add `password_history` table
   - Prevent password reuse
