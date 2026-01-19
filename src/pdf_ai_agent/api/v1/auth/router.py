"""
Authentication API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import os

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.config.database.models.model_user import UserModel
from pdf_ai_agent.security.password import hash_password
from pdf_ai_agent.security.token_operations import TokenOperations
from pdf_ai_agent.security.key_manager import KeyManager
from pdf_ai_agent.api.v1.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    ErrorResponse,
    ErrorDetail,
)
from pdf_ai_agent.api.utils import generate_request_id
from pdf_ai_agent.api.rate_limit import limiter

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


def get_token_operations() -> TokenOperations:
    """
    Get TokenOperations instance configured with environment variables.
    For production, these should be loaded from secure configuration.
    """
    # Load JWT configuration from environment
    # These are placeholder values - in production, load from secure config
    private_key_pem = os.getenv("JWT_PRIVATE_KEY", "")
    public_key_pem = os.getenv("JWT_PUBLIC_KEY", "")
    active_kid = os.getenv("JWT_KID", "default-key-1")
    issuer = os.getenv("JWT_ISSUER", "pdf-agent-api")
    audience = os.getenv("JWT_AUDIENCE", "pdf-agent-users")
    
    # In production, these should be loaded from secure configuration
    if not private_key_pem or not public_key_pem:
        # For development/testing only - generate temporary keys
        # WARNING: Do not use in production!
        import logging
        logging.warning("JWT keys not found in environment - generating temporary keys for development only")
        
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()
        
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    key_manager = KeyManager(
        active_kid=active_kid,
        private_key_pem=private_key_pem,
        keyset={active_kid: public_key_pem}
    )
    
    return TokenOperations(
        key_manager=key_manager,
        issuer=issuer,
        audience=audience,
        leeway=0
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    responses={
        201: {"description": "User registered successfully"},
        422: {"description": "Validation failed", "model": ErrorResponse},
        409: {"description": "Email or username already exists", "model": ErrorResponse},
        429: {"description": "Too many requests", "model": ErrorResponse},
        403: {"description": "Registration forbidden", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    }
)
@limiter.limit("5/minute")  # Rate limit: 5 registrations per minute per IP
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
    token_ops: TokenOperations = Depends(get_token_operations),
):
    """
    Register a new user account.
    
    Creates a new user with the provided credentials and returns a JWT token.
    
    **Rate Limiting**: 5 requests per minute per IP address.
    
    **Validation Rules**:
    - Email: valid format, max 254 chars, lowercase/trimmed
    - Username: 3-30 chars, only letters/numbers/dots/underscores
    - Password: 8-72 chars, must contain at least 1 letter and 1 number
    - Full name: 1-100 chars, trimmed
    
    **Error Codes**:
    - `VALIDATION_FAILED`: Input validation failed
    - `EMAIL_TAKEN`: Email already registered
    - `USERNAME_TAKEN`: Username already taken
    - `RATE_LIMITED`: Too many registration attempts
    - `REGISTRATION_FORBIDDEN`: Registration is disabled or forbidden
    - `INTERNAL_ERROR`: Unexpected server error
    """
    request_id = generate_request_id()
    
    try:
        # Check if email already exists
        email_check = await db.execute(
            select(UserModel).where(UserModel.email == register_data.email)
        )
        if email_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "EMAIL_TAKEN",
                        "message": "Email is already in use.",
                        "request_id": request_id,
                    },
                    "errors": [
                        {"field": "email", "reason": "Email address already registered"}
                    ]
                }
            )
        
        # Check if username already exists
        username_check = await db.execute(
            select(UserModel).where(UserModel.username == register_data.username)
        )
        if username_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "USERNAME_TAKEN",
                        "message": "Username is already in use.",
                        "request_id": request_id,
                    },
                    "errors": [
                        {"field": "username", "reason": "Username already taken"}
                    ]
                }
            )
        
        # Hash password
        password_hash = hash_password(register_data.password)
        
        # Create new user
        new_user = UserModel(
            username=register_data.username,
            email=register_data.email,
            full_name=register_data.full_name,
            password_hash=password_hash,
            is_active=True,
            is_superuser=False,
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        # Generate JWT token
        token = token_ops.generate_access_token(
            user_id=str(new_user.user_id),
            email=new_user.email,
            fullname=new_user.full_name,
            expires_in=3600  # 1 hour
        )
        
        # Return success response
        return RegisterResponse(
            status="ok",
            message="registration successful",
            token=token,
            data={"user_id": f"usr_{new_user.user_id}"}
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 conflicts)
        raise
    except IntegrityError as e:
        # Handle database integrity errors (e.g., race conditions)
        await db.rollback()
        # Try to determine which field caused the conflict
        error_msg = str(e.orig).lower()
        if 'email' in error_msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "EMAIL_TAKEN",
                        "message": "Email is already in use.",
                        "request_id": request_id,
                    },
                    "errors": [
                        {"field": "email", "reason": "Email address already registered"}
                    ]
                }
            )
        elif 'username' in error_msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "USERNAME_TAKEN",
                        "message": "Username is already in use.",
                        "request_id": request_id,
                    },
                    "errors": [
                        {"field": "username", "reason": "Username already taken"}
                    ]
                }
            )
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred.",
                        "request_id": request_id,
                    }
                }
            )
    except Exception as e:
        # Handle unexpected errors
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "request_id": request_id,
                }
            }
        )
