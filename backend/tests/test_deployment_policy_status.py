"""The settings UI must describe the current durable access policy."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routers import app_settings


def configuration(path):
    return SimpleNamespace(
        ACCESS_POLICY_FILE=str(path), BLOCK_PUBLIC_IP_LOGIN=True,
        SECURE_COOKIES=True, TRUSTED_PROXIES=["127.0.0.1", "::1"],
        ALLOWED_HOSTS=["localhost"], CORS_ORIGINS=[], ENVIRONMENT="production",
        DISABLE_AUTH=False, ALLOW_PRIVATE_NETWORK_HOSTS=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_public,expected", [(False, "local"), (True, "public")])
async def test_status_reads_current_policy_after_ui_change(tmp_path, monkeypatch, allow_public, expected):
    policy = tmp_path / "access-policy.json"
    policy.write_text(json.dumps({"allow_public": allow_public}), encoding="utf-8")
    monkeypatch.setattr(app_settings, "settings", configuration(policy))
    monkeypatch.setattr(app_settings, "auth_check", AsyncMock())
    result = await app_settings.get_deployment_status(Authorize=object())
    assert result["mode"] == expected


@pytest.mark.asyncio
async def test_unreadable_policy_never_reports_safe_local_status(tmp_path, monkeypatch):
    policy = tmp_path / "access-policy.json"
    policy.write_text("invalid", encoding="utf-8")
    monkeypatch.setattr(app_settings, "settings", configuration(policy))
    monkeypatch.setattr(app_settings, "auth_check", AsyncMock())
    with pytest.raises(HTTPException) as error:
        await app_settings.get_deployment_status(Authorize=object())
    assert error.value.status_code == 503
