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

2. Copy `config.yaml.sample` to `config.yaml` for PKCE and TTL settings

### OAuth Endpoint

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
