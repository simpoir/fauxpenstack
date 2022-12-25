A stub for running stuff in something vaguely reminiscent of OpenStack.

This was written while waiting for a swift upload to complete, mostly in order
to run tests in a timely fashion. There is no setup, but it's incomplete, kinda
insecure and it doesn't scale.

The name is a pun of french "faux" (fake) and opentack.

## Setup

Requires python3.10+ and poetry.

First thing first, edit `auth.json` with a new secret and change the user/pass.
of foouser. You might also want to change the `net_bridges` to match any bridge
you have, if you care about network.

If you want to actually run VMs, you also need qemu
If you want your VMs to be reachable they also need some extra setup.
Running `make ubuntu-deps` fulfills both of those needs.


Easiest way to set is to just run `make install` as a user.
It'll create a socket activation user service running from the source folder,
so it doesn't keep running when you don't need it.
Can be removed with `make uninstall`

The `auth.json` contains basic credentials and ACLs.
"glue" (keystone) is just a user mapping in `auth.json``
"brisk" (swift) buckets are in `buckets` and are just folders.
"peek" (glance) images are in `images` the same.
"pulsar" (nova) VMs are just qemu processes, can be killed. SSH keys are in `keypairs`
