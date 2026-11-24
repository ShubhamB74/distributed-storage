"""Registration, login, logout and bearer-token authentication (ADR-0011, D16, D17)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from distributed_storage.api.errors import ApiError
from distributed_storage.audit.service import AuditAction, AuditEntry, AuditService, Outcome
from distributed_storage.auth.lockout import lockout_seconds
from distributed_storage.auth.passwords import AUTH_SCHEME, PasswordVerifier
from distributed_storage.auth.tokens import generate_token, hash_token
from distributed_storage.authz.principal import Principal
from distributed_storage.core.config import Settings
from distributed_storage.db.models import Device, User
from distributed_storage.db.models import Session as SessionModel

# last_used_at / last_seen_at are refreshed at most this often, to avoid a write per request.
TOUCH_INTERVAL = timedelta(seconds=60)


def invalid_credentials() -> ApiError:
    # One response for unknown account, wrong secret, disabled account and locked account.
    return ApiError(401, "invalid_credentials", "invalid email or secret")


def unauthorized() -> ApiError:
    return ApiError(
        401,
        "unauthorized",
        "authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    expires_at: datetime
    device_id: uuid.UUID


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        verifier: PasswordVerifier,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._verifier = verifier
        self._audit = audit

    async def register(self, *, email: str, auth_secret: str) -> uuid.UUID:
        if not self._settings.allow_registration:
            raise ApiError(403, "registration_disabled", "registration is disabled")
        verifier = await self._verifier.hash(auth_secret)
        user = User(email=email, auth_scheme=AUTH_SCHEME, auth_verifier=verifier)
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            raise ApiError(
                409, "email_taken", "an account with this email already exists"
            ) from None
        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.USER_REGISTERED,
                resource_type="user",
                outcome=Outcome.SUCCESS,
                actor_user_id=user.id,
                resource_id=str(user.id),
            ),
        )
        await self._session.commit()
        return user.id

    async def login(self, *, email: str, auth_secret: str, device_name: str) -> LoginResult:
        now = datetime.now(UTC)
        user = await self._session.scalar(select(User).where(User.email == email))

        refusal = self._refusal_reason(user, now)
        if user is None or refusal is not None:
            await self._verifier.verify_dummy(auth_secret)
            await self._audit_login_failure(user, refusal or "unknown_account")
            raise invalid_credentials()

        if not await self._verifier.verify(user.auth_verifier, auth_secret):
            await self._record_failed_attempt(user.id, now)
            await self._audit_login_failure(user, "wrong_secret")
            raise invalid_credentials()

        await self._reset_failures(user, auth_secret)
        device = await self._device_for_login(user.id, device_name, now)

        token = generate_token()
        expires_at = now + timedelta(minutes=self._settings.session_ttl_minutes)
        self._session.add(
            SessionModel(
                user_id=user.id,
                device_id=device.id,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.AUTH_LOGIN,
                resource_type="session",
                outcome=Outcome.SUCCESS,
                actor_user_id=user.id,
                device_id=device.id,
            ),
        )
        await self._session.commit()
        return LoginResult(access_token=token, expires_at=expires_at, device_id=device.id)

    async def logout(self, principal: Principal) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.id == principal.session_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.AUTH_LOGOUT,
                resource_type="session",
                outcome=Outcome.SUCCESS,
                actor_user_id=principal.user_id,
                device_id=principal.device_id,
                resource_id=str(principal.session_id),
            ),
        )
        await self._session.commit()

    @staticmethod
    def _refusal_reason(user: User | None, now: datetime) -> str | None:
        if user is None:
            return "unknown_account"
        if user.status != "active":
            return "account_disabled"
        if user.locked_until is not None and user.locked_until > now:
            return "account_locked"
        return None

    async def _audit_login_failure(self, user: User | None, reason: str) -> None:
        await self._audit.record_independent(
            AuditEntry(
                action=AuditAction.AUTH_LOGIN,
                resource_type="session",
                outcome=Outcome.FAILURE,
                actor_user_id=user.id if user is not None else None,
                details={"reason": reason},
            )
        )

    async def _record_failed_attempt(self, user_id: uuid.UUID, now: datetime) -> None:
        count = (
            await self._session.execute(
                update(User)
                .where(User.id == user_id)
                .values(failed_login_count=User.failed_login_count + 1, updated_at=func.now())
                .returning(User.failed_login_count)
            )
        ).scalar_one()
        seconds = lockout_seconds(
            count,
            max_failures=self._settings.login_max_failures,
            base_seconds=self._settings.login_lockout_base_seconds,
            max_seconds=self._settings.login_lockout_max_seconds,
        )
        if seconds > 0:
            await self._session.execute(
                update(User)
                .where(User.id == user_id)
                .values(locked_until=now + timedelta(seconds=seconds))
            )
        await self._session.commit()

    async def _reset_failures(self, user: User, auth_secret: str) -> None:
        values: dict[str, object] = {}
        if user.failed_login_count or user.locked_until is not None:
            values.update(failed_login_count=0, locked_until=None)
        if self._verifier.needs_rehash(user.auth_verifier):
            values["auth_verifier"] = await self._verifier.hash(auth_secret)
        if values:
            await self._session.execute(
                update(User).where(User.id == user.id).values(updated_at=func.now(), **values)
            )

    async def _device_for_login(self, user_id: uuid.UUID, name: str, now: datetime) -> Device:
        device = await self._find_device(user_id, name)
        if device is None:
            candidate = Device(user_id=user_id, name=name, last_seen_at=now)
            try:
                async with self._session.begin_nested():
                    self._session.add(candidate)
            except IntegrityError:  # a concurrent login created it first
                device = await self._find_device(user_id, name)
            else:
                device = candidate
        if device is None:
            raise ApiError(409, "device_conflict", "could not register the device, try again")
        if device.revoked_at is not None:
            raise ApiError(
                403, "device_revoked", "this device name was revoked, choose another device name"
            )
        device.last_seen_at = now
        return device

    async def _find_device(self, user_id: uuid.UUID, name: str) -> Device | None:
        return await self._session.scalar(
            select(Device).where(Device.user_id == user_id, Device.name == name)
        )


async def authenticate_token(session: AsyncSession, token: str) -> Principal | None:
    """Resolve a bearer token to a principal, or None if it is invalid, expired or revoked."""
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(SessionModel, Device, User)
            .join(Device, SessionModel.device_id == Device.id)
            .join(User, SessionModel.user_id == User.id)
            .where(SessionModel.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        return None
    stored_session, device, user = row
    if (
        stored_session.revoked_at is not None
        or stored_session.expires_at <= now
        or device.revoked_at is not None
        or user.status != "active"
    ):
        return None

    last_used = stored_session.last_used_at
    if last_used is None or now - last_used > TOUCH_INTERVAL:
        await session.execute(
            update(SessionModel)
            .where(SessionModel.id == stored_session.id)
            .values(last_used_at=now)
        )
        await session.execute(update(Device).where(Device.id == device.id).values(last_seen_at=now))
        await session.commit()
    return Principal(user_id=user.id, device_id=device.id, session_id=stored_session.id)
