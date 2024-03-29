A stub for running stuff in something vaguely reminiscent of OpenStack.

This was written while waiting for a swift upload to complete, mostly in order
to run tests in a timely fashion. There is no setup, but it's incomplete, kinda
insecure and it doesn't scale.

The name is a pun of french "faux" (fake) and opentack.

## Setup

Requires python3.10+ and poetry.

First thing first, copy `conf.toml.example` to `conf.toml` with a new secret
and change the user/pass of foouser. You might also want to change the
`net_bridges` to match any bridge you have, if you care about network.

If you want to actually run VMs, you also need qemu
If you want your VMs to be reachable they also need some extra setup.
Running `make ubuntu-deps` fulfills both of those needs.

If you want to run the service once, `poetry run fauxpenstack -v`

Easiest way to set is to just run `make install` as a user.
It'll create a socket activation user service running from the source folder,
so it doesn't keep running when you don't need it.
Can be removed with `make uninstall`

The `conf.toml` contains basic credentials and ACLs.
"glue" (keystone) is just a user mapping in `conf.toml``
"brisk" (swift) buckets are in `buckets` and are just folders.
"peek" (glance) images are in `images` the same.
"pulsar" (nova) VMs are just qemu processes, can be killed.
SSH keys are in `keypairs`. There is no volume management.


## Using with juju

Using juju with custom clouds can be fiddly due to having to manage juju
metadata. That being said, controllers and simple units (e.g. ubuntu) appear
to work at least partially.
For this, you'll need a bridge with dhcp, configured in conf.toml and you'll
need to tweak your novarc to point to the public interface running the service
(because instances need to reach it from within).


```
wget <cloud_image_url> images/123:my_img_name.x86_64.qcow2
source novarc.sample
juju add-cloud faux
# select openstack and fill questions.

juju add-credential faux
# more questions. Use keystone v3 and enter anything as a tenant/project

# replace series/id to match the downloaded image.
# Alternatively, you could configure a local image metadata stream, but this
# is out-of-scope. See the upstream juju docs for that.
juju bootstrap faux --bootstrap-image 123 --bootstrap-series focal --bootstrap-constraints arch=amd64
juju deploy ubuntu  --series focal

juju ssh ubuntu/0
exit

juju kill-controller faux-default --timeout 1s -y
# This is as far as things have been tested, which is plenty for a mock service.
```
