"""Stone is like keystone"""
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web

routes = web.RouteTableDef()
app = web.Application()
app["ep_name"] = __name__
app["ep_type"] = "identity"


class InvalidTokenError(Exception):
    pass


def catalog(request: web.Request):
    base = request.config_dict.get("base_url")
    if not base:
        base = f"{request.scheme}://{request.host}"
    defaults = {"region_id": "default", "interface": "public", "region": "default"}
    root_app = request.config_dict["root_app"]
    return [
        {
            "type": ep["ep_type"],
            "name": ep["ep_name"],
            "endpoints": [
                {
                    **defaults,
                    "url": f"{base}/{str(next(iter(ep.router.routes())).url_for()).split('/')[1]}",
                }
            ],
        }
        for ep in root_app._subapps
    ]


def encode_token(key: str, token: bytes) -> str:
    """Make a cheat and fat token."""
    key = key.encode("utf-8")
    data = json.dumps(token).encode("utf-8")
    h = hmac.new(key, data, hashlib.sha256).hexdigest().encode("ascii")
    return base64.b64encode(data + b"~~~" + h).decode("ascii")


def decode_token(key: str, token: str) -> Any:
    key = key.encode("utf-8")
    data, h = base64.b64decode(token.encode("ascii")).split(b"~~~")
    h2 = hmac.new(key, data, hashlib.sha256).hexdigest().encode("ascii")
    if h2 != h:
        raise InvalidTokenError
    return json.loads(data)


@routes.get("/")
async def endpoints(request: web.Request):
    return web.json_response({})


@routes.post("/auth/tokens")
async def auth(request: web.Request):
    data = await request.json()
    auth_config = request.config_dict["auth_config"]
    try:
        user = data["auth"]["identity"]["password"]["user"]
        username = user.get("name") or user["id"]
        password = user["password"]
        try:
            if auth_config["users"][username]["password"] != password:
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
        "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        "catalog": catalog(request),
    }
    token = encode_token(auth_config["secret_key"], token_data)
    return web.json_response(
        {"token": token_data},
        headers={"X-Subject-Token": token},
    )


app.add_routes(routes)
