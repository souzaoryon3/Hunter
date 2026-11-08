"""Compatibilidade dos imports antigos; seguranca em backend.security."""
from backend.security import (SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    pwd_context, oauth2_scheme, get_password_hash, verify_password,
    create_access_token, get_current_user)
