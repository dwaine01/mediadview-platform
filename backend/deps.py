"""Shared FastAPI dependencies: authentication and RBAC gates.

Extracted from server.py (Fase 2A of the modularization plan - see
docs/AGENT_COORDINATION.md and docs/REFACTOR_FASE2_PLAN.md). Every
domain router that needs Depends(get_current_user), Depends(require_admin)
or Depends(require_superadmin) can now import them directly from here
instead of receiving them as factory parameters threaded through server.py
(the pattern already used by create_workspace_routes(db, get_current_user,
require_admin, bump_playlist_version, ...) - this is exactly the kind of
6-8 parameter factory the plan calls out as painful).

Pure relocation: same JWT decoding logic, same env vars, same RBAC checks,
same behavior. server.py imports these at module level
(from deps import get_current_user, require_admin, require_superadmin)
so server.get_current_user etc. keep working unchanged for existing
callers (permissions.py's lazy 'from server import get_current_user',
tests that do 'from server import ...').
"""
import logging
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import db
from rbac import Role, get_effective_role

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    if os.environ.get('ENVIRONMENT', 'development') == 'production':
        raise RuntimeError("JWT_SECRET must be set in production")
    JWT_SECRET = 'mediaview-dev-only-secret-do-not-deploy'
    logging.getLogger("server").warning("Using dev JWT_SECRET fallback — NOT for production")
JWT_ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Legacy decoder that ALSO accepts Auth v2 tokens (aud/iss/typ) for compat.
    Tries v2 first (with audience/issuer verification), falls back to v1 (no aud/iss).

    SEC-002 fix: Legacy tokens now also validate session_epoch to honour revocation
    (password change, logout, role change all bump epoch → old tokens rejected).
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token = credentials.credentials
        is_v2_token = False
        try:
            # v2 tokens carry aud/iss and must be verified — do that first.
            payload = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                audience=os.environ.get("JWT_AUDIENCE", "mediadview-frontend"),
                issuer=os.environ.get("JWT_ISSUER", "mediadview-api"),
            )
            is_v2_token = True
        except jwt.InvalidTokenError:
            # v1 legacy tokens: no aud/iss claims → decode without verification of those.
            payload = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                options={"verify_aud": False, "verify_iss": False},
            )
        user_id = payload.get("sub")
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=401, detail="User not found", headers={"WWW-Authenticate": "Bearer"})
        if not user.get("active", True):
            raise HTTPException(status_code=401, detail="Account deactivated", headers={"WWW-Authenticate": "Bearer"})
        # SEC-002: enforce session epoch on LEGACY tokens so that password-change /
        # logout / role revocation invalidates all outstanding legacy access tokens.
        # v2 tokens already carry 'ver' and are validated inside auth_v2 decoder.
        if not is_v2_token:
            token_ver = payload.get("ver", 0)
            db_epoch  = user.get("session_epoch", 0)
            if token_ver < db_epoch:
                raise HTTPException(status_code=401,
                                    detail="Session revoked — please login again",
                                    headers={"WWW-Authenticate": "Bearer"})
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired", headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})


async def require_admin(current_user: dict = Depends(get_current_user)):
    """RBAC-aware gate: accepts SUPER_ADMIN, MEDIAVIEW_ADMIN and SUPPORT roles.
    Legacy role strings ('admin', 'superadmin') are automatically mapped via ROLE_MIGRATION_MAP."""
    role = get_effective_role(current_user)
    if role not in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def require_superadmin(current_user: dict = Depends(get_current_user)):
    """RBAC-aware gate: only SUPER_ADMIN passes.
    Legacy role string 'superadmin' is mapped automatically."""
    role = get_effective_role(current_user)
    if role != Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return current_user
