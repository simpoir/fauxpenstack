"""plaster n. building material used for decoration and coating"""

from uuid import uuid4

import aiofiles
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
