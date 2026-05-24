import logging

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from fastapi import HTTPException

from api.db.models import containers as models
from api.utils.templates import conv_sysctls2dict, conv_ports2dict

from datetime import datetime
import http.client
import urllib.request
from urllib.parse import urlparse
import json
import yaml
import os
import socket
import ipaddress

logger = logging.getLogger(__name__)

# Templates

# Maximum wall-clock time the template feed download is allowed to take.
# Without this, urllib falls back to socket.getdefaulttimeout() — which is
# unbounded by default — so a malicious or slow-responding template URL
# could hang the request worker indefinitely.
TEMPLATE_FETCH_TIMEOUT_S = 15

def is_private_ip(ip: str) -> bool:
    if ip == '0.0.0.0':
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast
    except ValueError:
        return False # Invalid IP, treat as public/unsafe

def validate_url(url: str):
    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme not in ('http', 'https'):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: Hostname missing.")

    # Resolve hostname to IPs. Every failure mode must fail CLOSED — a
    # silently-skipped validation here turns the template fetcher into an
    # SSRF gadget against the host network. We previously only caught
    # socket.gaierror, which left socket.timeout / socket.herror / generic
    # OSError as silent fall-throughs to "return True".
    try:
        ip_list = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, socket.herror, socket.timeout, OSError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL: hostname resolution failed ({exc.__class__.__name__}).",
        )

    if not ip_list:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL: hostname did not resolve to any address.",
        )

    for ip_info in ip_list:
        ip = ip_info[4][0]
        if is_private_ip(ip):
            raise HTTPException(status_code=400, detail=f"Access to private IP {ip} is denied.")

    return True


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# --- DNS-rebinding defence -------------------------------------------------
#
# validate_url() resolves the hostname once and rejects private addresses.
# urllib then resolves the hostname a SECOND time inside HTTPConnection.connect,
# leaving a TOCTOU window an attacker who controls DNS can drive at: the first
# answer is a public IP (passes validation), the second is 127.0.0.1 / the
# host's metadata service IP / a sibling container.
#
# The connection classes below re-resolve at connect-time and re-run the
# private-IP check before opening the socket. Failure surfaces as a normal
# OSError so urllib treats it as a transport failure, which the caller's
# except clause maps to a 400.

class _SSRFBlocked(OSError):
    pass


def _check_address_safe(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, socket.herror, socket.timeout, OSError) as exc:
        raise _SSRFBlocked(f"DNS resolution failed for {host!r}: {exc}") from exc
    if not infos:
        raise _SSRFBlocked(f"DNS returned no address for {host!r}")
    for info in infos:
        ip = info[4][0]
        if is_private_ip(ip):
            raise _SSRFBlocked(
                f"Refusing to connect to {host!r}: resolved to private IP {ip}"
            )


class _SSRFGuardedHTTPConnection(http.client.HTTPConnection):
    def connect(self):  # noqa: D401 — overrides stdlib
        _check_address_safe(self.host, self.port or 80)
        super().connect()


class _SSRFGuardedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):  # noqa: D401
        _check_address_safe(self.host, self.port or 443)
        super().connect()


class _SSRFGuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_SSRFGuardedHTTPConnection, req)


class _SSRFGuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_SSRFGuardedHTTPSConnection, req)


def _build_safe_opener():
    """Construct a urllib opener that re-validates DNS at connect time and
    rejects redirects to private addresses."""
    return urllib.request.build_opener(
        SafeRedirectHandler(),
        _SSRFGuardedHTTPHandler(),
        _SSRFGuardedHTTPSHandler(),
    )


def get_templates(db: Session):
    return db.query(models.Template).all()


def get_template(db: Session, url: str):
    return db.query(models.Template).filter(models.Template.url == url).first()


def get_template_by_id(db: Session, id: int):
    return db.query(models.Template).filter(models.Template.id == id).first()


def get_template_items(db: Session, template_id: int):
    return (
        db.query(models.TemplateItem)
        .filter(models.TemplateItem.template_id == template_id)
        .all()
    )

def match_templates(db: Session, query: str):
    return (
        db.query(models.TemplateItem)
        .filter(
            or_(
                models.TemplateItem.title.ilike(f"%{query}%"),
                models.TemplateItem.name.ilike(f"%{query}%"),
                models.TemplateItem.image.ilike(f"%{query}%")
            )
        )
        .limit(20)
        .all()
    )

def delete_template(db: Session, template_id: int):
    _template = (
        db.query(models.Template).filter(models.Template.id == template_id).first()
    )
    db.delete(_template)
    db.commit()
    return _template


def _build_template_item(entry: dict) -> models.TemplateItem:
    """Map one entry from a template feed to a TemplateItem row."""
    return models.TemplateItem(
        type=int(entry.get("type", 1)),
        title=entry["title"],
        platform=entry["platform"],
        description=entry.get("description", ""),
        name=entry.get("name", entry["title"].lower()),
        command=entry.get("command"),
        logo=entry.get("logo", ""),
        image=entry.get("image", ""),
        notes=entry.get("note", ""),
        categories=entry.get("categories", ""),
        restart_policy=entry.get("restart_policy"),
        ports=conv_ports2dict(entry.get("ports", [])),
        network_mode=entry.get("network_mode", ""),
        network=entry.get("network", ""),
        volumes=entry.get("volumes", []),
        env=entry.get("env", []),
        devices=entry.get("devices", []),
        labels=entry.get("labels", []),
        sysctls=conv_sysctls2dict(entry.get("sysctls", [])),
        cap_add=entry.get("cap_add", []),
        cpus=entry.get("cpus"),
        mem_limit=entry.get("mem_limit"),
    )


def _fetch_template_payload(url: str):
    """Open the template feed and decode it as JSON or YAML."""
    ext = os.path.splitext(urlparse(url).path)[1].rstrip()
    opener = _build_safe_opener()
    with opener.open(url, timeout=TEMPLATE_FETCH_TIMEOUT_S) as file:
        if ext in (".yml", ".yaml"):
            return yaml.load(file, Loader=yaml.SafeLoader)
        if ext in (".json", "json"):
            return json.load(file)
    raise HTTPException(status_code=422, detail=f"Invalid filetype: {ext!r}")


def _items_from_payload(payload) -> list[models.TemplateItem]:
    """Turn the loaded feed (list or dict) into TemplateItem rows."""
    if isinstance(payload, list):
        return [_build_template_item(entry) for entry in payload]
    if isinstance(payload, dict):
        return [_build_template_item(payload)]
    raise HTTPException(status_code=422, detail="Unexpected template payload shape")


def add_template(db: Session, template: models.Template):
    validate_url(template.url)
    _template = models.Template(title=template.title, url=template.url)

    try:
        payload = _fetch_template_payload(template.url)
        _template.items = _items_from_payload(payload)
    except HTTPException:
        raise
    except (OSError, TypeError, ValueError, KeyError) as err:
        logger.warning("Template fetch failed for %s: %s", template.url, err)
        status_code = getattr(err, "status_code", 400)
        raise HTTPException(status_code=status_code, detail=str(err))

    try:
        db.add(_template)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_title = (
            db.query(models.Template).filter(models.Template.title == template.title).first()
        )
        if existing_title:
            raise HTTPException(
                status_code=409, detail="Template with this title already exists."
            )
        # Title collision didn't fire -> URL collision; return the existing
        # row so the "Add Template" call is idempotent per URL.
        return get_template(db=db, url=template.url)

    return get_template(db=db, url=template.url)


def refresh_template(db: Session, template_id: id):
    template = (
        db.query(models.Template).filter(models.Template.id == template_id).first()
    )

    validate_url(template.url)

    _template_path = urlparse(template.url).path
    ext = os.path.splitext(_template_path)[1]

    items = []
    try:
        opener = _build_safe_opener()
        with opener.open(template.url, timeout=TEMPLATE_FETCH_TIMEOUT_S) as fp:
            if ext.rstrip() in (".yml", ".yaml"):
                loaded_file = yaml.load(fp, Loader=yaml.SafeLoader)
            elif ext.rstrip() in (".json"):
                loaded_file = json.load(fp)
            else:
                logger.warning("Refresh: invalid template filetype %r for url %s", ext, template.url)
                raise HTTPException(status_code=422, detail="Invalid filetype")
            if isinstance(loaded_file, list):
                for entry in loaded_file:

                    if entry.get("ports"):
                        ports = conv_ports2dict(entry.get("ports", []))
                    sysctls = conv_sysctls2dict(entry.get("sysctls", []))

                    item = models.TemplateItem(
                        type=int(entry["type"]),
                        title=entry["title"],
                        platform=entry["platform"],
                        description=entry.get("description", ""),
                        name=entry.get("name", entry["title"].lower()),
                        command=entry.get("command"),
                        logo=entry.get("logo", ""),  # default logo here!
                        image=entry.get("image", ""),
                        notes=entry.get("note", ""),
                        categories=entry.get("categories", ""),
                        restart_policy=entry.get("restart_policy"),
                        ports=ports,
                        network_mode=entry.get("network_mode", ""),
                        network=entry.get("network", ""),
                        volumes=entry.get("volumes", []),
                        env=entry.get("env", []),
                        devices=entry.get("devices", []),
                        labels=entry.get("labels", []),
                        sysctls=sysctls,
                        cap_add=entry.get("cap_add", []),
                        cpus=entry.get("cpus"),
                        mem_limit=entry.get("mem_limit"),
                    )
                    items.append(item)
            elif isinstance(loaded_file, dict):
                entry = loaded_file
                ports = conv_ports2dict(entry.get("ports", []))
                sysctls = conv_sysctls2dict(entry.get("sysctls", []))

                # Optional use classmethod from_dict
                template_content = models.TemplateItem(
                    type=int(entry["type"]),
                    title=entry["title"],
                    platform=entry["platform"],
                    description=entry.get("description", ""),
                    name=entry.get("name", entry["title"].lower()),
                    command=entry.get("command"),
                    logo=entry.get("logo", ""),  # default logo here!
                    image=entry.get("image", ""),
                    notes=entry.get("note", ""),
                    categories=entry.get("categories", ""),
                    restart_policy=entry.get("restart_policy"),
                    ports=ports,
                    network_mode=entry.get("network_mode", ""),
                    network=entry.get("network", ""),
                    volumes=entry.get("volumes", []),
                    env=entry.get("env", []),
                    devices=entry.get("devices", []),
                    labels=entry.get("labels", []),
                    sysctls=sysctls,
                    cap_add=entry.get("cap_add", []),
                    cpus=entry.get("cpus"),
                    mem_limit=entry.get("mem_limit"),
                )
                items.append(template_content)
    except Exception as exc:
        if hasattr(exc, "code") and exc.code == 404:
            raise HTTPException(status_code=exc.code, detail=exc.url)
        logger.error("Template refresh failed (ERR_001) for %s: %s", template.url, exc)
        if hasattr(exc, "status_code"):
            raise HTTPException(status_code=exc.status_code, detail=exc.explanation)
        raise HTTPException(status_code=400, detail=str(exc))
    else:
        template.updated_at = datetime.utcnow()
        template.items = items

        try:
            db.commit()
            logger.info('Template "%s" updated successfully.', template.title)
        except Exception as exc:
            db.rollback()
            logger.error("Template commit failed (ERR_002) for %s: %s", template.title, exc)
            raise HTTPException(
                status_code=exc.response.status_code, detail=exc.explanation
            )

    return template


def read_app_template(db, app_id):
    try:
        template_item = (
            db.query(models.TemplateItem)
            .filter(models.TemplateItem.id == app_id)
            .first()
        )
        return template_item
    except Exception as exc:
        raise HTTPException(
            status_code=exc.response.status_code, detail=exc.explanation
        )


def set_template_variables(db: Session, new_variables: models.TemplateVariables):
    try:
        template_vars = db.query(models.TemplateVariables).all()

        variables = []
        t_vars = new_variables

        for entry in t_vars:
            template_variables = models.TemplateVariables(
                variable=entry.variable, replacement=entry.replacement
            )
            variables.append(template_variables)

        db.query(models.TemplateVariables).delete()
        db.add_all(variables)
        db.commit()

        new_template_variables = db.query(models.TemplateVariables).all()

        return new_template_variables

    except IntegrityError as exc:
        logger.error("set_template_variables failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.explanation)


def read_template_variables(db: Session):
    return db.query(models.TemplateVariables).all()

def _parse_default_template_urls(raw: str):
    """Parse the YACHT_DEFAULT_TEMPLATE_URLS setting into [(title, url), ...].

    Format: `Title|URL` per entry, comma-separated. Whitespace around each
    field is stripped. Empty entries are skipped so a trailing comma in
    the env value doesn't blow up. Returns [] on empty/None so a deploy
    can explicitly disable seeding via YACHT_DEFAULT_TEMPLATE_URLS="".
    """
    if not raw:
        return []
    out = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "|" in entry:
            title, _, url = entry.partition("|")
            title = title.strip()
            url = url.strip()
        else:
            # Tolerant: bare URL with no title — derive title from host.
            url = entry
            try:
                from urllib.parse import urlparse
                title = urlparse(url).netloc or url
            except Exception:
                title = url
        if title and url:
            out.append((title, url))
    return out


def init_templates(db: Session):
    """Idempotently install the community Docker-image catalogs configured
    via Settings.DEFAULT_TEMPLATE_URLS. Called from `mark_setup_completed`
    so a fresh install lands on a populated Templates page instead of an
    empty one — but skips anything that's already installed (so re-running
    setup, or seeding after the user manually added the same URL, is a
    no-op).

    Network failures are caught per-entry and logged: an offline install,
    a Github outage, or a malformed feed must NEVER block the user from
    completing setup. The catalog will simply be missing and the user can
    refresh later from the UI.
    """
    from api.settings import get_settings

    raw = get_settings().DEFAULT_TEMPLATE_URLS
    defaults = _parse_default_template_urls(raw)
    if not defaults:
        logger.info("No default template URLs configured; skipping seed.")
        return

    for title, url in defaults:
        # get_template(url=...) returns None when not installed; otherwise
        # we leave the existing row alone (operator may have customised it).
        if get_template(db=db, url=url) is not None:
            logger.info("Default template already installed: %s", title)
            continue
        try:
            template = models.Template(title=title, url=url)
            add_template(db, template)
            logger.info("Added default template: %s (%s)", title, url)
        except Exception as e:
            # Non-fatal: setup-finalize must always succeed. Use logger.exception
            # so the traceback reaches container log aggregators.
            logger.exception(
                "Failed to add default template %s (%s): %s", title, url, e,
            )
