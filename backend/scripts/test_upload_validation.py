#!/usr/bin/env python3
"""
Test upload endpoint validation.
"""

import sys
from pathlib import Path

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from app.models.api import UploadRequest

def test_upload_request():
    """Test UploadRequest with various payloads."""
    
    print("Testing UploadRequest validation...")
    
    # Test 1: Valid with image_base64
    try:
        req1 = UploadRequest(
            image_base64="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            subject="math",
            filename="test.png",
            mime_type="image/png"
        )
        print(f"✓ Test 1 PASSED: Valid base64 request")
        print(f"  - subject: {req1.subject}")
        print(f"  - filename: {req1.filename}")
    except Exception as e:
        print(f"✗ Test 1 FAILED: {e}")
        return False
    
    # Test 2: Valid with image_url
    try:
        from pydantic import HttpUrl
        req2 = UploadRequest(
            image_url=HttpUrl("https://example.com/image.png"),
            subject="chemistry"
        )
        print(f"✓ Test 2 PASSED: Valid URL request")
        print(f"  - subject: {req2.subject}")
    except Exception as e:
        print(f"✗ Test 2 FAILED: {e}")
        return False
    
    # Test 3: Invalid - no image
    try:
        req3 = UploadRequest(subject="math")
        print(f"✗ Test 3 FAILED: Should have raised validation error")
        return False
    except Exception as e:
        print(f"✓ Test 3 PASSED: Correctly rejected missing image: {e}")
    
    # Test 4: Frontend-like payload
    try:
        req4 = UploadRequest(
            image_base64="data:image/png;base64,test",
            filename="test.png",
            mime_type="image/png",
            subject="math",
            grade=None,
            notes=None,
            question_no=None,
            question_type=None,
            mock_problem_count=None,
            difficulty=None,
            source=None,
            options=[],
            knowledge_tags=[],
            error_tags=[],
            user_tags=[]
        )
        print(f"✓ Test 4 PASSED: Frontend-like payload")
        print(f"  - All optional fields handled correctly")
    except Exception as e:
        print(f"✗ Test 4 FAILED: {e}")
        return False
    
    print("\n✓ All validation tests passed!")
    return True

if __name__ == "__main__":
    success = test_upload_request()
    sys.exit(0 if success else 1)
