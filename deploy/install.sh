#!/bin/bash
# Install or update the npec-rig service from this checkout (#62). Run on the rig, between
# experiments: sudo deploy/install.sh
#
# Installs npec-rig.service and the 120 s limit on the wait for the network time, enables the
# wait and the service, and starts the service if it is not running. A running service is not
# restarted: a restart during an experiment would interrupt it. It says when one is needed.
#
# Settings that differ per rig (environment variables) go in a drop-in that this script never
# touches: /etc/systemd/system/npec-rig.service.d/*.conf (test-bench-replay.conf is one).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"

install -m 0644 "$here/npec-rig.service" /etc/systemd/system/npec-rig.service
install -d /etc/systemd/system/systemd-time-wait-sync.service.d
install -m 0644 "$here/time-wait-limit.conf" \
    /etc/systemd/system/systemd-time-wait-sync.service.d/limit.conf
systemctl daemon-reload
systemctl enable --quiet systemd-time-wait-sync npec-rig

if systemctl is-active --quiet npec-rig; then
    echo "Installed. npec-rig keeps its old settings until it is restarted:"
    echo "  sudo systemctl restart npec-rig   (only when no experiment is running)"
else
    systemctl start npec-rig
    echo "Installed and started npec-rig."
fi
