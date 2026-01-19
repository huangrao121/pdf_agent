"""
Script to create a test user for manual testing of the login endpoint.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pdf_ai_agent.config.database.init_database import get_database_config, init_database, get_db_session
from pdf_ai_agent.config.database.models.model_user import UserModel
from pdf_ai_agent.security.password_utils import hash_password
from sqlalchemy import select


async def create_test_user():
    """Create a test user in the database."""
    # Initialize database
    config = get_database_config()
    await init_database(config)
    
    # Get database session
    async for session in get_db_session():
        # Check if user already exists
        result = await session.execute(
            select(UserModel).where(UserModel.email == "test@example.com")
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print("Test user already exists!")
            print(f"  Email: {existing_user.email}")
            print(f"  User ID: {existing_user.user_id}")
            print(f"  Full Name: {existing_user.full_name}")
            return
        
        # Create test user
        test_user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("testpassword123"),
            is_active=True,
            is_superuser=False,
            email_verified=True,
        )
        
        session.add(test_user)
        await session.commit()
        await session.refresh(test_user)
        
        print("✓ Test user created successfully!")
        print(f"  Email: {test_user.email}")
        print(f"  Password: testpassword123")
        print(f"  User ID: {test_user.user_id}")
        print(f"  Full Name: {test_user.full_name}")


if __name__ == "__main__":
    asyncio.run(create_test_user())
