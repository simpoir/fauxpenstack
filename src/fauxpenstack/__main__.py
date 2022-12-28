import asyncio
import ctypes
import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional

import click
from aiohttp import web

from . import brisk, glue, neutrino, peek, plaster, pulsar
from .middlewares import acl_middleware, idler, no_rel


async def on_startup(app: web.Application, timeout: int):
    async def _wait():
        import signal

        while time.time() - timeout < app["last_request"][0]:
            await asyncio.sleep(timeout)
        logging.error("Service idle for %ds. Shutting down.", timeout)
        os.kill(0, signal.SIGINT)

    asyncio.create_task(_wait())


@click.option("--port", type=int, default=8855)
@click.option("--auth", type=Path, default="auth.json")
@click.option("--dir", type=Path, help="work dir")
@click.option("--idle", type=int, help="stop after idle time")
@click.option("-v", "--verbose", help="verbose", count=True)
@click.command()
def main(auth: Path, port: int, dir: Path, idle: Optional[int], verbose: int) -> None:
    logging.basicConfig(level=20 - verbose * 10)

    if dir:
        os.chdir(dir)

    try:
        with open(auth) as auth:
            auth_config = json.load(auth)
    except OSError:
        logging.exception("Could not read auth data store.")

    app = web.Application(middlewares=[idler, no_rel, acl_middleware(auth_config)])
    app["root_app"] = app
    app["auth_config"] = auth_config
    app["last_request"] = [time.time()]  # make mutable ref
    if idle:
        app.on_startup.append(lambda a: on_startup(a, idle))
    app.add_subapp("/identity", glue.app)
    app.add_routes(glue.routes)
    app.add_subapp("/objects", brisk.app)
    app.add_subapp("/images", peek.app)
    app.add_subapp("/compute", pulsar.app)
    app.add_subapp("/network", neutrino.app)
    app.add_subapp("/storage/v3", plaster.app)

    # check if systemd is handing us a port and use that
    if fd_count := ctypes.cdll.LoadLibrary("libsystemd.so.0").sd_listen_fds(0):
        assert fd_count == 1, "systemd passed us multiple socket?!"
        web.run_app(app, sock=socket.fromfd(3, socket.AF_INET6, socket.SOCK_STREAM))
    else:
        web.run_app(app, port=port)


if __name__ == "__main__":
    main()
