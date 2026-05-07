import re

with open("backend/api/routers/setup/setup.py", "r") as f:
    content = f.read()

# Replace access_token generation and cookie logic
old_code = """
    access_token = create_access_token(data={"sub": new_user.username})

    return {
        "login": "successful",
        "username": new_user.username
    }
"""

new_code = """
    access_token = create_access_token(data={"sub": new_user.username})
    Authorize.set_access_cookies(access_token, response)

    return {
        "login": "successful",
        "username": new_user.username
    }
"""

content = content.replace(old_code, new_code)

with open("backend/api/routers/setup/setup.py", "w") as f:
    f.write(content)
