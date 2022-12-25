"""metadata service, because config drives are boring."""
import asyncio
from typing import Callable, Optional

import aiofiles
from aiohttp import web

routes = web.RouteTableDef()


@routes.get("/openstack")
async def metadata(request: web.Request) -> web.Response:
    return web.json_response({})


@routes.get("/openstack/{version}/vendor_data.json")
@routes.get("/openstack/{version}/vendor_data2.json")
async def vendor_data(request: web.Request) -> web.Response:
    return web.json_response({})


@routes.get("/openstack/{version}/user_data")
async def user_data(request: web.Request) -> web.Response:
    return web.Response(body=request.config_dict["user_data"])


@routes.get("/openstack/{version}/meta_data.json")
async def meta_data(request: web.Request) -> web.Response:
    return web.json_response(request.config_dict["meta_data"])


@routes.get("/openstack/{version}/network_data.json")
async def network_data(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "links": [
                {
                    "id": "br_link0",
                    "ethernet_mac_address": request.config_dict["hw_addr"],
                    "type": "bridge",
                }
            ],
            "networks": [
                {
                    "id": "network0",
                    "link": "br_link0",
                    "type": "ipv4_dhcp",
                }
            ],
            "services": [],
        }
    )


async def mk_metadata(instance) -> (Callable, int):
    """spawn a metadata service. returns a closer and a port."""

    meta_data = {
        "name": instance.name,
        "uuid": instance.id,
        "hostname": instance.hostname or instance.name,
        "public_keys": {},
    }

    if instance.key_name:
        try:
            key_name = instance.key_name.strip()
            async with aiofiles.open(f"keypairs/{key_name}") as f:
                meta_data["public_keys"][key_name] = await f.read()
        except FileNotFoundError:
            pass

    app = web.Application()
    app.add_routes(routes)
    app["user_data"] = instance.user_data or ""
    app["meta_data"] = meta_data
    app["hw_addr"] = instance._br_hwadd

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()

    def cleanup():
        asyncio.get_event_loop().is_running() and asyncio.create_task(site.stop())

    return (
        cleanup,
        site._server.sockets[0].getsockname()[1],
    )
