from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

import veridra.application_identity as identity_module


class _UnexpectedDependency:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Hosted session/password dependency initialized in operator mode.")


def test_operator_identity_skips_hosted_session_and_password_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "identity.sqlite3"
    monkeypatch.setenv("VERIDRA_ENV", "operator")
    monkeypatch.setenv("VERIDRA_IDENTITY_DB", str(database))
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8010")
    monkeypatch.setenv("VERIDRA_BIND_HOST", "127.0.0.1")

    monkeypatch.setattr(identity_module, "SQLitePasswordAuthenticator", _UnexpectedDependency)
    monkeypatch.setattr(identity_module, "SQLiteLoginThrottle", _UnexpectedDependency)
    monkeypatch.setattr(identity_module, "SQLitePasswordRecoveryThrottle", _UnexpectedDependency)
    monkeypatch.setattr(identity_module, "SecureSessionCookieExtractor", _UnexpectedDependency)
    monkeypatch.setattr(identity_module, "ServerSideSessionIdentityAdapter", _UnexpectedDependency)

    app = FastAPI()

    assert identity_module.configure_identity_middleware(app) is True
    assert app.state.veridra_identity_database == database.resolve()
    assert isinstance(
        app.state.veridra_identity_store,
        identity_module.SQLiteIdentityRecordStore,
    )
    assert not hasattr(app.state, "veridra_password_authenticator")
    assert not hasattr(app.state, "veridra_login_throttle")
    assert not hasattr(app.state, "veridra_password_recovery_throttle")

    middleware = next(
        item
        for item in app.user_middleware
        if item.cls is identity_module.VerifiedIdentityMiddleware
    )
    assert isinstance(
        middleware.kwargs["adapter"],
        identity_module._LocalOperatorIdentityAdapter,
    )
