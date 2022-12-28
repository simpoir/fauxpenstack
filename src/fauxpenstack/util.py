import socket

from aiohttp import web


def make_endpoint(routes, version, path=None):
    PUB_IP = socket.gethostbyname(socket.gethostname())
    path = path or ""

    @routes.get("/")
    async def versions(request: web.Request) -> web.Response:
        url = request.url
        return web.json_response(
            {
                "versions": [
                    {
                        "id": f"v{version}",
                        "status": "CURRENT",
                        "version": version,
                        "min_version": version,
                        "links": [
                            {
                                "href": f"{url.scheme}://{PUB_IP}:{url.port}{url.path}{path}",
                                "rel": "self",
                            }
                        ],
                    }
                ]
            }
        )
