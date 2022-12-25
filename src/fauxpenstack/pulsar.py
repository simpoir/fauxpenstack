"""pulsar n. magnetic rotating star formed by the collapse of a supernova"""

import logging
import os
import random
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiofiles
from aiohttp import web

from .metadata import mk_metadata
from .peek import get_image_by_id

routes = web.RouteTableDef()
app = web.Application()
app["ep_type"] = "compute"
app["ep_name"] = __name__

KEYPAIRS = Path("keypairs")
CONSOLES = Path("consoles")


# No persistence. When fauxpenstack dies, so do the VMs.
instances = {}


class Instance:
    config_drive = True

    def __init__(
        self,
        id,
        name,
        image,
        flavor,
        user_data=None,
        key_name=None,
        hostname=None,
        bridge=None,
    ):
        self.id = id
        self.name = name
        self.hostname = hostname
        self.created = datetime.utcnow().isoformat("T", "seconds")
        self.user_data = user_data
        self.key_name = key_name
        self._image = image
        self._flavor = flavor
        self._br_hwadd = self.gen_hwadd()
        self._br = bridge

    async def setup(self):
        self._meta_shutdown, meta_port = await mk_metadata(self)
        arch = self._image.name.split(".")[-2]
        self._sub = self._spawn(arch, self._image, meta_port, self._flavor)

    @staticmethod
    def gen_hwadd() -> str:
        while True:
            candidate = "52:54:00:" + ":".join([f"{b:x}" for b in random.randbytes(3)])
            for existing in instances.values():
                if existing._br_hwadd == candidate:
                    break
            else:
                return candidate

    @property
    def accessIPv4(self):
        """bridged arp lookup"""
        if not self._br_hwadd:
            return None
        with open("/proc/net/arp") as f:
            while entry := f.readline():
                if self._br_hwadd in entry:
                    return entry.partition(" ")[0]
        return None

    def __del__(self):
        if self._sub:
            self._sub.kill()
        try:
            os.remove(CONSOLES / self.id)
        except OSError:
            pass
        self._meta_shutdown()

    def _spawn(self, arch, image_file, metadata_port, flavor, bridge=None):
        args = [
            f"qemu-system-{arch}",
            # "-enable-kvm",
            "-snapshot",
            "-nographic",
            "-serial",
            f"file:{CONSOLES / self.id}",
            "-drive",
            f"file={image_file},if=virtio",
            "-m",
            f"{flavor['ram']}M",
            "-smbios",
            "type=1,product=OpenStack Compute",  # pants on fire
            # metadata-only network
            "-nic",
            f"user,net=169.254.169.0/24,restrict=on,"
            f"guestfwd=tcp:169.254.169.254:80-cmd:nc 127.0.0.1 {metadata_port}",
        ]
        logging.debug("spawning %r", args)
        if (ncpus := flavor["vcpus"]) > 1:
            args.append("-smp")
            args.append(str(ncpus))
        if self._br:
            args.append("-nic")
            args.append(f"bridge,br={self._br},mac={self._br_hwadd}")
        return subprocess.Popen(args, stdout=open("/dev/null", "w"))

    def info(self):
        data = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        ipv4 = self.accessIPv4
        if ipv4:
            data["accessIPv4"] = ipv4
            data["addresses"] = {"private": [{"addr": ipv4}]}
            data["status"] = "ACTIVE"
        else:
            # Not quite true, but network info is assumed to be available
            # on active instances, and we rely on dhcp because we're too lazy
            # to really manage network... So it'll look like a fast boot ;)
            data["status"] = "BUILDING"
        return data


@routes.get("/")
async def versions(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "versions": [
                {
                    "id": "v2.1",
                    "status": "CURRENT",
                    "version": "2.1",
                    "min_version": "2.1",
                }
            ]
        }
    )


@routes.get("/servers")
async def list_(request: web.Request) -> web.Response:
    return web.json_response({"servers": [{"id": id} for id in instances.keys()]})


@routes.delete("/servers/{server_id}")
async def delete(request: web.Request) -> web.Response:
    server_id = request.match_info["server_id"]
    try:
        instances.pop(server_id)
    except KeyError:
        return web.Response(status=404)
    return web.Response(status=204)


@routes.post("/servers")
async def create(request: web.Request) -> web.Response:
    config = request.config_dict["auth_config"]
    uuid = str(uuid4())
    data = await request.json()
    try:
        data = data["server"]
        flavor = config["flavors"][data["flavorRef"]]
    except KeyError:
        return web.Response(status=400)

    image = await get_image_by_id(data["imageRef"])
    if not image:
        return web.Response(status=404)
    try:
        bridge = config["net_bridges"][data["networks"][0]["uuid"]]
    except KeyError:
        bridge = None

    instance = instances[uuid] = Instance(
        uuid,
        data["name"],
        image,
        flavor,
        data.get("user_data"),
        data.get("key_name"),
        data.get("hostname"),
        bridge,
    )
    await instance.setup()
    return web.json_response(
        {"server": {"id": uuid, "links": []}},
        headers={"Location": f"{request.url}/{uuid}"},
    )


@routes.get("/servers/{server_id}")
async def get_server(request: web.Request) -> web.Response:
    server_id = request.match_info["server_id"]
    try:
        instance = instances[server_id]
    except KeyError:
        return web.Response(status=404)
    data = {"server": {"id": server_id, **instance.info()}}
    return web.json_response(data)


@routes.post("/os-keypairs")
async def import_keypair(request: web.Request) -> web.Response:
    data = await request.json()
    try:
        data = data["keypair"]
        name = data["name"].replace("/", "_")
        async with aiofiles.open(KEYPAIRS / name, "w") as f:
            await f.write(data["public_key"])
    except KeyError:
        return web.Response(status=400)
    return web.json_response()


@routes.delete("/os-keypairs/{name}")
async def delete_keypair(request: web.Request) -> web.Response:
    name = request.match_info["name"].replace("/", "_")
    try:
        await aiofiles.os.remove(KEYPAIRS / name)
    except FileNotFoundError:
        return web.Response(status=404)
    return web.Response(status=204)


app.add_routes(routes)
