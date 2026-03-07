"""Test login with detailed error reporting."""
import urllib.request
import urllib.error
import json

BASE_URL = "http://localhost:8000"

def make_request(endpoint, data=None):
    """Make HTTP request and return response."""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    if data:
        data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    
    try:
        with urllib.request.urlopen(req) as response:
            return {
                'status': response.status,
                'data': json.loads(response.read().decode('utf-8'))
            }
    except urllib.error.HTTPError as e:
        return {
            'status': e.code,
            'data': json.loads(e.read().decode('utf-8')) if e.read else None,
            'error': str(e)
        }
    except Exception as e:
        return {
            'status': 0,
            'data': None,
            'error': str(e)
        }

# Test credentials
test_users = [
    {"username": "Alan0634", "password": "admin123456"},
    {"username": "admin", "password": "admin123456"},
]

print("=== Testing Login ===\n")

for user in test_users:
    print(f"Testing: {user['username']} / {user['password']}")
    
    result = make_request("/auth/login", user)
    
    print(f"Status Code: {result['status']}")
    
    if result['data']:
        print(f"Response: {json.dumps(result['data'], indent=2, ensure_ascii=False)}")
        
        if result['status'] == 200:
            print("✅ Login successful!")
            print(f"Access Token: {result['data']['access_token'][:50]}...")
            print(f"Refresh Token: {result['data']['refresh_token'][:50]}...")
    else:
        print(f"Error: {result['error']}")
    
    print("-" * 50)
