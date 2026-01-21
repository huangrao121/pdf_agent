"""
Authentication routes for login, logout, and token management.
"""
import os
import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.api.schemas.auth_schemas import (
    LoginRequest, 
    LoginResponse, 
    LoginData, 
    ErrorResponse,
    RegisterRequest,
    RegisterResponse,
    RegisterData,
)
from pdf_ai_agent.api.services.auth_service import AuthService
from pdf_ai_agent.api.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
    RateLimitError,
    EmailTakenError,
    UsernameTakenError,
)
from pdf_ai_agent.api.rate_limiter import rate_limiter
from pdf_ai_agent.security.token_operations import TokenOperations, get_token_operations

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


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

def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    """
    Get AuthService instance.
    """
    return AuthService(db_session=session)

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
    auth_service: AuthService = Depends(get_auth_service),
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
        user = await auth_service.authenticate_user(
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
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            }
        )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "Email or username already taken"},
        422: {"model": ErrorResponse, "description": "Validation failed"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def register(
    request: Request,
    register_data: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    token_ops: TokenOperations = Depends(get_token_operations),
):
    """
    User registration endpoint.
    
    Creates a new user account with email, username, password, and full name.
    Returns JWT access token on successful registration.
    
    Security measures:
    - Rate limiting by IP and email
    - Email and username uniqueness validation
    - Password strength validation
    - Input sanitization
    """
    client_ip = get_client_ip(request)
    email = register_data.email.lower().strip()
    
    try:
        # Check rate limiting by IP
        is_limited, retry_after = rate_limiter.is_rate_limited(f"register_ip:{client_ip}")
        if is_limited:
            raise RateLimitError(retry_after=retry_after)
        
        # Check rate limiting by email
        is_limited, retry_after = rate_limiter.is_rate_limited(f"register_email:{email}")
        if is_limited:
            raise RateLimitError(retry_after=retry_after)
        
        # Register user
        user = await auth_service.register_user(
            email=email,
            username=register_data.username,
            password=register_data.password,
            full_name=register_data.full_name,
        )
        
        # Clear rate limit on successful registration
        rate_limiter.clear_attempts(f"register_ip:{client_ip}")
        rate_limiter.clear_attempts(f"register_email:{email}")
        
        # Generate access token
        expires_in = int(os.getenv("JWT_EXPIRES_IN", "3600"))
        access_token = token_ops.generate_access_token(
            user_id=str(user.user_id),
            expires_in=expires_in,
            email=user.email,
            fullname=user.full_name,
        )
        
        # Build response
        return RegisterResponse(
            status="ok",
            message="registration successful",
            token=access_token,
            data=RegisterData(
                user_id=str(user.user_id),
            )
        )
        
    except EmailTakenError as e:
        # Record failed attempt
        rate_limiter.record_failed_attempt(f"register_ip:{client_ip}")
        rate_limiter.record_failed_attempt(f"register_email:{email}")
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except UsernameTakenError as e:
        # Record failed attempt
        rate_limiter.record_failed_attempt(f"register_ip:{client_ip}")
        rate_limiter.record_failed_attempt(f"register_email:{email}")
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
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
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            }
        )
