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
"""plaster n. building material used for decoration and coating"""

from uuid import uuid4

from aiohttp import web

from .util import make_endpoint

routes = web.RouteTableDef()
app = web.Application()
app["ep_type"] = "volumev3"
app["ep_name"] = __name__
make_endpoint(routes, "3.0")


@routes.get("/volumes/detail")
@routes.get("/{project_id}/volumes/detail")
async def list_volumes(request: web.Request) -> web.Response:
    return web.json_response({"volumes": []})


app.add_routes(routes)
