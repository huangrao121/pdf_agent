"""
Example usage of the JWT authentication module.

This example demonstrates:
1. Generating test keys
2. Setting up the key manager
3. Creating and verifying tokens
4. Handling errors

NOTE: This is for demonstration only. In production, generate proper keys
and store them securely (e.g., environment variables, secret manager).
"""

from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from pdf_ai_agent.security.exceptions import (
    TokenExpiredError,
    InvalidSignatureError,
    InvalidAudienceError,
)
from pdf_ai_agent.security.key_manager import KeyManager
from pdf_ai_agent.security.token_operations import TokenOperations

import json

def generate_pair_keys():
    """Generate test ECDSA keys for demonstration."""
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    
    # Serialize to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return private_pem, public_pem


def test_main():
    """Demonstrate JWT authentication usage."""
    print("=" * 60)
    print("JWT Authentication Example with ES256")
    print("=" * 60)
    
    # 1. Generate test keys
    print("\n1. Generating test keys...")
    private_key_pem, public_key_pem = generate_pair_keys()
    print("✓ Keys generated successfully")
    
    # 2. Set up key manager
    print("\n2. Setting up key manager...")
    key_manager = KeyManager(
        active_kid="example-key-2024",
        private_key_pem=private_key_pem,
        keyset={"example-key-2024": public_key_pem}
    )
    print("✓ Key manager configured")
    
    # 3. Create token operations
    print("\n3. Initializing token operations...")
    token_ops = TokenOperations(
        key_manager=key_manager,
        issuer="example-app",
        audience="example-api",
        leeway=10  # 10 seconds clock skew tolerance
    )
    print("✓ Token operations ready")
    
    # 4. Generate a token
    print("\n4. Generating access token...")
    token = token_ops.generate_access_token(
        user_id="user_12345",
        expires_in=3600,  # 1 hour
        email="user@example.com",
        fullname="Example User"
    )
    print(f"✓ Token generated: {token[:50]}...")
    
    # 5. Verify and decode the token
    print("\n5. Verifying and decoding token...")
    try:
        payload = token_ops.verify_and_decode_token(token)
        print("✓ Token verified successfully!")
        print(f"  - User ID: {payload['sub']}")
        print(f"  - Issuer: {payload['iss']}")
        print(f"  - Audience: {payload['aud']}")
        print(f"  - Email: {payload.get('email', 'N/A')}")
        print(f"  - Full Name: {payload.get('fullname', 'N/A')}")
        print(f"  - Issued At: {datetime.fromtimestamp(payload['iat'], tz=timezone.utc)}")
        print(f"  - Expires At: {datetime.fromtimestamp(payload['exp'], tz=timezone.utc)}")
    except TokenExpiredError:
        print("✗ Token has expired")
    except InvalidSignatureError:
        print("✗ Token signature is invalid")
    except Exception as e:
        print(f"✗ Token verification failed: {e}")
    
    # 6. Demonstrate unsafe decode (for debugging only)
    print("\n6. Unsafe decode (debugging only)...")
    unsafe_payload = token_ops.decode_token_unsafe(token)
    print("⚠ Decoded without verification (use only for debugging):")
    print(f"  - User ID: {unsafe_payload['sub']}")
    
    # 7. Demonstrate error handling
    print("\n7. Testing error handling...")
    
    # Test with wrong audience
    print("\n   a. Testing wrong audience...")
    wrong_audience_ops = TokenOperations(
        key_manager=key_manager,
        issuer="example-app",
        audience="wrong-audience"
    )
    try:
        wrong_audience_ops.verify_and_decode_token(token)
        print("   ✗ Should have failed")
    except InvalidAudienceError:
        print("   ✓ Correctly rejected token with wrong audience")
    
    # Test with tampered token
    print("\n   b. Testing tampered token...")
    tampered_token = token[:-10] + "tampered12"
    try:
        token_ops.verify_and_decode_token(tampered_token)
        print("   ✗ Should have failed")
    except InvalidSignatureError:
        print("   ✓ Correctly rejected tampered token")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)

def main():
    private_key, public_key = generate_pair_keys()

    _, old_public_key = generate_pair_keys()
    keyset = {
        "key-2025-12": old_public_key,
        "key-2026-01": public_key,
    }

    env_content = f"""# JWT 配置 - 生成于 {datetime.now().isoformat()}
    JWT_ACTIVE_KID=key-2026-01
    JWT_PRIVATE_KEY={private_key.replace(chr(10), '\\n')}
    KEYSET={json.dumps(keyset).replace(chr(10), '\\n')}
    """
    env_file = ".env.dev"
        # 写入 .env 文件
    with open(env_file, 'a') as f:
        f.write(env_content)
    
    print("✅ 密钥生成成功！")
    print(f"📁 已写入 .env 文件")
    print(f"\n当前密钥 ID: key-2024-01")
    print(f"Keyset 包含 {len(keyset)} 个公钥")
    
    # 显示内容（不显示完整的私钥）
    print(f"\n私钥前 50 字符: {private_key[:50]}...")
    print(f"\nKeyset:")
    for kid in keyset:
        pub = keyset[kid][:50] + "..."
        print(f"  {kid}: {pub}")

if __name__ == "__main__":
    main()
