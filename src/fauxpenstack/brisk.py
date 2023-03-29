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
"""brisk adj. speedy, swift"""

import hashlib
import logging
import os
import time
from pathlib import Path

import aiofiles.os
from aiohttp import web

routes = web.RouteTableDef()
app = web.Application()
app["ep_type"] = "object-store"
app["ep_name"] = __name__

BUCKETS = Path("buckets")
CHUNK_SIZE = 10240

hash_cache = {}


async def stat(path: Path) -> dict:
    stat = await aiofiles.os.stat(path)
    try:
        hash = hash_cache[path]
    except KeyError:
        hash = hashlib.md5()
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(CHUNK_SIZE):
                hash.update(chunk)
        hash = hash.hexdigest()
        hash_cache[path] = hash

    return {
        "Content-Length": str(stat.st_size),
        "X-Timestamp": str(int(stat.st_mtime)),
        "Last-Modified": time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(stat.st_mtime)
        ),
        "Content-Type": "application/octet-stream",
        "ETag": f'"{hash}"',
    }


@routes.get("")
async def list_buckets(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", 0))
    marker = request.query.get("marker")
    end_marker = request.query.get("end_marker")
    prefix = request.query.get("prefix")
    listing = []
    for bucket in await aiofiles.os.listdir(BUCKETS):
        if not os.path.isdir(BUCKETS / bucket):
            continue
        if (end_marker and bucket > end_marker) or (limit and len(listing) > limit):
            break
        if marker and bucket <= marker:
            continue
        if prefix and not bucket.startswith(prefix):
            continue
        listing.append({"count": 0, "bytes": 0, "name": bucket})
    return web.json_response(listing)


@routes.get("/{bucket}")
async def list_bucket(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", 0))
    marker = request.query.get("marker")
    end_marker = request.query.get("end_marker")
    prefix = request.query.get("prefix")
    try:
        listing = []
        path = BUCKETS / request.match_info["bucket"]
        trim = len(str(path)) + 1
        for parent, _dirs, files in os.walk(path):  # XXX not async
            if (end_marker and parent > end_marker) or (limit and len(listing) > limit):
                break
            if marker and parent < marker:
                continue
            for f in files:
                obj_name = f"{parent[trim:]}/{f}"
                if prefix and not obj_name.startswith(prefix):
                    continue

                listing.append(
                    {
                        "hash": "FIXME",
                        "bytes": "FIXME",
                        "name": obj_name,
                        "content_type": "application/octet-stream",
                    }
                )
    except FileNotFoundError:
        return web.Response(status=404)
    return web.json_response(listing)


@routes.head("/{bucket}/{path:.+}")
async def head(request: web.Request) -> web.Response:
    try:
        return web.Response(
            headers=await stat(
                BUCKETS / request.match_info["bucket"] / request.match_info["path"]
            )
        )
    except FileNotFoundError:
        return web.Response(status=404)


@routes.put("/{bucket}")
async def create_bucket(request: web.Request) -> web.Response:
    bucket_name = request.match_info["bucket"]
    if "/" in bucket_name:
        return web.Response(status=400)
    path = BUCKETS / bucket_name
    try:
        await aiofiles.os.mkdir(path)
    except FileExistsError:
        pass
    return web.Response()


@routes.put("/{bucket}/{path:.+}")
async def upload(request: web.Request):
    dst = BUCKETS / request.match_info["bucket"] / request.match_info["path"]
    hash_cache.pop(dst, None)
    await aiofiles.os.makedirs(dst.parent, exist_ok=True)
    async with aiofiles.open(dst, "wb") as f:
        body = request.content
        async for chunk in body.iter_any():
            await f.write(chunk)
    return web.Response()


@routes.get("/{bucket}/{path:.+}")
async def download(request: web.Request) -> web.Response:
    path = BUCKETS / request.match_info["bucket"] / request.match_info["path"]
    try:
        stat = await aiofiles.os.stat(path)
    except FileNotFoundError:
        return web.Response(status=404)
    if await aiofiles.os.path.isdir(path):
        return web.Response(status=404)
    async with aiofiles.open(
        BUCKETS / request.match_info["bucket"] / request.match_info["path"], "rb"
    ) as f:
        response = web.StreamResponse(status=200)
        response.content_length = stat.st_size
        await response.prepare(request)
        while chunk := await f.read(CHUNK_SIZE):
            await response.write(chunk)
        return response


@routes.delete("/{bucket}/{path:.+}")
async def delete(request: web.Request) -> web.Response:
    bucket = BUCKETS / request.match_info["bucket"]
    path = bucket / request.match_info["path"]
    hash_cache.pop(path, None)
    try:
        await aiofiles.os.remove(path)
    except FileNotFoundError:
        return web.Response(status=404)

    parent = path.parent
    while parent != bucket:
        if not await aiofiles.os.listdir(parent):
            await aiofiles.os.rmdir(parent)
            parent = parent.parent
        else:
            break

    return web.Response(status=204)


@routes.get("/{rest:.+}")
async def unimpl(request) -> web.Response:
    logging.error("unimpl: %s %s", request.method, request.path)
    return web.Response(status=404)


app.add_routes(routes)
