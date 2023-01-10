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
