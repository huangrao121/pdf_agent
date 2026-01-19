# JWT Authentication with ES256

Secure JWT implementation using PyJWT with ECDSA (ES256) signing.

## Features

- **ES256 Algorithm**: ECDSA using P-256 curve + SHA-256
- **Key Rotation**: Support multiple public keys with `kid` selection
- **Secure Verification**: Validates signature, expiration, issuer, audience
- **Clock Skew**: Configurable leeway for time drift

## Quick Start

### 1. Generate Keys

```bash
# Generate private key
openssl ecparam -name prime256v1 -genkey -noout -out private_key.pem

# Extract public key
openssl ec -in private_key.pem -pubout -out public_key.pem
```

### 2. Configure Environment

```bash
export JWT_ACTIVE_KID="key-2024-01"
export JWT_PRIVATE_KEY="$(cat private_key.pem)"
export JWT_KEYSET='{"key-2024-01": "'"$(cat public_key.pem)"'"}'
```

### 3. Use in Code

```python
from security import KeyManager, TokenOperations

# Load keys from environment
key_manager = KeyManager.from_env()

# Initialize token operations
token_ops = TokenOperations(
    key_manager=key_manager,
    issuer="my-app",
    audience="my-api",
    leeway=10  # 10 seconds clock skew tolerance
)

# Generate token
token = token_ops.generate_access_token(
    user_id="user123",
    expires_in=3600
)

# Verify token
try:
    payload = token_ops.verify_and_decode_token(token)
    user_id = payload["sub"]
except TokenExpiredError:
    print("Token expired")
```

## Key Rotation

Add new keys to `JWT_KEYSET` while keeping old keys active for verification:

```json
{
  "key-2024-01": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "key-2024-02": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

Set `JWT_ACTIVE_KID=key-2024-02` to sign with the new key.

## Security

- Only ES256 algorithm is allowed
- Token verification checks: signature, expiration, issuer, audience
- Unknown `kid` values are rejected
- Private keys must be kept secure (never commit to git)
