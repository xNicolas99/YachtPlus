from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from api.db.models import containers as models
from api.db.models.settings import SecretKey
from datetime import datetime
from api.settings import Settings
import json
import asyncio

settings = Settings()


async def export_settings(db: AsyncSession):
    file_export = {}
    result_t = await db.execute(select(models.Template))
    file_export["templates"] = result_t.scalars().all()
    result_v = await db.execute(select(models.TemplateVariables))
    file_export["variables"] = result_v.scalars().all()
    return file_export


async def get_secret_key(db: AsyncSession):
    result = await db.execute(select(models.SecretKey).limit(1))
    check = result.scalars().first()
    if check:
        return True
    else:
        return False


async def generate_secret_key(db: AsyncSession):
    result = await db.execute(select(SecretKey).limit(1))
    check = result.scalars().first()
    if check is None:
        key = SecretKey(key=settings.SECRET_KEY)
        db.add(key)
        await db.commit()
        print("Secret key generated")
        return key.key
    else:
        print("Secret key exists")
        return check.key


async def import_settings(db: AsyncSession, upload):
    # File read is blocking I/O; run it in a thread so it doesn't block the loop.
    import_file = await asyncio.to_thread(upload.file.read)
    decoded_import = import_file.decode("utf-8")
    import_contents = json.loads(decoded_import)

    _templates = import_contents["templates"]
    _variables = import_contents["variables"]

    _template_list = []
    _var_list = []

    for template in _templates:
        template_model = models.Template(
            id=template["id"],
            title=template["title"],
            url=template["url"],
            updated_at=datetime.fromisoformat(template["updated_at"]),
            created_at=datetime.fromisoformat(template["created_at"]),
        )
        for item in template["items"]:
            _item = models.TemplateItem(**item)
            template_model.items.append(_item)
        _template_list.append(template_model)

    for variable in _variables:
        variable_model = models.TemplateVariables(**variable)
        _var_list.append(variable_model)

    # Remove Existing
    await db.execute(delete(models.TemplateVariables))
    await db.execute(delete(models.TemplateItem))
    await db.execute(delete(models.Template))

    # Add New
    db.add_all(_template_list)
    db.add_all(_var_list)
    await db.commit()
    response = {"success": "Import Successful"}
    return response
