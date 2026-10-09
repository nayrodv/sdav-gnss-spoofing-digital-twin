# Digital Twin Guard: PX4/Gazebo Proof-of-Concept Starter Package

This package implements the minimum research scaffold for the revised manuscript.
It is **not flight-certified** and has not been executed against PX4 inside the ChatGPT container.
The Python files have been syntax-checked. Run and calibrate them in a local PX4/ROS 2 environment.

## Intended setup

1. Build and run PX4 SITL with Gazebo, for example: `make px4_sitl gz_x500`.
2. Start the Micro XRCE-DDS Agent. PX4 SITL normally starts its client on UDP port 8888.
3. Place this package and `px4_msgs` in a ROS 2 workspace, then run `colcon build`.
4. Source the workspace and run `ros2 launch digital_twin_guard poc.launch.py`.
5. Record `/fmu/out/vehicle_gps_position`, `/fmu/out/vehicle_local_position`,
   `/fmu/out/timesync_status`, and `/digital_twin_guard/anomaly` in a rosbag.
6. In the PX4 shell, enable failure injection and execute `run_abrupt_spoofing.sh` commands.

## Official PX4 capabilities used

- PX4 exposes `vehicle_gps_position` and `vehicle_local_position` through its DDS topic configuration.
- The uXRCE-DDS bridge provides bidirectional PX4/ROS 2 exchange.
- PX4 SITL failure injection supports GPS `off`, `stuck`, and `wrong` modes.

## Gradual carry-off attack

Current generic PX4 GPS failure injection is sufficient for an abrupt `wrong` GPS test but not a realistic
controlled carry-off profile. The included `offline_gradual_spoofing.py` supports a reproducible replay-based
first experiment. A higher-fidelity next step is a Gazebo sensor plugin or simulator-specific GPS bias injector.

## Required calibration before publication

- Establish benign residual distributions for each scenario and vehicle model.
- Replace the constant-velocity twin with a validated dynamic or estimator-based prediction model.
- Add an independent localization source (visual odometry, optical flow, or secondary navigation estimate).
- Evaluate precision, recall, false-positive rate, detection latency, maximum deviation, CPU load, and message rate.
- Connect alerts to a deterministic response-policy test harness before commanding PX4.
