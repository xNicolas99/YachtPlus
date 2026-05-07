import requests

url = "http://localhost:8000"

# Register
session = requests.Session()
resp1 = session.post(f"{url}/api/setup/register", json={"username": "admin", "password": "password"})
print("Register:", resp1.status_code, resp1.json())
cookies = session.cookies.get_dict()

# Login
resp2 = session.post(f"{url}/api/auth/login", json={"username": "admin", "password": "password"})
print("Login:", resp2.status_code, resp2.json())

# Generate 2FA
resp3 = session.get(f"{url}/api/auth/2fa/generate")
print("Generate 2FA:", resp3.status_code, resp3.json())

# Try to bypass setup after registration
resp4 = session.post(f"{url}/api/setup/bypass")
print("Bypass after register:", resp4.status_code, resp4.json())
