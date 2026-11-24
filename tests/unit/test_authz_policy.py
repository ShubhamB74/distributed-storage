import uuid
from typing import cast

import pytest

from distributed_storage.authz.policy import Action, Resource, authorize
from distributed_storage.authz.principal import Principal


def _principal() -> Principal:
    return Principal(user_id=uuid.uuid4(), device_id=uuid.uuid4(), session_id=uuid.uuid4())


@pytest.mark.parametrize("action", list(Action))
def test_owner_is_allowed_every_action_on_their_own_resource(action: Action) -> None:
    principal = _principal()
    assert authorize(principal, action, Resource("any", principal.user_id)) is True


@pytest.mark.parametrize("action", list(Action))
def test_other_users_are_denied_every_action(action: Action) -> None:
    assert authorize(_principal(), action, Resource("any", uuid.uuid4())) is False


@pytest.mark.parametrize("action", list(Action))
def test_resources_without_an_owner_are_denied(action: Action) -> None:
    assert authorize(_principal(), action, Resource("any", None)) is False


def test_unknown_actions_are_denied_by_default() -> None:
    principal = _principal()
    unknown = cast(Action, "file:destroy")
    assert authorize(principal, unknown, Resource("file", principal.user_id)) is False


def test_the_device_or_session_of_a_principal_does_not_grant_ownership() -> None:
    principal = _principal()
    resource = Resource("file", principal.device_id)  # owner id equal to the device id
    assert authorize(principal, Action.FILE_READ, resource) is False
