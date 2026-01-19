"""
Utility functions for the API.
"""
import uuid
from datetime import datetime


def generate_request_id() -> str:
    """
    Generate a unique request ID.
    
    Returns:
        Request ID in format 'req_XXXXXXXXXX'
    """
    # Generate a short unique ID using timestamp and random UUID
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    random_part = str(uuid.uuid4())[:8]
    return f"req_{timestamp}_{random_part}"


def generate_user_id() -> str:
    """
    Generate a unique user ID.
    
    Returns:
        User ID in format 'usr_XXXXXXXXXX'
    """
    # Generate a unique ID
    unique_part = str(uuid.uuid4()).replace('-', '')[:16]
    return f"usr_{unique_part}"
