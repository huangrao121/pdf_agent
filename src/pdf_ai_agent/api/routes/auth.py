"""
Authentication routes for login, logout, and token management.
"""
import os
import logging
import secrets
import hashlib
import base64
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Request, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError

from pdf_ai_agent.config.database.init_database import get_db_session
from pdf_ai_agent.config.oauth_config import get_oauth_config
from pdf_ai_agent.config.app_config import get_app_config
from pdf_ai_agent.api.schemas.auth_schemas import (
    LoginRequest, 
    LoginResponse, 
    LoginData, 
    ErrorResponse,
    RegisterRequest,
    RegisterResponse,
    RegisterData,
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
    OAuthAuthorizeData,
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
    OAuthDisabledError,
    InvalidRedirectError,
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


@router.post(
    "/oauth/google/authorize",
    response_model=OAuthAuthorizeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        422: {"model": ErrorResponse, "description": "Validation failed"},
        403: {"model": ErrorResponse, "description": "OAuth disabled"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def oauth_google_authorize(
    request: Request,
    oauth_data: OAuthAuthorizeRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Generate Google OAuth authorization URL.
    
    Creates an authorization URL with PKCE support and stores state/verifier
    in HttpOnly cookies for security.
    
    Security measures:
    - State parameter to prevent CSRF attacks
    - PKCE to prevent authorization code interception
    - HttpOnly cookies for state and code_verifier storage
    - Redirect URL validation against allowlist
    """
    try:
        # Load configurations
        oauth_config = get_oauth_config()
        app_config = get_app_config()
        
        # Check if OAuth is enabled
        if not oauth_config.oauth_enabled:
            raise OAuthDisabledError()
        
        # Validate redirect_to parameter
        if not auth_service.validate_redirect_to(
            oauth_data.redirect_to,
            oauth_config.oauth_allowed_redirect_to_prefixes
        ):
            raise InvalidRedirectError(
                f"redirect_to must start with one of: {', '.join(oauth_config.oauth_allowed_redirect_to_prefixes)}"
            )
        
        # Generate state
        state = auth_service.generate_state()
        
        # Generate PKCE pair if enabled
        code_challenge = None
        code_verifier = None
        if app_config.oauth_pkce_enabled:
            code_verifier, code_challenge = auth_service.generate_pkce_pair()
        
        # Build authorization URL
        authorization_url = auth_service.build_authorization_url(
            client_id=oauth_config.google_client_id,
            redirect_uri=oauth_config.google_redirect_uri,
            scope=oauth_config.google_scopes,
            state=state,
            auth_endpoint=oauth_config.google_auth_endpoint,
            code_challenge=code_challenge,
        )
        
        # Build response
        response = OAuthAuthorizeResponse(
            status="ok",
            data=OAuthAuthorizeData(
                authorization_url=authorization_url,
                provider="google",
                state=state,
            )
        )
        
        # Create FastAPI Response to set cookies
        fastapi_response = Response(
            content=response.model_dump_json(),
            media_type="application/json",
            status_code=status.HTTP_200_OK,
        )
        
        # Set HttpOnly cookies for state and code_verifier
        max_age = app_config.oauth_state_ttl_seconds
        
        fastapi_response.set_cookie(
            key="oauth_state",
            value=state,
            httponly=True,
            secure=True,  # Only send over HTTPS
            samesite="lax",  # CSRF protection
            max_age=max_age,
        )
        
        if code_verifier:
            fastapi_response.set_cookie(
                key="oauth_pkce_verifier",
                value=code_verifier,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=max_age,
            )
        
        # Store redirect_to in cookie as well
        fastapi_response.set_cookie(
            key="oauth_redirect_to",
            value=oauth_data.redirect_to,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=max_age,
        )
        
        return fastapi_response
        
    except OAuthDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except InvalidRedirectError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
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
        logger.error(f"OAuth authorization error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            }
        )
