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
"""glue holds things together, kinda like a keystone does."""
import base64
import binascii
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web
from . import util

routes = web.RouteTableDef()
app = web.Application()
app["ep_name"] = __name__
app["ep_type"] = "identity"
util.make_endpoint(routes, "3.0", "v3")


REGION = "default"


class InvalidTokenError(Exception):
    pass


def catalog(request: web.Request):
    base = request.config_dict.get("base_url")
    if not base:
        base = f"{request.scheme}://{request.host}"
    defaults = {"region_id": "default", "interface": "public", "region": REGION}
    root_app = request.config_dict["root_app"]
    return [
        {
            "type": ep["ep_type"],
            "name": ep["ep_name"],
            "endpoints": [
                {
                    **defaults,
                    "url": f"{base}{str(next(iter(ep.router.routes())).url_for())}",
                }
            ],
        }
        for ep in root_app._subapps
    ]


def encode_token(key: str, token: Any) -> str:
    """Make a cheat and fat token."""
    b_key: bytes = key.encode("utf-8")
    data: bytes = json.dumps(token).encode("utf-8")
    h = hmac.new(b_key, data, hashlib.sha256).hexdigest().encode("ascii")
    return base64.b64encode(data + b"~~~" + h).decode("ascii")


def decode_token(key: str, token: str) -> Any:
    b_key: bytes = key.encode("utf-8")
    try:
        data, h = base64.b64decode(token.encode("ascii")).split(b"~~~")
    except binascii.Error:
        raise InvalidTokenError
    h2 = hmac.new(b_key, data, hashlib.sha256).hexdigest().encode("ascii")
    if h2 != h:
        raise InvalidTokenError
    return json.loads(data)


@routes.post("/v3/auth/tokens")
async def auth(request: web.Request):
    data = await request.json()
    app_config = request.config_dict["app_config"]
    try:
        user = data["auth"]["identity"]["password"]["user"]
        username = user.get("name") or user["id"]
        password = user["password"]
        try:
            if app_config["users"][username]["password"] != password:
                logging.error("invalid credentials")
                return web.Response(status=401)
        except KeyError:
            logging.error("invalid credentials")
            return web.Response(status=401)

    except KeyError:
        logging.error("unsupported auth method")
        return web.Response(status=401)

    token_data = {
        "methods": ["password"],
        "user": {"name": username, "id": username},
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(
            "T", "seconds"
        ),
        "catalog": catalog(request),
    }
    token = encode_token(app_config["secret_key"], token_data)
    return web.json_response(
        {"token": token_data},
        status=201,
        headers={"X-Subject-Token": token},
    )


@routes.post("/v3/tokens")
async def no_v2(request: web.Request) -> web.Response:
    logging.error("Query to identity v2 should be considered obsolete.")
    return web.Response(status=400)


app.add_routes(routes)
