import requests
import sys
import os
import time

# Configuration
BASE_URL = "http://localhost:8000/api"
SETUP_URL = f"{BASE_URL}/setup"
STATUS_URL = f"{SETUP_URL}/status"
REGISTER_URL = f"{SETUP_URL}/register"
FINALIZE_URL = f"{SETUP_URL}/finalize"
GEN_2FA_URL = f"{BASE_URL}/auth/2fa/generate"
ENABLE_2FA_URL = f"{BASE_URL}/auth/2fa/enable"

# Clean up any existing setup
if os.path.exists("/config/.setup_completed"):
    print("Removing existing setup completion flag...")
    os.remove("/config/.setup_completed")

def test_setup_flow():
    print("--- Starting Setup Flow Verification ---")

    # 1. Check Status (Should be False)
    print(f"Checking status at {STATUS_URL}...")
    try:
        resp = requests.get(STATUS_URL)
        if resp.status_code == 200:
            data = resp.json()
            print(f"Status Response: {data}")
            if data.get("is_setup") is not False:
                print("FAILURE: is_setup should be False initially.")
                sys.exit(1)
        else:
            print(f"FAILURE: Status check returned {resp.status_code}")
            # Try without /api prefix to debug
            resp_alt = requests.get("http://localhost:8000/setup/status")
            print(f"Debug: /setup/status returned {resp_alt.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"FAILURE: Connection error: {e}")
        sys.exit(1)

    # 2. Register User
    print("\nRegistering First User...")
    session = requests.Session()
    user_data = {
        "username": "admin_test",
        "password": "securepassword123"
    }
    resp = session.post(REGISTER_URL, json=user_data)
    if resp.status_code != 200:
        print(f"FAILURE: Registration failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("Registration successful.")
    # Check cookies for access_token
    if not session.cookies.get("access_token_cookie"):
        print("FAILURE: No access_token_cookie received.")
        sys.exit(1)

    print("Auth Cookie received.")

    # 3. Setup 2FA
    print("\nGenerating 2FA...")
    resp = session.post(GEN_2FA_URL)
    if resp.status_code != 200:
        print(f"FAILURE: 2FA Generation failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    secret = data.get("secret")
    qr_code = data.get("qr_code")

    if not secret or not qr_code:
        print("FAILURE: Missing secret or qr_code in response.")
        sys.exit(1)

    print(f"2FA Secret: {secret}")

    # Generate TOTP
    import pyotp
    totp = pyotp.TOTP(secret)
    code = totp.now()

    print(f"\nEnabling 2FA with code {code}...")
    resp = session.post(ENABLE_2FA_URL, json={"token": code})
    if resp.status_code != 200:
        print(f"FAILURE: 2FA Enable failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("2FA Enabled.")

    # 4. Finalize Setup
    print("\nFinalizing Setup...")
    resp = session.post(FINALIZE_URL)
    if resp.status_code != 200:
        print(f"FAILURE: Finalize failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    print("Setup Finalized.")

    # 5. Verify Status Again (Should be True)
    print("\nVerifying Final Status...")
    resp = requests.get(STATUS_URL)
    data = resp.json()
    if data.get("is_setup") is not True:
        print("FAILURE: is_setup should be True after finalize.")
        sys.exit(1)

    print("--- SUCCESS: Setup Flow Verified ---")

if __name__ == "__main__":
    # Ensure dependencies
    try:
        import pyotp
    except ImportError:
        print("Installing test dependencies...")
        os.system("pip install pyotp")

    # Wait for server to be ready?
    # Attempt connection
    try:
        requests.get(BASE_URL)
    except:
        print("Server might not be running. Attempting verification anyway.")

    test_setup_flow()
