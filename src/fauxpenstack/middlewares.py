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
import logging
import re
import time

from aiohttp import web

from . import glue


@web.middleware
def idler(request, handler) -> web.Response:
    request.config_dict["last_request"][0] = time.time()
    return handler(request)


def acl_middleware(app_config) -> web.Response:
    """basic authorization scheme"""

    @web.middleware
    async def _wrapper(request: web.Request, handler: web.RequestHandler):
        perm = request.method.lower()
        try:
            token = request.headers["X-Auth-Token"]
            key = request.config_dict["app_config"]["secret_key"]
            try:
                user = glue.decode_token(key, token)["user"]["name"]
            except glue.InvalidTokenError:
                logging.error("token validation error")
                return web.Response(status=401)
            roles = set(k for k, v in app_config["roles"].items() if user in v)
        except KeyError:
            token = "NO_TOKEN"
            roles = set()
        roles.add("ANONYMOUS")

        for pattern, rule in app_config["acls"].items():
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
