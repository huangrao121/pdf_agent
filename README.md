# PDF Agent

A PDF processing agent with secure JWT authentication.

## Features

- **JWT Authentication**: Secure token-based authentication using ES256 (ECDSA)
- **PDF Processing**: Process and manage PDF documents
- **FastAPI Backend**: Modern REST API framework

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
