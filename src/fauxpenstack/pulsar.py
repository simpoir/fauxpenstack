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
"""pulsar n. magnetic rotating star formed by the collapse of a supernova"""

import logging
import os
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles
from aiohttp import web

from .metadata import mk_metadata
from .peek import get_image_by_id
from .plaster import make_volume_from_image
from .util import make_endpoint

routes = web.RouteTableDef()
app = web.Application()
app["ep_type"] = "compute"
app["ep_name"] = __name__
make_endpoint(routes, "2.1")

KEYPAIRS = Path("keypairs")
CONSOLES = Path("consoles")
AZ_NAME = "nova"


# No persistence. When fauxpenstack dies, so do the VMs.
instances = {}


class Instance:
    config_drive = True

    def __init__(
        self,
        id: str,
        name: str,
        image: Path,
        flavor,
        volume: Optional[Path] = None,
        user_data=None,
        key_name=None,
        hostname=None,
        bridge=None,
        tags=None,
        metadata=None,
    ):
        self.id = id
        self.name = name
        self.hostname = hostname or name
        self.created = datetime.now(timezone.utc).isoformat("T", "seconds")
        self.user_data = user_data
        self.key_name = key_name
        self.tags = tags or []
        self._image = image
        self._volume = volume or image
        self._flavor = flavor
        self._br_hwadd = self.gen_hwadd()
        self._br = bridge
        self.metadata = metadata or {}

    async def setup(self):
        self._meta_shutdown, meta_port = await mk_metadata(self)
        arch = self._image.name.split(".")[-2]
        await self._spawn(arch, self._volume, meta_port, self._flavor)

    @staticmethod
    def gen_hwadd() -> str:
        while True:
            candidate = "52:54:00:" + ":".join(
                [f"{b:02x}" for b in random.randbytes(3)]
            )
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
        try:
            os.remove(CONSOLES / self.id)
        except OSError:
            pass

        if self._sub:
            try:
                self._sub.kill()
                # reap zombies
                self._sub.communicate()
                self._sub = None
            except Exception:
                pass
        self._volume_cleanup()
        self._meta_shutdown()

    def _volume_cleanup(self):
        # Only cleanup if the volume is not an image
        # TODO: leak volumes instead of cleaning implicitly?
        if self._image != self._volume:
            logging.debug("dropping instance volumes")
            self._volume.unlink()

    async def _spawn(self, arch, volume_file, metadata_port, flavor, bridge=None):
        nic_model = "virtio-net-pci"
        if arch == "s390x":
            nic_model = "virtio"

        args = [
            f"qemu-system-{arch}",
            "-nographic",
            "-uuid",
            self.id,
            "-serial",
            f"file:{CONSOLES / self.id}",
            "-drive",
            f"file={volume_file},if=virtio",
            "-m",
            f"{flavor['ram']}M",
            # metadata-only network
            "-nic",
            f"user,hostname={self.hostname},model={nic_model},net=169.254.169.0/24,restrict=on,"
            f"guestfwd=tcp:169.254.169.254:80-cmd:nc 127.0.0.1 {metadata_port}",
        ]

        match arch:
            case "x86_64":
                args.append("-enable-kvm")
                args.extend(
                    # pants on fire
                    ["-smbios", "type=1,product=OpenStack Compute"]
                )
            case "aarch64":
                # impdef is "less secure" but way faster
                args.extend(["-machine", "virt", "-cpu", "max,pauth-impdef=on"])
                args.extend(["-bios", "/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"])

        if (ncpus := flavor["vcpus"]) > 1:
            args.append("-smp")
            args.append(str(ncpus))

        if self._br:
            args.append("-nic")
            args.append(f"bridge,model={nic_model},br={self._br},mac={self._br_hwadd}")
        logging.debug("spawning %r", args)

        # del and async don't play together.
        self._sub = subprocess.Popen(
            args, stdin=open("/dev/null"), stdout=open("/dev/null", "w")
        )

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
            data["status"] = "BUILD"

        if self._sub and self._sub.returncode is not None:
            data["status"] = "ERROR"
        return data


@routes.get("/servers")
@routes.get("/servers/detail")
async def list_(request: web.Request) -> web.Response:
    return web.json_response(
        {"servers": [instance.info() for instance in instances.values()]}
    )


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
    config = request.config_dict["app_config"]
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
    volume = await make_volume_from_image(uuid, image, flavor["disk"])

    instance = instances[uuid] = Instance(
        uuid,
        data["name"],
        image,
        flavor,
        volume,
        data.get("user_data"),
        data.get("key_name"),
        data.get("hostname"),
        bridge,
        tags=data.get("tags"),
        metadata=data.get("metadata"),
    )
    await instance.setup()
    return web.json_response(
        {"server": {"id": uuid, "links": []}},
        headers={"Location": f"{request.url}/{uuid}"},
        status=202,
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


@routes.post("/servers/{server_id}/action")
async def server_action(request: web.Request) -> web.Response:
    server_id = request.match_info["server_id"]
    for action in await request.json():
        if action == "os-getConsoleOutput":
            async with aiofiles.open(CONSOLES / server_id) as f:
                return web.json_response({"output": await f.read()})

    return web.json_response()


@routes.get("/servers/{server_id}/os-security-groups")
async def get_server_secgroups(request: web.Request) -> web.Response:
    return web.json_response({"security-groups": []})


@routes.get("/servers/{server_id}/os-interface")
async def get_server_ports(request: web.Request) -> web.Response:
    return web.json_response({"interfaceAttachments": []})


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
    return web.json_response({"keypair": {"name": name}})


@routes.get("/os-keypairs")
async def list_keypair(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "keypairs": [
                {"keypair": {"name": name, "type": "ssh"}}
                for name in await aiofiles.os.listdir(KEYPAIRS)
            ]
        }
    )


@routes.delete("/os-keypairs/{name}")
async def delete_keypair(request: web.Request) -> web.Response:
    name = request.match_info["name"].replace("/", "_")
    try:
        await aiofiles.os.remove(KEYPAIRS / name)
    except FileNotFoundError:
        return web.Response(status=404)
    return web.Response(status=204)


@routes.get("/flavors")
@routes.get("/flavors/detail")
async def get_flavors_details(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "flavors": [
                {"name": k, "id": k, **v}
                for k, v in request.config_dict["app_config"]["flavors"].items()
            ]
        }
    )


@routes.get("/os-availability-zone")
async def list_az(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "availabilityZoneInfo": [
                {
                    "hosts": None,
                    "zoneName": AZ_NAME,
                    "zoneState": {"available": True},
                }
            ]
        }
    )


app.add_routes(routes)
