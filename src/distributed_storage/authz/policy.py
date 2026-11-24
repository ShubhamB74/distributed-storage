"""Central, deny-by-default authorization, independent of authentication.

``authorize`` knows nothing about tokens or sessions: it takes an already-established
principal, an action and the resource, and answers yes or no. Phase 1 has one rule: owners
may act on their own resources. Phase 5 extends this with grants.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from distributed_storage.authz.principal import Principal


class Action(StrEnum):
    FILE_CREATE = "file:create"
    FILE_LIST = "file:list"
    FILE_READ = "file:read"
    FILE_WRITE_CONTENT = "file:write_content"
    DEVICE_LIST = "device:list"
    DEVICE_REVOKE = "device:revoke"


@dataclass(frozen=True, slots=True)
class Resource:
    """What is being acted on. ``owner_id`` is the owner of the existing row (for collection
    actions and creation, the principal's own id)."""

    kind: str
    owner_id: uuid.UUID | None


_OWNER_ACTIONS: frozenset[Action] = frozenset(Action)


def authorize(principal: Principal, action: Action, resource: Resource) -> bool:
    if action not in _OWNER_ACTIONS:
        return False
    if resource.owner_id is None:
        return False
    return resource.owner_id == principal.user_id
