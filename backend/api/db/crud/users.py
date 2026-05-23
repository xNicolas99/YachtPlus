from sqlalchemy.orm import Session
from sqlalchemy import func
import bcrypt
from api.db.models import users as models
from api.db.models.settings import TokenBlacklist
from api.db.schemas import users as schemas
from api.settings import Settings
from fastapi.exceptions import HTTPException
from datetime import datetime
from api.auth.jwt import create_access_token

settings = Settings()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_name(db: Session, username: str):
    return (
        db.query(models.User)
        .filter(models.User.username == username.casefold())
        .first()
    )


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def _normalize_username(username: str) -> str:
    """Canonical, case-folded username used at every write site.

    Login + permission lookups query via ``username.casefold()`` already, so
    a stored mixed-case username is unreachable through normal auth. That
    asymmetry was the lock-out vector for the case-squat attack — fix it by
    storing the same canonical form everywhere.
    """
    if username is None:
        return username
    return username.strip().casefold()


def _username_is_taken(db: Session, username: str, *, excluding_id: int = None) -> bool:
    """Case-insensitive existence check that ignores ``excluding_id`` so an
    admin updating an existing user doesn't collide with that user's own row.

    Compares ``LOWER(stored_username) == canonical(input)`` so legacy rows
    that were persisted before this normalization existed (mixed-case
    usernames left over from the early setup wizard) still match — that's
    exactly the lock-out vector this guard exists to close.
    """
    canonical = _normalize_username(username)
    q = db.query(models.User).filter(func.lower(models.User.username) == canonical)
    if excluding_id is not None:
        q = q.filter(models.User.id != excluding_id)
    return q.first() is not None


def create_user(db: Session, user: schemas.UserCreate):
    _hashed_password = get_password_hash(user.password)
    canonical_username = _normalize_username(user.username)

    # Defence-in-depth case-insensitive collision check. The DB still has the
    # UNIQUE constraint, but checking here gives us a clean 400 instead of
    # leaking IntegrityError-shaped detail strings.
    if _username_is_taken(db, canonical_username):
        raise HTTPException(status_code=409, detail="Username already in use.")

    db_user = models.User(
        username=canonical_username,
        hashed_password=_hashed_password,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        perm_start=user.perm_start,
        perm_stop=user.perm_stop,
        perm_restart=user.perm_restart,
        perm_delete=user.perm_delete
    )
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
    except Exception as exc:
        # Without a rollback the session stays in a failed-transaction state
        # and every subsequent query in this request raises InvalidRequestError.
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not create user: {exc}")
    return db_user


def update_user(db: Session, user: schemas.UserUpdate, current_user):
    # current_user here is a STRING (username) from jwt subject
    # unless called with user object.
    # The router passes current_user as string usually.
    # But wait, `update_user_admin` in router might pass something else?
    # Let's clarify usage.
    # Standard user self-update: `current_user` is their username.
    # Admin update: we are updating a specific user object/ID.

    # This function seems designed for "self update" primarily or generic update if `current_user` is the user to be updated?
    # Original code: `_user = get_user_by_name(db=db, username=current_user)`
    # This implies it updates the user WHO IS LOGGED IN.

    # We need a separate function or logic for Admin updating OTHER users.

    _hashed_password = get_password_hash(user.password) if user.password else None
    _user = get_user_by_name(db=db, username=current_user)

    if _user and _user.is_active:
        if user.username:
            new_canonical = _normalize_username(user.username)
            if new_canonical != _user.username.casefold():
                # Reject if another row already owns the canonical name —
                # otherwise an attacker could squat a case-variant of
                # someone else's username and starve their login lookup.
                if _username_is_taken(db, new_canonical, excluding_id=_user.id):
                    raise HTTPException(
                        status_code=409, detail="Username already in use."
                    )
                _user.username = new_canonical

        if user.password:
            _user.hashed_password = _hashed_password

        try:
            db.add(_user)
            db.commit()
            db.refresh(_user)
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        return _user

def update_user_by_id(db: Session, user_id: int, user_update: schemas.UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None

    if user_update.username:
        new_canonical = _normalize_username(user_update.username)
        if _username_is_taken(db, new_canonical, excluding_id=db_user.id):
            raise HTTPException(status_code=409, detail="Username already in use.")
        db_user.username = new_canonical
    if user_update.password:
        db_user.hashed_password = get_password_hash(user_update.password)

    # Update permissions if provided
    if user_update.is_active is not None:
        db_user.is_active = user_update.is_active
    if user_update.is_superuser is not None:
        db_user.is_superuser = user_update.is_superuser
    if user_update.perm_start is not None:
        db_user.perm_start = user_update.perm_start
    if user_update.perm_stop is not None:
        db_user.perm_stop = user_update.perm_stop
    if user_update.perm_restart is not None:
        db_user.perm_restart = user_update.perm_restart
    if user_update.perm_delete is not None:
        db_user.perm_delete = user_update.perm_delete

    try:
        db.commit()
        db.refresh(db_user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username already in use or database error")
    return db_user

def verify_password(plain_password, hashed_password):
    # bcrypt requires bytes
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')

    return bcrypt.checkpw(plain_password, hashed_password)


def get_password_hash(password):
    if isinstance(password, str):
        password = password.encode('utf-8')

    # gensalt default rounds is 12
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    return hashed.decode('utf-8')


def prune_blacklist(db: Session):
    expired_list = []
    db.query(TokenBlacklist).filter(TokenBlacklist.expires < datetime.utcnow()).delete()
    db.commit()
    return


def blacklist_api_key(key_id, db: Session, requesting_user=None):
    """Revoke and delete an API key.

    If ``requesting_user`` is given, the key is only removed when it belongs
    to that user or the requester is a superuser. This prevents an IDOR
    where any authenticated user could pass an arbitrary key_id and delete
    another account's API token.
    """
    key = db.query(models.APIKEY).filter(models.APIKEY.id == key_id).first()
    if not key:
        return {"error": "Key not found"}

    if requesting_user is not None:
        is_owner = key.user == requesting_user.id
        is_admin = bool(getattr(requesting_user, "is_superuser", False))
        if not (is_owner or is_admin):
            # Surface as 404 rather than 403 so we don't leak the fact that
            # the key id exists for some other account.
            return {"error": "Key not found"}

    access = TokenBlacklist(jti=key.jti, expires=None, revoked=True)
    db.add(access)
    db.delete(key)
    db.commit()
    return {"success": "api key " + str(key_id) + " deleted."}


def get_keys(user, db: Session):
    keys = db.query(models.APIKEY).filter(models.APIKEY.user == user.id).all()
    return keys


def create_key(key_name, user, Authorize, db: Session):
    # Use our custom create_access_token from api.auth.jwt
    # Note: create_access_token returns the encoded string.
    # We need JTI. Our custom implementation puts username in 'sub'.
    # It doesn't generate a JTI by default unless we add it.
    # To support blacklisting, we should add JTI.

    import uuid
    jti = str(uuid.uuid4())

    # We create a long-lived token (or infinite if expires_delta is large)
    # Original used expires_time=False.
    # Our create_access_token uses default 15 mins if not provided.
    from datetime import timedelta
    # 10 years expiration for API key effectively
    expires = timedelta(days=365*10)

    api_key = create_access_token(
        data={"sub": user.username, "jti": jti},
        expires_delta=expires
    )

    _hashed_key = get_password_hash(api_key)

    db_key = models.APIKEY(
        key_name=key_name, user=user.id, hashed_key=_hashed_key, jti=jti
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    db_key.token = api_key
    return db_key.__dict__
