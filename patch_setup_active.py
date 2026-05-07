import re

with open("backend/api/routers/setup/setup.py", "r") as f:
    content = f.read()

# Replace the registration user active flag
old_reg = """        user_update = UserUpdate(
            username=user.username,
            password=user.password,
            is_superuser=True,
            is_active=True
        )"""

new_reg = """        user_update = UserUpdate(
            username=user.username,
            password=user.password,
            is_superuser=True,
            is_active=False
        )"""

content = content.replace(old_reg, new_reg)

old_create = """        # Create the user as superuser
        user.is_superuser = True
        try:
            new_user = create_user(db=db, user=user)"""

new_create = """        # Create the user as superuser
        user.is_superuser = True
        user.is_active = False
        try:
            new_user = create_user(db=db, user=user)"""

content = content.replace(old_create, new_create)

# In finalize, set user back to active
old_finalize = """    if not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA must be enabled to finalize setup.")

    mark_setup_completed(db)"""

new_finalize = """    if not user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA must be enabled to finalize setup.")

    user.is_active = True
    db.commit()

    mark_setup_completed(db)"""

content = content.replace(old_finalize, new_finalize)

with open("backend/api/routers/setup/setup.py", "w") as f:
    f.write(content)
