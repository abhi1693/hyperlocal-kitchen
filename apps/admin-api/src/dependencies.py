"""Shared dependencies for the independently deployed platform-admin API."""

from typing import Annotated

from fastapi import Depends
from kitchen_core.auth_schemas import AdminPrincipal
from kitchen_core.db import get_session
from kitchen_http.auth import require_admin
from sqlalchemy.orm import Session

DB = Annotated[Session, Depends(get_session, scope="function")]
Admin = Annotated[AdminPrincipal, Depends(require_admin)]
