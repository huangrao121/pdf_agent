"""
Authentication Schema Usage Examples
=====================================

This file demonstrates how to use the authentication models for common use cases.
These are example snippets that show the intended usage patterns.

Note: These are illustrative examples, not executable test code.
Actual implementation would require async database session management.
"""

from datetime import datetime, timedelta
import hashlib
import secrets

# Example imports (in actual code)
# from database.models.model_user import UserModel
# from database.models.model_auth import (
#     OAuthIdentityModel,
#     PasswordCredentialModel, 
#     VerificationCodeModel,
#     VerificationCodeType,
# )


# ============================================================
# Example 1: Create User with Email/Password
# ============================================================
def example_register_with_password():
    """
    Register a new user with email and password.
    Steps:
    1. Create user profile
    2. Hash password and store in password_credentials
    3. Generate email verification code
    4. Send verification email (not shown)
    """
    # Create user
    user = UserModel(
        username="johndoe",
        email="john@example.com",
        full_name="John Doe",
        is_active=True,
        is_superuser=False,
    )
    # db.add(user)
    # await db.flush()  # Get user_id
    
    # Hash password (use bcrypt in production)
    password = "SecureP@ssw0rd"
    password_hash = hashlib.sha256(password.encode()).hexdigest()  # Use bcrypt!
    
    # Create password credential
    credential = PasswordCredentialModel(
        user_id=user.user_id,
        password_hash=password_hash,
        email_verified=False,  # Not verified yet
    )
    # db.add(credential)
    
    # Generate verification code
    verification_token = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(verification_token.encode()).hexdigest()
    
    verification_code = VerificationCodeModel(
        user_id=user.user_id,
        code_type=VerificationCodeType.EMAIL_VERIFICATION,
        code_hash=code_hash,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        used_at=None,
    )
    # db.add(verification_code)
    # await db.commit()
    
    # Send email with verification_token (not shown)
    print(f"User created: {user.username}")
    print(f"Verification token: {verification_token}")
    return user, verification_token


# ============================================================
# Example 2: Verify Email
# ============================================================
def example_verify_email():
    """
    Verify user email with token from email.
    Steps:
    1. Find verification code by hashed token
    2. Check expiration and usage
    3. Mark email as verified
    4. Mark code as used
    """
    received_token = "token_from_email_link"
    code_hash = hashlib.sha256(received_token.encode()).hexdigest()
    
    # Find verification code
    # verification_code = await db.query(VerificationCodeModel).filter(
    #     VerificationCodeModel.code_hash == code_hash,
    #     VerificationCodeModel.code_type == VerificationCodeType.EMAIL_VERIFICATION,
    #     VerificationCodeModel.used_at.is_(None),
    #     VerificationCodeModel.expires_at > datetime.utcnow(),
    # ).first()
    
    # if not verification_code:
    #     raise ValueError("Invalid or expired verification code")
    
    # Mark code as used
    # verification_code.used_at = datetime.utcnow()
    
    # Mark email as verified
    # credential = await db.query(PasswordCredentialModel).filter(
    #     PasswordCredentialModel.user_id == verification_code.user_id
    # ).first()
    # credential.email_verified = True
    # credential.email_verified_at = datetime.utcnow()
    # await db.commit()
    
    print("Email verified successfully")


# ============================================================
# Example 3: Login with Email/Password
# ============================================================
def example_login_with_password():
    """
    Authenticate user with email and password.
    Steps:
    1. Find user by email
    2. Verify password hash
    3. Check email verification status
    4. Issue session/JWT (not shown)
    """
    email = "john@example.com"
    password = "SecureP@ssw0rd"
    
    # Find user
    # user = await db.query(UserModel).filter(UserModel.email == email).first()
    # if not user:
    #     raise ValueError("Invalid credentials")
    
    # Verify password
    # credential = await db.query(PasswordCredentialModel).filter(
    #     PasswordCredentialModel.user_id == user.user_id
    # ).first()
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()  # Use bcrypt!
    # if credential.password_hash != password_hash:
    #     raise ValueError("Invalid credentials")
    
    # Check email verification
    # if not credential.email_verified:
    #     raise ValueError("Email not verified")
    
    # if not user.is_active:
    #     raise ValueError("Account is disabled")
    
    # Issue session/JWT
    print(f"Login successful: {email}")
    return "jwt_token_here"


# ============================================================
# Example 4: OAuth Login (Google)
# ============================================================
def example_oauth_login():
    """
    Login or register user via OAuth (e.g., Google).
    Steps:
    1. Receive OAuth callback with provider info
    2. Check if OAuth identity exists
    3. If yes: Login existing user
    4. If no: Create new user and OAuth identity
    """
    # OAuth callback data
    provider = "google"
    provider_subject = "1234567890"  # Google user ID
    provider_email = "john@gmail.com"
    provider_name = "John Doe"
    access_token = "oauth_access_token"
    refresh_token = "oauth_refresh_token"
    token_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Check if OAuth identity exists
    # oauth_identity = await db.query(OAuthIdentityModel).filter(
    #     OAuthIdentityModel.provider == provider,
    #     OAuthIdentityModel.provider_subject == provider_subject,
    # ).first()
    
    # if oauth_identity:
    #     # Existing user - login
    #     user = oauth_identity.user
    #     print(f"OAuth login: {user.username}")
    #     return user
    # else:
    #     # New user - register
    #     user = UserModel(
    #         username=provider_email.split('@')[0],  # Generate username
    #         email=provider_email,
    #         full_name=provider_name,
    #         is_active=True,
    #     )
    #     db.add(user)
    #     await db.flush()
    #     
    #     oauth_identity = OAuthIdentityModel(
    #         user_id=user.user_id,
    #         provider=provider,
    #         provider_subject=provider_subject,
    #         access_token=access_token,  # Should be encrypted
    #         refresh_token=refresh_token,  # Should be encrypted
    #         token_expires_at=token_expires_at,
    #         provider_email=provider_email,
    #         provider_name=provider_name,
    #     )
    #     db.add(oauth_identity)
    #     await db.commit()
    #     
    #     print(f"OAuth registration: {user.username}")
    #     return user


# ============================================================
# Example 5: Password Reset
# ============================================================
def example_password_reset():
    """
    Reset forgotten password.
    Steps:
    1. User requests reset
    2. Generate reset token
    3. Send reset email
    4. User submits new password + token
    5. Verify token and update password
    """
    email = "john@example.com"
    
    # Step 1-3: Request reset
    # user = await db.query(UserModel).filter(UserModel.email == email).first()
    # if not user:
    #     # Don't reveal if email exists (security)
    #     return
    
    reset_token = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(reset_token.encode()).hexdigest()
    
    verification_code = VerificationCodeModel(
        user_id="user.user_id",
        code_type=VerificationCodeType.PASSWORD_RESET,
        code_hash=code_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
        used_at=None,
    )
    # db.add(verification_code)
    # await db.commit()
    
    print(f"Password reset token: {reset_token}")
    
    # Step 4-5: Reset password
    received_token = reset_token
    new_password = "NewSecureP@ssw0rd"
    
    code_hash = hashlib.sha256(received_token.encode()).hexdigest()
    # verification_code = await db.query(VerificationCodeModel).filter(
    #     VerificationCodeModel.code_hash == code_hash,
    #     VerificationCodeModel.code_type == VerificationCodeType.PASSWORD_RESET,
    #     VerificationCodeModel.used_at.is_(None),
    #     VerificationCodeModel.expires_at > datetime.utcnow(),
    # ).first()
    
    # if not verification_code:
    #     raise ValueError("Invalid or expired reset token")
    
    # Update password
    new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()  # Use bcrypt!
    # credential = await db.query(PasswordCredentialModel).filter(
    #     PasswordCredentialModel.user_id == verification_code.user_id
    # ).first()
    # credential.password_hash = new_password_hash
    # credential.password_changed_at = datetime.utcnow()
    
    # Mark token as used
    # verification_code.used_at = datetime.utcnow()
    # await db.commit()
    
    print("Password reset successfully")


# ============================================================
# Example 6: Change Email
# ============================================================
def example_change_email():
    """
    Change user email address.
    Steps:
    1. User requests email change
    2. Generate verification code with new email in metadata
    3. Send verification email to NEW email
    4. User clicks link
    5. Verify token and update email
    """
    user_id = 123
    new_email = "newemail@example.com"
    
    # Generate verification code
    verification_token = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(verification_token.encode()).hexdigest()
    
    verification_code = VerificationCodeModel(
        user_id=user_id,
        code_type=VerificationCodeType.CHANGE_EMAIL,
        code_hash=code_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
        used_at=None,
        extra_data=f'{{"new_email": "{new_email}"}}',  # Store new email
    )
    # db.add(verification_code)
    # await db.commit()
    
    print(f"Email change token: {verification_token}")
    
    # Verify and update
    received_token = verification_token
    code_hash = hashlib.sha256(received_token.encode()).hexdigest()
    
    # verification_code = await db.query(VerificationCodeModel).filter(
    #     VerificationCodeModel.code_hash == code_hash,
    #     VerificationCodeModel.code_type == VerificationCodeType.CHANGE_EMAIL,
    #     VerificationCodeModel.used_at.is_(None),
    #     VerificationCodeModel.expires_at > datetime.utcnow(),
    # ).first()
    
    # import json
    # metadata = json.loads(verification_code.extra_data)
    # new_email = metadata['new_email']
    
    # Update user email
    # user = await db.query(UserModel).filter(
    #     UserModel.user_id == verification_code.user_id
    # ).first()
    # user.email = new_email
    
    # Mark token as used
    # verification_code.used_at = datetime.utcnow()
    # await db.commit()
    
    print(f"Email changed to: {new_email}")


# ============================================================
# Example 7: Bind OAuth to Existing Account
# ============================================================
def example_bind_oauth_provider():
    """
    Bind OAuth provider to existing user account.
    User already logged in with email/password, now wants to add Google login.
    """
    user_id = 123  # Currently logged in user
    
    # OAuth callback data
    provider = "github"
    provider_subject = "9876543210"
    access_token = "github_access_token"
    
    # Check if this OAuth identity is already bound
    # existing = await db.query(OAuthIdentityModel).filter(
    #     OAuthIdentityModel.provider == provider,
    #     OAuthIdentityModel.provider_subject == provider_subject,
    # ).first()
    
    # if existing:
    #     raise ValueError("This OAuth account is already linked")
    
    # Create new OAuth identity
    oauth_identity = OAuthIdentityModel(
        user_id=user_id,
        provider=provider,
        provider_subject=provider_subject,
        access_token=access_token,
        provider_email="john@github.com",
        provider_name="John Doe",
    )
    # db.add(oauth_identity)
    # await db.commit()
    
    print(f"OAuth provider {provider} bound to user {user_id}")


# ============================================================
# Example 8: Multiple Authentication Methods
# ============================================================
def example_user_with_multiple_auth_methods():
    """
    Example of a user with both password and multiple OAuth providers.
    This demonstrates the flexibility of the schema.
    """
    # User profile
    user = UserModel(
        user_id=123,
        username="johndoe",
        email="john@example.com",
        full_name="John Doe",
        is_active=True,
    )
    
    # Password credential
    password_cred = PasswordCredentialModel(
        user_id=123,
        password_hash="$2b$12$...",
        email_verified=True,
        email_verified_at=datetime.utcnow(),
    )
    
    # Multiple OAuth identities
    google_oauth = OAuthIdentityModel(
        user_id=123,
        provider="google",
        provider_subject="1234567890",
        provider_email="john@gmail.com",
    )
    
    github_oauth = OAuthIdentityModel(
        user_id=123,
        provider="github",
        provider_subject="9876543210",
        provider_email="john@github.com",
    )
    
    print(f"User {user.username} can login with:")
    print("  - Email/password")
    print("  - Google OAuth")
    print("  - GitHub OAuth")


if __name__ == "__main__":
    print("Authentication Schema Usage Examples")
    print("=" * 60)
    print()
    print("This file contains example code snippets.")
    print("See function docstrings for detailed explanations.")
    print()
    print("Available examples:")
    print("  1. Register with email/password")
    print("  2. Verify email")
    print("  3. Login with email/password")
    print("  4. OAuth login (Google)")
    print("  5. Password reset")
    print("  6. Change email")
    print("  7. Bind OAuth provider to existing account")
    print("  8. User with multiple authentication methods")
