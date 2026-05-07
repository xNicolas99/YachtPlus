import requests

url = "http://localhost:8000"

# Register
resp1 = requests.post(f"{url}/api/setup/register", json={"username": "admin", "password": "password"})
print("Register:", resp1.status_code, resp1.json())
# In setup.py, register sets a cookie "access_token_cookie", but we removed it returning in json response
cookies = resp1.cookies

# Before bypass, try generate 2FA
resp2 = requests.get(f"{url}/api/auth/2fa/generate", cookies=cookies)
print("Generate 2FA before bypass:", resp2.status_code, resp2.json())

# Bypass setup
resp3 = requests.post(f"{url}/api/setup/bypass")
print("Bypass:", resp3.status_code, resp3.json())
