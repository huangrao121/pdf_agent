"""
Authentication routes for login, logout, and token management.
"""
import os
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.schemas.auth_schemas import LoginRequest, LoginResponse, LoginData, ErrorResponse
from pdf_ai_agent.api.services.auth_service import AuthService
from pdf_ai_agent.api.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
    RateLimitError,
)
from pdf_ai_agent.api.rate_limiter import rate_limiter
from pdf_ai_agent.security.token_operations import TokenOperations
from pdf_ai_agent.security.key_manager import KeyManager

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_token_operations() -> TokenOperations:
    """
    Get token operations instance with configuration from environment.
    """
    # Load key configuration from environment
    private_key = os.getenv("JWT_PRIVATE_KEY", "")
    active_kid = os.getenv("JWT_ACTIVE_KID", "default-key")
    public_key = os.getenv("JWT_PUBLIC_KEY", "")
    issuer = os.getenv("JWT_ISSUER", "pdf-ai-agent")
    audience = os.getenv("JWT_AUDIENCE", "pdf-ai-agent-api")
    
    # Create keyset
    keyset = {active_kid: public_key} if public_key else {}
    
    # Initialize key manager
    key_manager = KeyManager(
        active_kid=active_kid,
        private_key_pem=private_key,
        keyset=keyset
    )
    
    # Initialize token operations
    return TokenOperations(
        key_manager=key_manager,
        issuer=issuer,
        audience=audience,
        leeway=0
    )


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    """
    # Check for X-Forwarded-For header (if behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Fall back to direct client IP
    return request.client.host if request.client else "unknown"


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Account disabled or email not verified"},
        422: {"model": ErrorResponse, "description": "Validation failed"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
    token_ops: TokenOperations = Depends(get_token_operations),
):
    """
    User login endpoint.
    
    Authenticates user with email and password, returns JWT access token.
    
    Security measures:
    - Rate limiting by IP and email
    - Account lockout after 5 failed attempts
    - Constant-time password comparison
    - Audit logging (not implemented in this minimal version)
    - User enumeration prevention (same error for invalid email and password)
    """
    client_ip = get_client_ip(request)
    email = login_data.email.lower().strip()
    
    try:
        # Check rate limiting by IP
        is_limited, retry_after = rate_limiter.is_rate_limited(f"ip:{client_ip}")
        if is_limited:
            raise RateLimitError(retry_after=retry_after)
        
        # Check rate limiting by email
        is_limited, retry_after = rate_limiter.is_rate_limited(f"email:{email}")
        if is_limited:
            raise RateLimitError(retry_after=retry_after)
        
        # Authenticate user
        user = await AuthService.authenticate_user(
            db=db,
            email=email,
            password=login_data.password,
            require_email_verification=False  # Set to True if email verification is required
        )
        
        # Clear rate limit on successful login
        rate_limiter.clear_attempts(f"ip:{client_ip}")
        rate_limiter.clear_attempts(f"email:{email}")
        
        # Generate access token
        expires_in = int(os.getenv("JWT_EXPIRES_IN", "3600"))
        access_token = token_ops.generate_access_token(
            user_id=str(user.user_id),
            expires_in=expires_in,
            email=user.email,
            fullname=user.full_name,
        )
        
        # Build response
        return LoginResponse(
            status="ok",
            message="login successful",
            data=LoginData(
                access_token=access_token,
                token_type="Bearer",
                expires_in=expires_in,
                refresh_token=None,  # Refresh token not implemented yet
                user_id=str(user.user_id),
                email=user.email or "",
                full_name=user.full_name,
            )
        )
        
    except InvalidCredentialsError as e:
        # Record failed attempt
        rate_limiter.record_failed_attempt(f"ip:{client_ip}")
        rate_limiter.record_failed_attempt(f"email:{email}")
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except AccountDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except EmailNotVerifiedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            },
            headers={"Retry-After": str(e.retry_after)}
        )
    
    except PydanticValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "status": "error",
                "error_code": "VALIDATION_FAILED",
                "message": "Validation error",
                "details": e.errors(),
            }
        )
    
    except Exception as e:
        # Log the error with proper logging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            }
        )
