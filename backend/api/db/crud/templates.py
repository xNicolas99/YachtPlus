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

# Templates

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

    try:
        # Resolve hostname to IP
        # Note: This might pick one IP if multiple are returned.
        # For stricter security, we might need to check all IPs.
        ip_list = socket.getaddrinfo(hostname, None)
        for ip_info in ip_list:
             # ip_info[4][0] is the IP address string
             ip = ip_info[4][0]
             if is_private_ip(ip):
                 raise HTTPException(status_code=400, detail=f"Access to private IP {ip} is denied.")

    except socket.gaierror:
        # If hostname cannot be resolved, fail early to prevent SSRF bypasses.
        raise HTTPException(status_code=400, detail="Invalid URL: Hostname resolution failed.")

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


def add_template(db: Session, template: models.Template):
    validate_url(template.url)
    try:
        _template_path = urlparse(template.url).path
        ext = os.path.splitext(_template_path)[1]
        # Opens the JSON and iterate over the content.
        _template = models.Template(title=template.title, url=template.url)
        opener = urllib.request.build_opener(SafeRedirectHandler())
        with opener.open(template.url) as file:
            if ext.rstrip() in (".yml", ".yaml"):
                loaded_file = yaml.load(file, Loader=yaml.SafeLoader)
            elif ext.rstrip() in (".json", "json"):
                loaded_file = json.load(file)
            else:
                print("Invalid filetype")
                raise
            if type(loaded_file) == list:
                for entry in loaded_file:
                    ports = conv_ports2dict(entry.get("ports", []))
                    sysctls = conv_sysctls2dict(entry.get("sysctls", []))

                    # Optional use classmethod from_dict
                    try:
                        template_content = models.TemplateItem(
                            type=int(entry.get("type", 1)),
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
                    except Exception as exc:
                        raise HTTPException(
                            status_code=exc.response.status_code,
                            detail=entry.get("name") + " " + exc.explanation,
                        )
                    _template.items.append(template_content)
            elif type(loaded_file) == dict:
                entry = loaded_file
                ports = conv_ports2dict(entry.get("ports", []))
                sysctls = conv_sysctls2dict(entry.get("sysctls", []))

                # Optional use classmethod from_dict
                template_content = models.TemplateItem(
                    type=int(entry.get("type", 1)),
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
                _template.items.append(template_content)
    except (OSError, TypeError, ValueError) as err:
        # Optional handle KeyError here too.
        print("data request failed", err)
        if hasattr(err, "status_code"):
             raise HTTPException(status_code=err.status_code, detail=err.explanation)
        else:
             raise HTTPException(status_code=400, detail=str(err))

    try:
        db.add(_template)
        db.commit()
    except IntegrityError as err:
        db.rollback()
        # Check if the conflict is due to the Title
        existing_title = (
            db.query(models.Template).filter(models.Template.title == template.title).first()
        )
        if existing_title:
            raise HTTPException(
                status_code=409, detail="Template with this title already exists."
            )

        # If the template URL already exists, we return the existing one.
        # This makes the "Add Template" operation idempotent for URLs.
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
        with opener.open(template.url) as fp:
            if ext.rstrip() in (".yml", ".yaml"):
                loaded_file = yaml.load(fp, Loader=yaml.SafeLoader)
            elif ext.rstrip() in (".json"):
                loaded_file = json.load(fp)
            else:
                print("Invalid filetype")
                raise HTTPException(status_code=422, detail="Invalid filetype")
            if type(loaded_file) == list:
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
            elif type(loaded_file) == dict:
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
        else:
            print("Template update failed. ERR_001", exc)
            if hasattr(exc, "status_code"):
                 raise HTTPException(status_code=exc.status_code, detail=exc.explanation)
            else:
                 raise HTTPException(status_code=400, detail=str(exc))
    else:
        # db.delete(template)
        # make_transient(template)
        # db.commit()

        template.updated_at = datetime.utcnow()
        template.items = items

        try:
            # db.add(template)
            db.commit()
            print(f'Template "{template.title}" updated successfully.')
        except Exception as exc:
            db.rollback()
            print("Template update failed. ERR_002", exc)
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
        print(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.explanation)


def read_template_variables(db: Session):
    return db.query(models.TemplateVariables).all()

def init_templates(db: Session):
    """
    Initializes default templates if none exist.
    """
    templates_exist = get_templates(db)
    if not templates_exist:
        print("No templates found. Adding default templates.")
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
                print(f"Added default template: {default['title']}")
            except Exception as e:
                print(f"Failed to add default template {default['title']}: {e}")
