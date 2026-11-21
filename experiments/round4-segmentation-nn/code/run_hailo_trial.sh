#!/usr/bin/env bash
# #406 trial A: run the container steps of hailo_compile.py for one chip and optimisation level, CPU only.
#
#   run_hailo_trial.sh <hailo8|hailo10h> <level> [steps...]     default steps: parse optimize emulate compile profile
#
# Every docker run is capped at 10 CPUs and 16 GB (another job trains on the GPU and needs CPU for data loading).
# The work root and this code folder are mounted at their host paths; the container runs as the host user and
# its working directory is the run folder, so the DFC's own log files land there.
set -euo pipefail
CHIP=$1; LEVEL=$2; shift 2
STEPS=("${@:-parse optimize emulate compile profile}"); STEPS=(${STEPS[*]})
NN=/home/txoof/temp.nobackup/npec-406-nn
CODE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case $CHIP in hailo8) IMAGE=npec406/hailo-hailo8:dfc-3.33.1 ;; hailo10h) IMAGE=npec406/hailo-hailo10h:dfc-5.1.0 ;; *) exit 2 ;; esac
D=$NN/hailo/trial-A/${CHIP}_L$LEVEL
NAME=plantseg_s2f0
mkdir -p "$D"
dk() {
    docker run --rm -i --cpus=10 --memory=16g --memory-swap=16g --ipc=host --user "$(id -u):$(id -g)" \
        -e PYTHONPYCACHEPREFIX=/tmp/pycache -v "$NN":"$NN" -v "$CODE":"$CODE":ro -w "$D" \
        --name "npec406-trialA-$CHIP-L$LEVEL-$1-$$" "$IMAGE" "${@:2}"
}
for s in "${STEPS[@]}"; do
    echo "=== $(date -u +%FT%TZ) $CHIP level $LEVEL: $s"
    if [ "$s" = profile ]; then
        dk "$s" hailo profiler "$D/${NAME}_compiled.har" --hef "$D/${NAME}_$CHIP.hef" \
            --out-path "$D/${NAME}_profile.html" --csv "$D/${NAME}_profile.csv" > "$D/$s.log" 2>&1 || echo "profile failed"
    else
        dk "$s" python "$CODE/hailo_compile.py" "$s" --arch "$CHIP" --level "$LEVEL" > "$D/$s.log" 2>&1
    fi
    tail -n 3 "$D/$s.log"
done
echo "=== $(date -u +%FT%TZ) $CHIP level $LEVEL: done"
