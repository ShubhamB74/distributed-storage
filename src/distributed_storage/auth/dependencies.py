from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from distributed_storage.api.dependencies import SessionDep, SettingsDep
from distributed_storage.audit.service import AuditService
from distributed_storage.auth.passwords import PasswordVerifier
from distributed_storage.auth.service import AuthService, authenticate_token, unauthorized
from distributed_storage.auth.tokens import MAX_TOKEN_LENGTH
from distributed_storage.authz.principal import Principal

# auto_error=False: missing or non-bearer credentials become our uniform 401 body.
_bearer = HTTPBearer(auto_error=False)


async def get_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    if len(credentials.credentials) > MAX_TOKEN_LENGTH:
        raise unauthorized()
    principal = await authenticate_token(session, credentials.credentials)
    if principal is None:
        raise unauthorized()
    return principal


def get_auth_service(request: Request, session: SessionDep, settings: SettingsDep) -> AuthService:
    state = request.app.state
    verifier: PasswordVerifier = state.password_verifier
    audit: AuditService = state.audit
    return AuthService(session=session, settings=settings, verifier=verifier, audit=audit)


PrincipalDep = Annotated[Principal, Depends(get_principal)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
