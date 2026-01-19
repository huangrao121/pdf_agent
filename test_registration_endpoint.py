#!/usr/bin/env python3
"""
Test script to demonstrate the user registration endpoint.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_successful_registration():
    """Test successful user registration."""
    print("\n=== Test 1: Successful Registration ===")
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "john.doe@example.com",
            "username": "johndoe",
            "password": "SecurePass123",
            "full_name": "John Doe"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
    data = response.json()
    assert "token" in data
    assert data["status"] == "ok"
    print("✓ Registration successful")


def test_email_validation():
    """Test email validation."""
    print("\n=== Test 2: Invalid Email Format ===")
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "invalid-email",
            "username": "testuser",
            "password": "Password123",
            "full_name": "Test User"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_FAILED"
    print("✓ Email validation working")


def test_password_validation():
    """Test password strength validation."""
    print("\n=== Test 3: Weak Password (no number) ===")
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "test2@example.com",
            "username": "testuser2",
            "password": "OnlyLetters",
            "full_name": "Test User"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_FAILED"
    print("✓ Password validation working")


def test_duplicate_email():
    """Test duplicate email rejection."""
    print("\n=== Test 4: Duplicate Email ===")
    # Try to register with the same email as test 1
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "john.doe@example.com",
            "username": "anotherjohn",
            "password": "SecurePass456",
            "full_name": "Another John"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "EMAIL_TAKEN"
    print("✓ Duplicate email detection working")


def test_rate_limiting():
    """Test rate limiting."""
    print("\n=== Test 5: Rate Limiting ===")
    print("Making 5 requests...")
    for i in range(5):
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={
                "email": f"test{i}@example.com",
                "username": f"testuser{i}",
                "password": "Password123",
                "full_name": "Test User"
            }
        )
        print(f"  Request {i+1}: {response.status_code}")
    
    # 6th request should be rate limited
    print("Making 6th request (should be rate limited)...")
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": "test99@example.com",
            "username": "testuser99",
            "password": "Password123",
            "full_name": "Test User"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    if response.status_code == 429:
        print("✓ Rate limiting working")
    else:
        print(f"⚠ Rate limiting may not be working (expected 429, got {response.status_code})")


if __name__ == "__main__":
    print("=" * 60)
    print("User Registration Endpoint Test Suite")
    print("=" * 60)
    print("\nMake sure the server is running on http://localhost:8000")
    print("Press Ctrl+C to cancel or Enter to continue...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled")
        exit(0)
    
    try:
        test_successful_registration()
        test_email_validation()
        test_password_validation()
        test_duplicate_email()
        test_rate_limiting()
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
