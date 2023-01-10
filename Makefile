#!/usr/bin/make -f

SVC_NAME=fauxpenstack
SVC_PORT=8855

.PHONY: install
install:
	poetry install
	SVC_PORT=$(SVC_PORT) envsubst < $(SVC_NAME).service > $(HOME)/.config/systemd/user/$(SVC_NAME).service
	SVC_PORT=$(SVC_PORT) envsubst < $(SVC_NAME).socket > $(HOME)/.config/systemd/user/$(SVC_NAME).socket
	systemctl enable --now --user $(SVC_NAME).socket
	systemctl status --user $(SVC_NAME).socket

.PHONY: uninstall
uninstall:
	systemctl disable --now --user $(SVC_NAME).service || true
	systemctl disable --now --user $(SVC_NAME).socket || true
	rm -f $(HOME)/.config/systemd/user/$(SVC_NAME).socket
	rm -f $(HOME)/.config/systemd/user/$(SVC_NAME).service

.PHONY: ubuntu-deps
ubuntu-deps:
	sudo apt-get -y install qemu-system-x86 qemu-system-arm qemu-system-ppc qemu-system-s390x
	@echo "If you intend to spin VMs and to use a virtual network, I can update " \
		"setup qemu-bridge-helper to allow users to attach to the configured bridges. " \
		"This is unnecessary if fauxpenstack runs as root."
	@echo "Should I do that? (type YES in all caps or no)"
	@read X; if [ "$$X" = "YES" ]; then \
		sudo chmod +s /usr/lib/qemu/qemu-bridge-helper; \
		test -f /etc/qemu/bridge.conf || sudo mkdir -p /etc/qemu; \
		for brname in $$(awk 'BEGIN {br=0} /\\[/ {br=0} match($$0, /= *"([^"]+)"/, a) {if (br) {print a[1]}} /\\[net_bridges/ {br=1}' conf.toml | sort -u); do \
		  grep $$brname /etc/qemu/bridge.conf || echo "allow $$brname" | sudo tee -a /etc/qemu/bridge.conf ; \
		done; \
	fi
	@echo all done.
