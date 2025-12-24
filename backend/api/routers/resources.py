from __future__ import annotations
from fastapi import APIRouter, Depends
from api.auth.jwt import get_auth_wrapper

from api.actions import resources
from api.db.schemas.resources import ImageWrite, VolumeWrite, NetworkWrite
from api.auth.auth import auth_check

router = APIRouter()
### Images ###


@router.get(
    "/images/",
)
async def get_images(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_images()


@router.post(
    "/images/",
)
async def write_image(image: ImageWrite, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.write_image(image.image)


@router.get(
    "/images/{image_id}",
)
async def get_image(image_id, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_image(image_id)


@router.get(
    "/images/{image_id}/pull",
)
async def pull_image(image_id, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.update_image(image_id)


@router.delete(
    "/images/{image_id}",
)
async def delete_image(image_id, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.delete_image(image_id)


### Volumes ###
@router.get(
    "/volumes/",
)
async def get_volumes(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_volumes()


@router.post(
    "/volumes/",
)
async def write_volume(name: VolumeWrite, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.write_volume(name.name)


@router.get(
    "/volumes/{volume_name}",
)
async def get_volume(volume_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_volume(volume_name)


@router.delete(
    "/volumes/{volume_name}",
)
async def delete_volume(volume_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.delete_volume(volume_name)


### Networks ###
@router.get(
    "/networks/",
)
async def get_networks(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_networks()


@router.post(
    "/networks/",
)
async def write_network(form: NetworkWrite, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.write_network(form)


@router.get(
    "/networks/{network_name}",
)
async def get_network(network_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.get_network(network_name)


@router.delete(
    "/networks/{network_name}",
)
async def delete_network(network_name, Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    auth_check(Authorize)
    return await resources.delete_network(network_name)
