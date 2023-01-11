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
"""neutrino n. a neutral particle lighter than a neutron"""

from aiohttp import web

from . import util

routes = web.RouteTableDef()
app = web.Application()
app["ep_name"] = __name__
app["ep_type"] = "network"
util.make_endpoint(routes, "2.0", "v2.0")


@routes.get("/v2.0/networks")
async def listing(request: web.Request) -> web.Response:
    nets = request.config_dict["app_config"]["net_bridges"]
    return web.json_response(
        {
            "networks": [
                {"name": name, "id": name, "label": name, "status": "ACTIVE"}
                for name in nets.keys()
            ]
        }
    )


@routes.get("/v2.0/networks/{network_id}")
async def get_network(request: web.Request) -> web.Response:
    network_id = request.match_info["network_id"]
    try:
        return web.json_response(
            {
                "network": {
                    "name": network_id,
                    "id": network_id,
                    "status": "ACTIVE",
                }
            }
        )
    except KeyError:
        return web.Response(status=404)


@routes.get("/v2.0/subnets")
async def list_subnets(request: web.Request) -> web.Response:
    return web.json_response({"subnets": []})


@routes.get("/v2.0/floatingips")
async def list_floatingips(request: web.Request) -> web.Response:
    return web.json_response({"floatingips": []})


@routes.get("/v2.0/ports")
async def list_ports(request: web.Request) -> web.Response:
    return web.json_response({"ports": []})


@routes.get("/v2.0/security-groups")
async def security_groups(request: web.Request) -> web.Response:
    return web.json_response(
        dict(
            security_groups=[
                dict(
                    id="default",
                    name="default",
                    security_group_rules=[],
                    stateful=False,
                    shared=False,
                )
            ]
        )
    )


@routes.post("/v2.0/security-group-rules")
async def add_security_group_rules(request: web.Request) -> web.Response:
    return web.json_response(status=201)


app.add_routes(routes)
