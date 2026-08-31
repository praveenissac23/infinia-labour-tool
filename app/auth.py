"""
Authentication - password hashing and JWT session tokens. The desktop
app never needed this at all (whoever sits at the PC has full access);
a multi-staff web app genuinely does, since not everyone should
necessarily be able to edit Master Data or salary adjustments.
"""
import os
import bcrypt
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
import models

# In production this MUST come from an environment variable, never
# hardcoded - this default is for local dev/testing only.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours - a staff member's typical work session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Uses the bcrypt library directly rather than passlib's CryptContext
# wrapper - confirmed directly as a real, current compatibility bug:
# passlib's own bcrypt version-detection code crashes against bcrypt
# 4.x/5.x (which removed the __about__ attribute passlib's detection
# relies on), so hashing failed outright. bcrypt itself works fine.
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_download_token(username: str) -> str:
    """
    A separate, short-lived token (60 seconds) scoped only to file
    downloads - used instead of the main 12-hour login token for URLs
    that get passed via a query string (export/backup links, which
    can't carry an Authorization header since they're opened by a
    plain browser navigation, not a fetch() call). Query-string tokens
    can end up in browser history, screen shares, or server access
    logs; if the real 12-hour session token were used there, anyone
    who saw that URL could reuse it - not just for downloads, but for
    any API call, for hours. Scoping it and expiring it in a minute
    closes that off.
    """
    expire = datetime.utcnow() + timedelta(seconds=60)
    return jwt.encode({"sub": username, "scope": "download", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_download_user_from_token(token: str, db: Session) -> models.User:
    """Validates a create_download_token() token specifically - rejects
    a normal login token even if it's otherwise valid, so a leaked
    download URL can only ever be used for the one thing it was
    issued for, for the one minute it's valid."""
    credentials_exception = HTTPException(status_code=401, detail="Invalid or expired download link.")
    # A link with no token at all, or a mangled one, must be refused the
    # same way an expired one is. Passing None into the decoder raised a
    # different error and surfaced as a 500 - a broken link looked like a
    # broken server.
    if not token or not isinstance(token, str):
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "download":
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None or payload.get("scope") == "download":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def get_user_from_token_string(token: str, db: Session) -> models.User:
    """Same validation as get_current_user, but takes a raw token string
    directly rather than pulling it from the Authorization header - used
    for the export endpoints specifically, which need to work via a
    plain browser navigation (window.open(url)), not a fetch() call.
    A direct navigation can't set custom headers, so the token travels
    as a query parameter there instead; this lets that same JWT still
    go through the exact same validation either way."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="This action requires admin access.")
    return user
