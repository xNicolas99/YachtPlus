import re

with open("backend/api/routers/users.py", "r") as f:
    content = f.read()

# Add check for _user.is_active to login and login_cookie
old_login = """    if _user is not None and crud.verify_password(user_data.password, _user.hashed_password):

        # Check 2FA"""

new_login = """    if _user is not None and crud.verify_password(user_data.password, _user.hashed_password):
        if not _user.is_active:
            record_login_attempt(db, client_ip, user_data.username, False)
            logger.warning(f"Login failed for IP: {client_ip} - Reason: User is inactive")
            raise HTTPException(status_code=400, detail="User account is inactive. Setup may be incomplete.")

        # Check 2FA"""

content = content.replace(old_login, new_login)

old_login_cookie = """    if _user is not None and crud.verify_password(user_data.password, _user.hashed_password):
        if _user.is_2fa_enabled:"""

new_login_cookie = """    if _user is not None and crud.verify_password(user_data.password, _user.hashed_password):
        if not _user.is_active:
            record_login_attempt(db, client_ip, user_data.username, False)
            logger.warning(f"Login failed for IP: {client_ip} - Reason: User is inactive")
            raise HTTPException(status_code=400, detail="User account is inactive. Setup may be incomplete.")

        if _user.is_2fa_enabled:"""

content = content.replace(old_login_cookie, new_login_cookie)

with open("backend/api/routers/users.py", "w") as f:
    f.write(content)
