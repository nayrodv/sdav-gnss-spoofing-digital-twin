#!/usr/bin/env bash
set -euo pipefail
# Run from the PX4 SITL console after enabling failure injection.
param set SYS_FAILURE_EN 1
# Abrupt erroneous GPS position supported by current PX4 SITL failure injection.
failure gps wrong
sleep 12
failure gps ok
