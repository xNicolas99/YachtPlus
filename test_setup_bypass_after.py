import requests

url = "http://localhost:8000"

# Register
session = requests.Session()
resp1 = session.post(f"{url}/api/setup/register", json={"username": "admin", "password": "password"})

# Generate 2FA
resp2 = session.get(f"{url}/api/auth/2fa/generate")
secret = resp2.json()["secret"]

import pyotp
totp = pyotp.TOTP(secret)
code = totp.now()

# Enable 2FA
resp3 = session.post(f"{url}/api/auth/2fa/enable", json={"secret": secret, "code": code})

# Finalize
resp4 = session.post(f"{url}/api/setup/finalize")

# Try to bypass setup after setup complete
resp5 = session.post(f"{url}/api/setup/bypass")
print("Bypass after setup complete:", resp5.status_code, resp5.json())
