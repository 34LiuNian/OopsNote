"""Reset password for testing."""
from app.services.user_store import user_store
from app.auth.security import hash_password, verify_password

# Reset password for Alan0634
username = "Alan0634"
new_password = "admin123456"

print(f"Resetting password for user: {username}")
print(f"New password: {new_password}")

try:
    # Method 1: Using admin_reset_password
    user = user_store.admin_reset_password(username=username, new_password=new_password)
    print(f"✅ Password reset successful!")
    print(f"User: {user.username}")
    print(f"Role: {user.role}")
    
    # Verify the password works
    verified = verify_password(new_password, user.password_hash)
    print(f"Password verification: {verified}")
    
except Exception as e:
    print(f"❌ Error: {e}")

# Also create a test admin user if it doesn't exist
print("\n--- Creating test user: testadmin ---")
try:
    test_user = user_store.create_user(
        username="testadmin",
        password="admin123456",
        role="admin",
        nickname="Test Admin"
    )
    print(f"✅ Created user: {test_user.username}")
    print(f"Role: {test_user.role}")
except ValueError as e:
    if "已存在" in str(e):
        print(f"ℹ️  User 'testadmin' already exists, resetting password...")
        user_store.admin_reset_password(username="testadmin", new_password="admin123456")
        print(f"✅ Password reset for 'testadmin'")
    else:
        print(f"❌ Error: {e}")
