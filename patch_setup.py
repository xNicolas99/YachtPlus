import re

with open("backend/api/routers/setup/setup.py", "r") as f:
    content = f.read()

# Fix the bypass route
old_bypass = """@router.post("/bypass")
def bypass_setup(db: Session = Depends(get_db)):
    if is_setup_completed(db):
        return {"message": "Setup already completed or bypassed."}

    status = db.query(SetupStatus).first()"""

new_bypass = """@router.post("/bypass")
def bypass_setup(db: Session = Depends(get_db)):
    if is_setup_completed(db):
        return {"message": "Setup already completed or bypassed."}

    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Cannot bypass setup after a user has been registered.")

    status = db.query(SetupStatus).first()"""

content = content.replace(old_bypass, new_bypass)

# Ensure cookie is set
# Note: I already updated update_setup.py to set the cookie, but let's make sure it's correct.
old_cookie_code = """    access_token = create_access_token(data={"sub": new_user.username})
    Authorize.set_access_cookies(access_token, response)

    return {"""

new_cookie_code = """    access_token = create_access_token(data={"sub": new_user.username})
    Authorize.set_access_cookies(access_token, response)

    return {"""

# If it wasn't replaced properly before, let's just do a robust regex
content = re.sub(r'    access_token = create_access_token\(data=\{"sub": new_user\.username\}\)\n\n    return \{',
                 r'    access_token = create_access_token(data={"sub": new_user.username})\n    Authorize.set_access_cookies(access_token, response)\n\n    return {',
                 content)

with open("backend/api/routers/setup/setup.py", "w") as f:
    f.write(content)
