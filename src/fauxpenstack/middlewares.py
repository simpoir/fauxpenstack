import logging
import re
import time

from aiohttp import web

from . import glue


@web.middleware
def idler(request, handler) -> web.Response:
    request.config_dict["last_request"][0] = time.time()
    return handler(request)


def acl_middleware(auth_config) -> web.Response:
    """basic authorization scheme"""

    @web.middleware
    async def _wrapper(request: web.Request, handler: web.RequestHandler):
        perm = request.method.lower()
        try:
            token = request.headers["X-Auth-Token"]
            key = request.config_dict["auth_config"]["secret_key"]
            try:
                user = glue.decode_token(key, token)["user"]["name"]
            except glue.InvalidTokenError:
                logging.error("token validation error")
                return web.Response(status=401)
            roles = set(k for k, v in auth_config["roles"].items() if user in v)
        except KeyError:
            token = "NO_TOKEN"
            roles = {"ANONYMOUS"}
        for pattern, rule in auth_config["acls"].items():
            if re.match(pattern.replace("*", ".*"), request.path):
                for role in roles:
                    try:
                        if perm in rule[role]:
                            return await handler(request)
                    except KeyError:
                        continue
        else:
            logging.debug(
                "rejected access with perm %r , path %r and roles %r",
                perm,
                request.path,
                roles,
            )
            return web.Response(status=401)

    return _wrapper


@web.middleware
def no_rel(request, handler) -> web.Response:
    """Deny path traversal."""
    if request.path.startswith("//") or "\\" in request.path or "./" in request.path:
        return web.Response(status=400)
    return handler(request)
