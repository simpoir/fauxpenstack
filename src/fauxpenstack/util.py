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
import socket

from aiohttp import web


def make_endpoint(routes, version, path=None):
    """Make an aggregate of generic version list and version."""
    PUB_IP = socket.gethostbyname(socket.gethostname())
    path = path or ""

    @routes.get("/")
    async def versions(request: web.Request) -> web.Response:
        url = request.url

        current = {
            "id": f"v{version}",
            "status": "CURRENT",
            "version": "",  # no microversion
            "min_version": version,
            "links": [
                {
                    "href": f"{url.scheme}://{PUB_IP}:{url.port}{url.path}{path}",
                    "rel": "self",
                }
            ],
        }
        return web.json_response(
            {
                "versions": [current],
                "version": current,
            }
        )
