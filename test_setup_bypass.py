import requests

url = "http://localhost:8000"

# First try to access a protected route before doing anything
resp0 = requests.get(f"{url}/api/apps/")
print("Access protected route before setup:", resp0.status_code)

# Bypass setup
resp1 = requests.post(f"{url}/api/setup/bypass")
print("Bypass:", resp1.status_code, resp1.json())

# Try to access protected route after bypass
resp2 = requests.get(f"{url}/api/apps/")
print("Access protected route after bypass:", resp2.status_code)

# Check if anyone can hit register again
resp3 = requests.post(f"{url}/api/setup/register", json={"username": "hacker", "password": "password"})
print("Register after bypass:", resp3.status_code, resp3.json())
