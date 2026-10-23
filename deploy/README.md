# Running the rig as a service

`npec-rig.service` starts the web console at boot and restarts it whenever it exits, so a
running experiment carries on after a reboot or a crash (#62). The experiment's state is in
`rig.db`, and the scheduler takes the next photo slot from the experiment's start time, so nothing
else needs to be restored.

## Install

```bash
sudo cp deploy/npec-rig.service /etc/systemd/system/npec-rig.service
sudo systemctl daemon-reload
sudo systemctl enable --now npec-rig
```

Before installing on a rig that runs an experiment, stop the server that was started by hand
(SIGTERM, then wait until its PID is gone; see CLAUDE.md). Two servers cannot share port 8000
or the camera. Do this between experiments, never during one.

## Check

```bash
systemctl status npec-rig            # active (running)
journalctl -u npec-rig -n 50         # the app's output
```

## Stop or restart

```bash
sudo systemctl restart npec-rig      # SIGTERM, the camera is closed cleanly
sudo systemctl stop npec-rig         # stays stopped until started or the next boot
```

## Test bench

`test-bench-replay.conf` is a drop-in for the test bench Pi only (#279). Instructions are in the
file.
