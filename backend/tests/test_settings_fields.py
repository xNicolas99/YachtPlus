"""Sanity tests for Settings fields that were referenced in code but
previously never declared on the Pydantic model. With extra='forbid',
reading an undeclared attribute crashes with AttributeError — these
tests catch regressions where someone adds a settings.* reference and
forgets to declare the field.
"""
from api.settings import Settings


def test_compose_dir_is_declared_and_has_trailing_slash_default():
    s = Settings()
    assert hasattr(s, "COMPOSE_DIR")
    # Call sites do `settings.COMPOSE_DIR + name`, so a trailing separator
    # is part of the contract.
    assert s.COMPOSE_DIR.endswith("/") or s.COMPOSE_DIR.endswith("\\")


def test_docker_host_is_declared_as_optional():
    s = Settings()
    assert hasattr(s, "DOCKER_HOST")
    # Default is None unless env var is set; aiodocker / docker.from_env
    # handle that fall-through.
    # (We don't assert the value because tests may run with DOCKER_HOST in env.)


def test_trusted_proxies_is_declared_and_iterable():
    s = Settings()
    assert hasattr(s, "TRUSTED_PROXIES")
    # Either explicitly set or empty list; the security layer iterates it.
    assert isinstance(s.TRUSTED_PROXIES, list)


def test_compose_dir_respects_env(monkeypatch):
    monkeypatch.setenv("COMPOSE_DIR", "/tmp/compose-test/")
    s = Settings()
    assert s.COMPOSE_DIR == "/tmp/compose-test/"
