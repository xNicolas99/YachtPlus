import requests

url = "http://localhost:8000"

# Register
session = requests.Session()
resp1 = session.post(f"{url}/api/setup/register", json={"username": "admin", "password": "password"})
print("Register:", resp1.status_code, resp1.json())

# Generate 2FA
resp2 = session.get(f"{url}/api/auth/2fa/generate")
print("Generate 2FA:", resp2.status_code, resp2.json())
