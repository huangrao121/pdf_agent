# PDF Agent

A PDF processing agent with secure JWT authentication.

## Features

- **JWT Authentication**: Secure token-based authentication using ES256 (ECDSA)
- **Google OAuth**: OAuth 2.0 authorization with PKCE support
- **PDF Processing**: Process and manage PDF documents
- **FastAPI Backend**: Modern REST API framework

## OAuth Configuration

The application supports Google OAuth 2.0 for user authentication:

1. Copy `.env.dev.sample` to `.env.dev` and configure:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth client secret
   - `GOOGLE_REDIRECT_URI`: OAuth callback URL
   - `OAUTH_ALLOWED_REDIRECT_TO_PREFIXES`: Allowed redirect paths
   - `FRONTEND_BASE_URL`: Frontend base URL for redirects

2. Copy `config.yaml.sample` to `config.yaml` for PKCE and TTL settings

### OAuth Endpoints

#### 1. Authorization Endpoint

**POST** `/api/auth/oauth/google/authorize`

Request:
```json
{
  "redirect_to": "/app"
}
```

Response:
```json
{
  "status": "ok",
  "data": {
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "provider": "google",
    "state": "st_..."
  }
}
```

#### 2. Callback Endpoint

**GET** `/api/auth/oauth/google/callback`

Query Parameters:
- `code` (string, required): Authorization code from Google
- `state` (string, required): State parameter for CSRF protection
- `error` (string, optional): Error code if authorization failed
- `error_description` (string, optional): Error description

Response:
- `302 Redirect` to frontend with access token in HttpOnly cookie
- On success: Redirects to `FRONTEND_BASE_URL + redirect_to`
- On error: Redirects to `FRONTEND_BASE_URL/login?error=<error_code>`

Security Features:
- State parameter validation (CSRF protection)
- PKCE code verifier validation
- ID token verification (audience, issuer, expiration)
- HttpOnly cookie for token storage
- Automatic user creation or linking based on email

## Security Module

The project includes a secure JWT authentication module in the `/security` folder. See [security/README.md](security/README.md) for details on:

- Token generation and verification
- ES256 (ECDSA) signing
- Key rotation support
- Usage examples

## Getting Started

```bash
# Install dependencies
pip install -e .

# Run the application
python main.py
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```
