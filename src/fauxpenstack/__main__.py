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
import asyncio
import ctypes
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional
import toml

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
@click.option("--conf", type=Path, default="conf.toml")
@click.option("--dir", type=Path, help="work dir")
@click.option("--idle", type=int, help="stop after idle time")
@click.option("-v", "--verbose", help="verbose", count=True)
@click.command()
def main(conf: Path, port: int, dir: Path, idle: Optional[int], verbose: int) -> None:
    logging.basicConfig(level=20 - verbose * 10)

    if dir:
        os.chdir(dir)

    try:
        app_config = toml.load(conf)
    except OSError:
        logging.exception("Could not read config data store.")

    app = web.Application(middlewares=[idler, no_rel, acl_middleware(app_config)])
    app["root_app"] = app
    app["app_config"] = app_config
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
