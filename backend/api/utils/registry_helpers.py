"""Shared helpers for parsing container image references in a CodeQL-safe way.

CodeQL's py/incomplete-url-substring-sanitization query flags raw string
prefix checks such as ``name.startswith("ghcr.io/")`` as potentially unsafe.
These functions use :mod:`urllib.parse` to inspect only the hostname portion
of a reference and never rely on substring matching for security decisions.
"""

from urllib.parse import urlparse


def get_registry_and_name(image_name: str):
    """Return ``(registry, repo_name)`` for a container image reference.

    The reference may contain a registry host prefix or be a plain short
    name such as ``nginx`` or ``linuxserver/plex``.

    Recognised registry hosts:
      - docker.io / index.docker.io  -> ``dockerhub``
      - ghcr.io                      -> ``ghcr``
      - lscr.io                      -> ``linuxserver``

    Anything without an explicit host is treated as ``dockerhub``.

    Examples
    --------
    >>> get_registry_and_name("nginx")
    ('dockerhub', 'nginx')
    >>> get_registry_and_name("ghcr.io/linuxserver/plex")
    ('ghcr', 'linuxserver/plex')
    >>> get_registry_and_name("lscr.io/linuxserver/plex")
    ('linuxserver', 'linuxserver/plex')
    >>> get_registry_and_name("https://ghcr.io/linuxserver/plex")
    ('ghcr', 'linuxserver/plex')
    """
    # urlparse treats bare strings as paths; give it a pseudo scheme so the
    # first component becomes the netloc if one is present.
    if "://" in image_name:
        parsed = urlparse(image_name)
        hostname = (parsed.hostname or "").lower()
        remainder = parsed.path.lstrip("/")
    else:
        # Add a fake scheme to turn "ghcr.io/foo" into netloc=ghcr.io path=/foo
        parsed = urlparse(f"docker://{image_name}")
        hostname = (parsed.hostname or "").lower()
        remainder = parsed.path.lstrip("/")

    if hostname in ("docker.io", "index.docker.io"):
        return "dockerhub", remainder
    if hostname == "ghcr.io":
        return "ghcr", remainder
    if hostname == "lscr.io":
        return "linuxserver", remainder

    # No explicit registry host -> Docker Hub short name.
    return "dockerhub", image_name


def drop_registry_prefix(image_name: str) -> str:
    """Return the repository name with any recognised registry host removed."""
    _, remainder = get_registry_and_name(image_name)
    return remainder
