from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from api.db.models import containers as models
from api.db.models.settings import SecretKey
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from api.settings import get_settings
settings = get_settings()
import json
import asyncio
import logging

logger = logging.getLogger(__name__)



async def export_settings(db: AsyncSession):
    file_export = {}
    result_t = await db.execute(select(models.Template).options(selectinload(models.Template.items)))
    file_export["templates"] = result_t.scalars().all()
    result_v = await db.execute(select(models.TemplateVariables))
    file_export["variables"] = result_v.scalars().all()
    return file_export


async def get_secret_key(db: AsyncSession):
    result = await db.execute(select(SecretKey).limit(1))
    check = result.scalars().first()
    if check:
        return True
    else:
        return False


async def generate_secret_key(db: AsyncSession):
    # Keep the configured signing key in its dedicated secret file rather
    # than creating a second plaintext copy in database backups.
    return get_settings().SECRET_KEY


async def import_settings(db: AsyncSession, upload):
    # File read is blocking I/O; run it in a thread so it doesn't block the loop.
    limit = 5 * 1024 * 1024
    import_file = await asyncio.to_thread(upload.file.read, limit + 1)
    if len(import_file) > limit:
        raise HTTPException(413, "Settings export is too large")
    from api.db.schemas.templates import Import_Export
    from pydantic import ValidationError
    try:
        import_contents = json.loads(import_file.decode("utf-8"))
        if not isinstance(import_contents, dict) or not {"templates", "variables"} <= import_contents.keys():
            raise ValueError("Missing settings export sections")
        validated = Import_Export.model_validate(import_contents)
        if any(not row.title or not row.url for row in validated.templates):
            raise ValueError("Templates require title and URL")
        for catalog in validated.templates:
            if any(item.type is None or not item.title or not item.platform or not item.image for item in catalog.items):
                raise ValueError("Template items require type, title, platform and image")
        if any(not row.variable or row.replacement is None for row in validated.variables):
            raise ValueError("Variables require name and replacement")
        import_contents = validated.model_dump()
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, "Invalid settings export") from None

    _templates = import_contents["templates"]
    _variables = import_contents["variables"]

    _template_list = []
    _var_list = []

    for template in _templates:
        values = {key: template[key] for key in ("title", "url", "updated_at", "created_at") if template.get(key) is not None}
        template_model = models.Template(**values)
        for item in template["items"]:
            fields = {column.key for column in models.TemplateItem.__table__.columns} - {"id", "template_id"}
            _item = models.TemplateItem(**{key: value for key, value in item.items() if key in fields})
            template_model.items.append(_item)
        _template_list.append(template_model)

    for variable in _variables:
        variable_model = models.TemplateVariables(variable=variable["variable"], replacement=variable["replacement"])
        _var_list.append(variable_model)

    # Remove Existing
    await db.execute(delete(models.TemplateVariables))
    await db.execute(delete(models.TemplateItem))
    await db.execute(delete(models.Template))

    # Add New
    db.add_all(_template_list)
    db.add_all(_var_list)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(422, "Settings export contains conflicting data") from None
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(503, "Settings import database unavailable") from None
    response = {"success": "Import Successful"}
    return response
