"""
Authentication routes for login, logout, and token management.
"""
import os
import logging

from fastapi import APIRouter, Depends, Request, HTTPException, status, Response
from fastapi.responses import RedirectResponse
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
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
    RateLimitError,
    EmailTakenError,
    UsernameTakenError,
    OAuthDisabledError,
    InvalidRedirectError,
    InvalidOAuthStateError,
    OAuthProviderError,
    InvalidIdTokenError,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "status": "error",
                "error_code": e.error_code,
                "message": e.message,
            }
        )
    
    except PydanticValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


@router.get(
    "/oauth/google/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses={
        302: {"description": "Redirect to frontend with tokens in cookies"},
        400: {"model": ErrorResponse, "description": "Invalid OAuth state or error from provider"},
        403: {"model": ErrorResponse, "description": "OAuth disabled"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def oauth_google_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    auth_service: AuthService = Depends(get_auth_service),
    token_ops: TokenOperations = Depends(get_token_operations),
):
    """
    Handle Google OAuth callback.
    
    This endpoint is called by Google after user authorizes the application.
    It exchanges the authorization code for tokens, verifies the ID token,
    creates or links the user account, and redirects back to the frontend
    with JWT tokens.
    
    Query parameters:
    - code: Authorization code from Google (required for success)
    - state: State parameter for CSRF protection (required)
    - error: Error code if user denied or error occurred
    - error_description: Description of the error
    
    Security measures:
    - State parameter validation (CSRF protection)
    - PKCE code_verifier validation
    - ID token verification (audience, issuer, expiration)
    - HttpOnly cookies for token storage
    """
    try:
        # Load configurations
        oauth_config = get_oauth_config()
        app_config = get_app_config()
        
        # Get frontend base URL from environment (defined early for error handlers)
        frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
        
        # Check if OAuth is enabled
        if not oauth_config.oauth_enabled:
            raise OAuthDisabledError()
        
        # Get stored state and redirect_to from cookies
        expected_state = request.cookies.get("oauth_state")
        redirect_to = request.cookies.get("oauth_redirect_to", "/app")
        code_verifier = request.cookies.get("oauth_pkce_verifier")
        
        # Check if error from provider
        if error:
            error_msg = error_description or error
            logger.warning(f"OAuth error from provider: {error_msg}")
            # Redirect to frontend with error
            redirect_url = f"{frontend_base_url}{redirect_to}?error=oauth_error&error_description={error_msg}"
            response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
            # Clear OAuth cookies
            response.delete_cookie("oauth_state")
            response.delete_cookie("oauth_redirect_to")
            response.delete_cookie("oauth_pkce_verifier")
            return response
        
        # Validate required parameters
        if not code or not state:
            raise InvalidOAuthStateError("Missing code or state parameter")
        
        # Validate state parameter (CSRF protection)
        if not expected_state or state != expected_state:
            raise InvalidOAuthStateError("State parameter mismatch")
        
        # Exchange code for tokens
        token_data = await auth_service.exchange_code_for_tokens(
            code=code,
            client_id=oauth_config.google_client_id,
            client_secret=oauth_config.google_client_secret,
            redirect_uri=oauth_config.google_redirect_uri,
            token_endpoint=oauth_config.google_token_endpoint,
            code_verifier=code_verifier if app_config.oauth_pkce_enabled else None,
        )
        
        # Get id_token from response
        id_token = token_data.get("id_token")
        if not id_token:
            raise InvalidIdTokenError("No id_token in response")
        
        # Verify and decode id_token
        id_token_payload = auth_service.verify_and_decode_id_token(
            id_token=id_token,
            client_id=oauth_config.google_client_id,
        )
        
        # Extract user information from id_token
        provider_subject = id_token_payload.get("sub")
        provider_email = id_token_payload.get("email")
        # email_verified = id_token_payload.get("email_verified", False)
        provider_name = id_token_payload.get("name")
        avatar_url = id_token_payload.get("picture")
        
        if not provider_subject:
            raise InvalidIdTokenError("Missing sub claim in id_token")
        
        # Optional: Only accept verified emails
        # if not email_verified:
        #     raise InvalidIdTokenError("Email not verified by provider")
        
        # Handle user creation or linking
        user, is_new_user = await auth_service.handle_oauth_user(
            provider="google",
            provider_subject=provider_subject,
            provider_email=provider_email,
            provider_name=provider_name,
            avatar_url=avatar_url,
            access_token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
        )
        
        # Generate our own JWT access token
        expires_in = int(os.getenv("JWT_EXPIRES_IN", "3600"))
        access_token = token_ops.generate_access_token(
            user_id=str(user.user_id),
            expires_in=expires_in,
            email=user.email,
            fullname=user.full_name,
        )
        
        # Build redirect URL to frontend
        redirect_url = f"{frontend_base_url}{redirect_to}"
        
        # Create redirect response
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        
        # Set HttpOnly cookie for access token
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,  # Only send over HTTPS
            samesite="lax",
            max_age=expires_in,
        )
        
        # Clear OAuth state cookies
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_redirect_to")
        response.delete_cookie("oauth_pkce_verifier")
        
        logger.info(f"OAuth login successful for user {user.user_id} (new_user={is_new_user})")
        
        return response
        
    except InvalidOAuthStateError as e:
        logger.warning(f"Invalid OAuth state: {e.message}")
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/login?error=invalid_state"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        # Clear OAuth cookies
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_redirect_to")
        response.delete_cookie("oauth_pkce_verifier")
        return response
    
    except (OAuthProviderError, InvalidIdTokenError) as e:
        logger.error(f"OAuth error: {e.message}", exc_info=True)
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
        error_code = e.error_code.lower()
        redirect_url = f"{frontend_url}/login?error={error_code}"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        # Clear OAuth cookies
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_redirect_to")
        response.delete_cookie("oauth_pkce_verifier")
        return response
    
    except OAuthDisabledError:
        logger.warning("OAuth is disabled")
        # frontend_base_url might not be defined if exception occurs early
        frontend_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/login?error=oauth_disabled"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        return response
    
    except Exception as e:
        # Log the error with proper logging
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        # frontend_base_url might not be defined if exception occurs early
        frontend_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/login?error=internal_error"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        # Try to clear OAuth cookies if possible
        try:
            response.delete_cookie("oauth_state")
            response.delete_cookie("oauth_redirect_to")
            response.delete_cookie("oauth_pkce_verifier")
        except Exception:
            pass  # Ignore cookie deletion errors
        return response
