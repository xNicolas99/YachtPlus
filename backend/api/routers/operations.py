"""Status and explicitly authorized execution of allowlisted operations."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import get_auth_wrapper
from api.db.models.operations import Operation
from api.db.schemas.apps import DeployForm
from api.services import operations
from api.utils.auth import get_db
from api.utils.security import limiter

router = APIRouter()


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=64)
    resource: str = Field(min_length=1, max_length=512)
    action: str | None = Field(default=None, max_length=32)


async def _owned_operation(db, operation_id, actor):
    operation = await db.get(Operation, operation_id)
    if not operation or (not actor.is_superuser and (
        operation.actor_id != actor.id or operation.actor_instance != actor.account_instance
    )):
        raise HTTPException(404, "Task not found")
    return operation


@router.get("")
@router.get("/", include_in_schema=False)
async def list_operations(
    state: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    actor = await operations.resolve_actor(db, Authorize)
    if state and state not in operations.ACTIVE_STATUSES | operations.TERMINAL_STATUSES:
        raise HTTPException(422, "Unsupported task status")
    conditions = [] if actor.is_superuser else [Operation.actor_id == actor.id, Operation.actor_instance == actor.account_instance]
    if state:
        conditions.append(Operation.status == state)
    total = (await db.execute(select(func.count()).select_from(Operation).where(*conditions))).scalar_one()
    result = await db.execute(select(Operation).where(*conditions).order_by(
        Operation.created_at.desc(), Operation.id.desc()).offset(offset).limit(limit))
    return {"items": [operations.public_operation(item) for item in result.scalars()], "total": total}


@router.post("", status_code=202)
@router.post("/", status_code=202, include_in_schema=False)
@limiter.limit("30/minute")
async def create_operation(
    request: Request,
    payload: OperationRequest,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    response: Response = None,
):
    operations.validate_descriptor(payload.kind, payload.resource, payload.action)
    actor = await operations.resolve_actor(db, Authorize)
    if Authorize.is_api_key():
        raise HTTPException(403, "API keys cannot create tasks")
    operation = await operations.submit_operation(db, kind=payload.kind, resource=payload.resource,
                                                  action=payload.action, actor=actor)
    return operations.public_operation(operation)


@router.get("/{operation_id}")
async def get_operation(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
):
    actor = await operations.resolve_actor(db, Authorize)
    return operations.public_operation(await _owned_operation(db, operation_id, actor))


@router.post("/deploy", status_code=202)
@limiter.limit("10/minute")
async def create_deployment(
    request: Request,
    template: DeployForm,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    response: Response = None,
):
    # Payloads may contain credentials. The task record only stores the name;
    # the validated form exists in a code-owned runner closure until completion.
    from api.routers.apps import _validate_deploy_template
    from api.db.crud import templates as template_crud
    from api.utils.apps import merge_template
    from api.actions import apps
    from fastapi.responses import JSONResponse

    actor = await operations.resolve_actor(db, Authorize)
    if Authorize.is_api_key():
        raise HTTPException(403, "API keys cannot create deployments")
    operations.check_actor_permission(actor, "perm_start")
    if template.edit:
        operations.check_actor_permission(actor, "perm_restart")
    if template.template_id:
        item = await template_crud.read_app_template(db, template.template_id)
        if item:
            template = merge_template(template, item)
    _validate_deploy_template(template)
    if template.security_profile == "image-default":
        operations.check_actor_permission(actor, "superuser")
    conflicts = await apps.check_container_conflicts(template)
    if conflicts:
        return JSONResponse(status_code=409, content={"success": False, "conflicts": conflicts})

    async def deploy(report):
        await report("Deploying container")
        result = await apps.deploy_app(template)
        if isinstance(result, dict) and result.get("success") is False:
            raise HTTPException(409, "Deployment conflicts with an existing resource")

    operation = await operations.submit_operation(db, kind="container.deploy", resource=template.name,
                                                  action="edit" if template.edit else "create",
                                                  actor=actor, runner=deploy)
    return operations.public_operation(operation)


@router.post("/{operation_id}/retry", status_code=202)
@limiter.limit("10/minute")
async def retry_operation(
    request: Request,
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper),
    response: Response = None,
):
    actor = await operations.resolve_actor(db, Authorize)
    if Authorize.is_api_key():
        raise HTTPException(403, "API keys cannot retry tasks")
    previous = await _owned_operation(db, operation_id, actor)
    if not operations.public_operation(previous)["retryable"]:
        raise HTTPException(409, "This task cannot be retried. Use the resource's action instead.")
    operation = await operations.submit_operation(db, kind=previous.kind, resource=previous.resource,
                                                  action=previous.action, actor=actor)
    return operations.public_operation(operation)
