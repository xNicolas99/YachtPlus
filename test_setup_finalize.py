import requests

url = "http://localhost:8000"

# Register
session = requests.Session()
resp1 = session.post(f"{url}/api/setup/register", json={"username": "admin", "password": "password"})
print("Register:", resp1.status_code, resp1.json())
cookies = session.cookies.get_dict()

# Try to login (should fail because is_active=False)
resp2 = session.post(f"{url}/api/auth/login", json={"username": "admin", "password": "password"})
print("Login before finalize:", resp2.status_code, resp2.json())

# Generate 2FA using the cookie returned by register
resp3 = session.get(f"{url}/api/auth/2fa/generate")
print("Generate 2FA:", resp3.status_code, resp3.json())
secret = resp3.json()["secret"]

# Install pyotp if needed for testing (we assume it's in the environment since we installed requirements)
import pyotp
totp = pyotp.TOTP(secret)
code = totp.now()

# Enable 2FA
resp4 = session.post(f"{url}/api/auth/2fa/enable", json={"secret": secret, "code": code})
print("Enable 2FA:", resp4.status_code, resp4.json())

# Finalize
resp5 = session.post(f"{url}/api/setup/finalize")
print("Finalize:", resp5.status_code, resp5.json())

# Try to login (should succeed because is_active=True)
resp6 = session.post(f"{url}/api/auth/login", json={"username": "admin", "password": "password", "otp_token": totp.now()})
print("Login after finalize:", resp6.status_code, resp6.json())
