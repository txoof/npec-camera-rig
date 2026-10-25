# Running the rig as a service

`npec-rig.service` starts the web console at boot and restarts it whenever it exits, so a
running experiment carries on after a reboot or a crash (#62). The experiment's state is in
`rig.db`, and the scheduler takes the next photo slot from the experiment's start time.

After a reboot the camera starts cold, and a cold start is measured to shift readings
(`docs/metrology-log.md`). Every photo in the first 60 minutes after the Pi starts is flagged as
taken in the cold-start window, so those photos say they are not covered by the validation bands.

The service runs whatever is checked out in `/home/pi/npec_camera_rig`. Keep that checkout on
`main` with no local changes: after a crash or a reboot, the code there is the code that runs.

## Install

Between experiments only, never during one. First check:

1. No experiment is running (Experiments page).
2. No server started by hand is running: `ps -eo pid,args | grep [u]vicorn` shows nothing. If one
   is, stop it with SIGTERM and wait until its PID is gone (CLAUDE.md). Two servers cannot share
   port 8000 or the camera.

Then:

```bash
sudo cp deploy/npec-rig.service /etc/systemd/system/npec-rig.service
sudo systemctl daemon-reload
sudo systemctl enable --now npec-rig
```

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

## Trying a branch on a rig that runs the service

The service restarts the app 5 s after it exits, so do not stop the app by its PID to run a
branch server: the service would start the main checkout again and the two would fight over port
8000 and the camera. Stop the service instead, run the branch server, then start the service
again when done:

```bash
sudo systemctl stop npec-rig
# run the branch server (CLAUDE.md, Restarting the port 8000 server), try it, stop it with SIGTERM
sudo systemctl start npec-rig
```

A service that cannot start (port taken, an import error) is tried again every 5 s with no limit.
That keeps an experiment going through short faults. Telling someone that it keeps failing is a
later slice of #62.

## Test bench

`test-bench-replay.conf` is a drop-in for the test bench Pi only (#279). Instructions are in the
file.
