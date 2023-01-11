# Copyright 2023  Simon Poirier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""peek v. to glance quickly"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles.os
from aiohttp import web

from .util import make_endpoint

IMAGES = Path("images")

routes = web.RouteTableDef()
app = web.Application()
app["ep_type"] = "image"
app["ep_name"] = __name__
make_endpoint(routes, "2", "v2")


async def get_image_by_id(image_id):
    for image in await aiofiles.os.listdir(IMAGES):
        if image.startswith(image_id + ":"):
            return IMAGES / image


@routes.post("/v2/images")
async def create_image(request: web.Request) -> web.Response:
    payload = await request.json()
    uuid = payload.get("id") or str(uuid4())
    name = payload.get("name", "").replace("/", "_")  # mildly sanitize path
    format = payload.get("disk_format") or "qcow2"
    for image in await aiofiles.os.listdir(IMAGES):
        if image.startswith(uuid + ":"):
            return web.Response(status=409)
    arch = payload.get("architecture") or "x86_64"

    path = IMAGES / f"{uuid}:{name}.{arch}.{format}"
    async with aiofiles.open(path, "wb"):
        pass  # touch

    ts = datetime.now(timezone.utc).isoformat("T", "seconds")
    return web.json_response(
        {
            "status": "active",
            "name": name,
            "tags": [],
            "container_format": "bare",
            "disk_format": format,
            "visibility": "public",
            "min_disk": 0,
            "min_ram": 0,
            "virtual_size": None,
            "protected": False,
            "id": uuid,
            "self": f"/v2/images/{uuid}",
            "file": f"/v2/images/{uuid}/file",
            "checksum": None,
            "os_hash_algo": None,
            "os_hash_value": None,
            "os_hidden": False,
            "created_at": ts,
            "updated_at": ts,
            "size": 0,
            "schema": "/v2/schemas/image",
        }
    )


@routes.put("/v2/images/{uuid}/file")
async def upload(request: web.Request) -> web.Response:
    uuid = request.match_info["uuid"]
    for image in await aiofiles.os.listdir(IMAGES):
        if image.startswith(uuid + ":"):
            break
    else:
        return web.Response(status=404)
    path = IMAGES / image
    async with aiofiles.open(path, "wb") as f:
        async for chunk in request.content.iter_any():
            await f.write(chunk)
    proc = await asyncio.create_subprocess_exec("qemu-img", "resize", path, "10G")
    await proc.wait()
    return web.Response(status=204)


@routes.get("/v2/images")
async def list(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", 0))
    marker = request.query.get("marker")
    end_marker = request.query.get("end_marker")
    return web.json_response(await _list(limit, marker, end_marker))


async def _list(
    limit: Optional[int] = None,
    marker: Optional[str] = None,
    end_marker: Optional[str] = None,
):
    listing = []
    for image in await aiofiles.os.listdir(IMAGES):
        if (end_marker and image > end_marker) or (limit and len(listing) > limit):
            break
        if marker and image <= marker:
            continue
        uuid, sep, name = image.partition(":")
        if not sep:
            continue
        name, _, format = name.rpartition(".")
        name, _, arch = name.rpartition(".")
        stat = await aiofiles.os.stat(IMAGES / image)
        listing.append(
            {
                "status": "active",
                "name": name,
                "architecture": arch,
                "tags": [],
                "container_format": "bare",
                "disk_format": format,
                "visibility": "public",
                "min_disk": 0,
                "min_ram": 0,
                "virtual_size": None,
                "protected": False,
                "id": uuid,
                "self": f"/v2/images/{uuid}",
                "file": f"/v2/images/{uuid}/file",
                "checksum": None,
                "os_hash_algo": "sha512",
                "os_hash_value": "FIXME",
                "os_hidden": False,
                "created_at": "FIXME",
                "updated_at": "FIXME",
                "size": stat.st_size,
                "schema": "/v2/schemas/image",
            }
        )
    return {"images": listing, "schema": "/v2/schemas/images", "first": "/v2/images"}


@routes.get("/v2/images/{uuid}")
async def get_image(request: web.Request) -> web.Response:
    uuid = request.match_info["uuid"]
    listing = await _list(1, uuid)
    if not listing["images"]:
        return web.Response(status=404)
    return web.json_response(listing["images"][0])


@routes.delete("/v2/images/{image_id}")
async def delete(request: web.Request) -> web.Response:
    uuid = request.match_info["image_id"]
    for image in await aiofiles.os.listdir(IMAGES):
        if image.startswith(uuid + ":"):
            await aiofiles.os.remove(IMAGES / image)
            return web.Response(status=204)

    return web.Response(status=404)


@routes.get("/v2/schemas/image")
async def schema(request: web.Request) -> web.Response:
    # just enough to make glanceclient satisfied
    return web.json_response(
        {
            "name": "images",
            "properties": {},
        }
    )


app.add_routes(routes)
