import logging

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from fastapi import HTTPException

from api.db.models import containers as models
from api.utils.templates import conv_sysctls2dict, conv_ports2dict

from datetime import datetime
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
    opener = urllib.request.build_opener(SafeRedirectHandler())
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
        opener = urllib.request.build_opener(SafeRedirectHandler())
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

def init_templates(db: Session):
    """
    Initializes default templates if none exist.
    """
    templates_exist = get_templates(db)
    if not templates_exist:
        logger.info("No templates found. Adding default templates.")
        defaults = [
            {
                "title": "LSIO Portainer Templates",
                "url": "https://raw.githubusercontent.com/technorabilia/portainer-templates/main/lsio/templates/templates.json"
            }
        ]

        for default in defaults:
            try:
                template = models.Template(title=default["title"], url=default["url"])
                # add_template handles validation and fetching
                add_template(db, template)
                logger.info("Added default template: %s", default["title"])
            except Exception as e:
                # We deliberately do NOT re-raise: a transient network failure
                # while fetching the default templates feed must not crash app
                # startup. But silent print() previously made these failures
                # invisible in container log aggregators — use the real logger
                # with traceback so operators actually see them.
                logger.exception(
                    "Failed to add default template %s: %s", default["title"], e,
                )
