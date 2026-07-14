import re
with open("backend/api/settings.py", "r") as f:
    content = f.read()

replacement = """    # Check persistent file or create it
    secret_file = os.getenv("SECRET_KEY_FILE", "/config/.secret_key")
    env_file = os.getenv("ENV_FILE", "/config/.env")

    # If the directory doesn't exist (e.g. running outside docker), fall back to current directory
    config_dir = os.path.dirname(env_file)
    if config_dir and not os.path.exists(config_dir):
        # Graceful fallback for local development
        env_file = ".env"
        secret_file = ".secret_key"

    try:
        # First try to read from .env
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("SECRET_KEY="):
                        return line.split("=", 1)[1].strip()

        # If not found in .env, check legacy secret_file or generate new
        if os.path.exists(secret_file):
            with open(secret_file, "r") as f:
                new_secret = f.read().strip()
        else:
            new_secret = secrets.token_urlsafe(32)

        # Write to .env
        with open(env_file, "a") as f:
            f.write(chr(10) + "SECRET_KEY=" + str(new_secret) + chr(10))

        return new_secret"""

new_content = re.sub(r'    # Check persistent file or create it.*?return new_secret', replacement, content, flags=re.DOTALL)

with open("backend/api/settings.py", "w") as f:
    f.write(new_content)
