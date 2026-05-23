import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from api.routers.search import search


class MockAuthValid:
    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return "admin"


class MockAuthInvalid:
    def jwt_required(self, allow_setup_pending=False):
        raise HTTPException(status_code=401, detail="Unauthorized")


@pytest.fixture
def mock_auth_enabled(monkeypatch):
    monkeypatch.setattr("api.auth.auth.settings.DISABLE_AUTH", False)


def _template_orm(**kwargs):
    """Create an object that exposes attributes like a Template ORM row."""
    defaults = {
        "id": 1,
        "title": "Demo",
        "name": "demo",
        "description": "desc",
        "image": "demo:latest",
        "logo": "logo.png",
        "url": "http://example.com/template.json",
    }
    defaults.update(kwargs)
    obj = MagicMock()
    for key, value in defaults.items():
        setattr(obj, key, value)
    return obj


@pytest.mark.asyncio
async def test_search_returns_dockerhub_and_templates(mock_auth_enabled):
    docker_results = [{"name": "nginx", "description": "web server"}]
    template_orm = [_template_orm(id=1, title="Nginx", name="nginx")]

    db = MagicMock()
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(return_value=docker_results),
    ) as registry_mock, patch(
        "api.routers.search.match_templates",
        return_value=template_orm,
    ) as match_mock:
        result = await search(q="nginx", db=db, Authorize=MockAuthValid())

    registry_mock.assert_awaited_once_with("dockerhub", "nginx")
    match_mock.assert_called_once_with(db, "nginx")

    assert result["dockerhub"] == docker_results
    assert len(result["templates"]) == 1
    assert result["templates"][0]["id"] == 1
    assert result["templates"][0]["title"] == "Nginx"
    assert result["templates"][0]["name"] == "nginx"


@pytest.mark.asyncio
async def test_search_empty_query_results(mock_auth_enabled):
    db = MagicMock()
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(return_value=[]),
    ), patch(
        "api.routers.search.match_templates",
        return_value=[],
    ):
        result = await search(q="zzz", db=db, Authorize=MockAuthValid())

    assert result == {"dockerhub": [], "templates": []}


@pytest.mark.asyncio
async def test_search_template_orm_conversion(mock_auth_enabled):
    db = MagicMock()
    template_orm = [
        _template_orm(
            id=5,
            title="Plex",
            name="plex",
            description="Media server",
            image="linuxserver/plex",
            logo="plex.png",
            url="http://example.com/plex.json",
        )
    ]
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(return_value=[]),
    ), patch(
        "api.routers.search.match_templates",
        return_value=template_orm,
    ):
        result = await search(q="plex", db=db, Authorize=MockAuthValid())

    t = result["templates"][0]
    assert t == {
        "id": 5,
        "title": "Plex",
        "name": "plex",
        "description": "Media server",
        "image": "linuxserver/plex",
        "logo": "plex.png",
        "url": "http://example.com/plex.json",
    }


@pytest.mark.asyncio
async def test_search_unauthorized(mock_auth_enabled):
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await search(q="nginx", db=db, Authorize=MockAuthInvalid())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_search_propagates_registry_failure(mock_auth_enabled):
    db = MagicMock()
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(side_effect=RuntimeError("registry down")),
    ), patch(
        "api.routers.search.match_templates",
        return_value=[],
    ):
        with pytest.raises(RuntimeError) as exc:
            await search(q="nginx", db=db, Authorize=MockAuthValid())
    assert "registry down" in str(exc.value)


@pytest.mark.asyncio
async def test_search_propagates_template_failure(mock_auth_enabled):
    db = MagicMock()
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(return_value=[]),
    ), patch(
        "api.routers.search.match_templates",
        side_effect=RuntimeError("db boom"),
    ):
        with pytest.raises(RuntimeError) as exc:
            await search(q="nginx", db=db, Authorize=MockAuthValid())
    assert "db boom" in str(exc.value)


@pytest.mark.asyncio
async def test_search_runs_template_match_in_threadpool(mock_auth_enabled):
    """match_templates is sync, so the router uses run_in_threadpool.
    Confirm via the threadpool wrapper that the call still flows through.
    """
    db = MagicMock()
    with patch(
        "api.routers.search.registries.search_registry",
        new=AsyncMock(return_value=[]),
    ), patch(
        "api.routers.search.run_in_threadpool",
        new=AsyncMock(return_value=[]),
    ) as run_in_threadpool_mock, patch(
        "api.routers.search.match_templates",
        return_value=[],
    ) as match_mock:
        await search(q="abc", db=db, Authorize=MockAuthValid())

    run_in_threadpool_mock.assert_awaited_once()
    # The first positional argument is the sync function reference
    args, _ = run_in_threadpool_mock.call_args
    assert args[0] is match_mock
    assert args[1] is db
    assert args[2] == "abc"
