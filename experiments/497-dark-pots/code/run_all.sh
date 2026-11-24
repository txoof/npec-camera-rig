#!/bin/bash
# Runs the full-photo sweeps of log 46 for form $1 (A or B). Photos: ~/temp.nobackup/rig-copies/ac-testing/497-dark-pots/
cd "$(dirname "$0")/../../.." || exit 1
R=/home/txoof/temp.nobackup/rig-copies/ac-testing/497-dark-pots; A=experiments/497-dark-pots/data/api; D=experiments/497-dark-pots/data
export FORM=$1 PYTHONPATH=$PWD/src
specs=()
for f in 2026-11-18/130053_642253 2026-11-20/130053_661727 2026-11-20/200053_650433 2026-11-22/090053_635081 2026-11-22/130053_643712 2026-11-22/200053_652827 2026-11-23/090053_682903 2026-11-23/110053_651340 2026-11-23/120053_763671 2026-11-23/130053_611736 2026-11-23/140053_650696; do
  specs+=("$R/e18/$f.jpg:$A/e18_${f//\//_}.json"); done
.venv/bin/python experiments/497-dark-pots/code/run_photos.py e18 $D/sweep_e18_$1.csv "${specs[@]}" > /tmp/run_e18_$1.log 2>&1 &
specs=()
for f in 080901_918763 083401_915111 090401_910945 092901_914185 094401_914003 095901_923968; do specs+=("$R/e20/$f.jpg:$A/e20_$f.json"); done
.venv/bin/python experiments/497-dark-pots/code/run_photos.py e20 $D/sweep_e20_$1.csv "${specs[@]}" > /tmp/run_e20_$1.log 2>&1 &
wait
