from fastapi import APIRouter, Response

from distributed_storage.auth.dependencies import AuthServiceDep, PrincipalDep
from distributed_storage.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, service: AuthServiceDep) -> RegisterResponse:
    user_id = await service.register(email=body.email, auth_secret=body.auth_secret)
    return RegisterResponse(user_id=user_id)


@router.post("/login")
async def login(body: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    result = await service.login(
        email=body.email, auth_secret=body.auth_secret, device_name=body.device_name
    )
    return TokenResponse(
        access_token=result.access_token,
        expires_at=result.expires_at,
        device_id=result.device_id,
    )


@router.post("/logout", status_code=204)
async def logout(principal: PrincipalDep, service: AuthServiceDep) -> Response:
    await service.logout(principal)
    return Response(status_code=204)
