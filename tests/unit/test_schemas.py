import base64

import pytest
from pydantic import ValidationError

from distributed_storage.auth.schemas import LoginRequest, RegisterRequest
from distributed_storage.files.schemas import MAX_METADATA_BYTES, CreateFileRequest

SECRET = "a-sufficiently-long-secret"


def test_email_is_trimmed_and_lower_cased() -> None:
    request = RegisterRequest(email="  Alice@Example.COM ", auth_secret=SECRET)
    assert request.email == "alice@example.com"


@pytest.mark.parametrize("email", ["no-at-sign", "a@b", "a b@c.de", "@x.io", "x@.io "])
def test_invalid_emails_are_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email=email, auth_secret=SECRET)


@pytest.mark.parametrize("secret", ["", "short", "x" * 15, "x" * 1025])
def test_auth_secret_length_is_bounded(secret: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", auth_secret=secret)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate({"email": "a@b.co", "auth_secret": SECRET, "role": "admin"})


def test_login_device_name_is_trimmed_and_checked() -> None:
    request = LoginRequest(email="a@b.co", auth_secret=SECRET, device_name="  my laptop ")
    assert request.device_name == "my laptop"
    for bad in ["   ", "tab\there", "nul\x00byte", "x" * 65]:
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.co", auth_secret=SECRET, device_name=bad)


def _envelope(size: int) -> str:
    return base64.b64encode(b"x" * size).decode()


def test_create_file_request_decodes_the_metadata_envelope() -> None:
    request = CreateFileRequest.model_validate(
        {"metadata_format": "dev-plain-v0", "metadata_envelope": _envelope(5), "size_bytes": 10}
    )
    assert request.metadata_envelope == b"xxxxx"


@pytest.mark.parametrize(
    "payload",
    [
        {"metadata_format": "other", "metadata_envelope": _envelope(5), "size_bytes": 10},
        {"metadata_format": "dev-plain-v0", "metadata_envelope": "!!!not-base64", "size_bytes": 10},
        {"metadata_format": "dev-plain-v0", "metadata_envelope": "", "size_bytes": 10},
        {
            "metadata_format": "dev-plain-v0",
            "metadata_envelope": _envelope(MAX_METADATA_BYTES + 1),
            "size_bytes": 10,
        },
        {"metadata_format": "dev-plain-v0", "metadata_envelope": _envelope(5), "size_bytes": 0},
        {"metadata_format": "dev-plain-v0", "metadata_envelope": 123, "size_bytes": 10},
    ],
)
def test_invalid_create_file_requests_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CreateFileRequest.model_validate(payload)


def test_the_envelope_cap_is_inclusive() -> None:
    request = CreateFileRequest.model_validate(
        {
            "metadata_format": "dev-plain-v0",
            "metadata_envelope": _envelope(MAX_METADATA_BYTES),
            "size_bytes": 1,
        }
    )
    assert len(request.metadata_envelope) == MAX_METADATA_BYTES
