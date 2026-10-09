# PX4/Gazebo Next-Stage Execution Protocol

This file describes the next validation stage that was **not executable in the current ChatGPT environment**.

## 1. Target environment

Use a supported Linux development environment with PX4, Gazebo, and ROS 2. Record exact OS, PX4 release/commit, Gazebo release, ROS 2 distribution, CPU, RAM, and compiler versions in the manuscript.

PX4's current documentation supports Gazebo SITL with the X500 quadrotor using:

```bash
cd PX4-Autopilot
make px4_sitl gz_x500
```

A headless run can use:

```bash
HEADLESS=1 make px4_sitl gz_x500
```

PX4 uses the uXRCE-DDS bridge for PX4/ROS 2 data exchange.

## 2. Minimum experiment

Run the same six scenarios used in the reduced-order proof of concept:

1. nominal operation;
2. temporary benign GNSS degradation;
3. benign communication/twin delay;
4. abrupt GNSS spoofing;
5. gradual carry-off spoofing;
6. spoofing combined with communication delay.

Do not use PX4's generic `failure gps wrong` result as the only spoofing model. It is useful as a failure-handling smoke test, but the publication experiment requires a controlled bias injector with documented onset, direction, magnitude/rate, and duration.

## 3. Required data streams

At minimum record:

- vehicle GNSS position/velocity;
- local position/velocity estimate;
- estimator innovation/test-ratio information if exposed by the selected PX4 release;
- actuator or vehicle-command state needed to reconstruct the twin prediction;
- simulator ground truth (evaluation only; never supplied to the detector);
- twin state and synchronization age;
- multi-source residuals;
- classifier probability/decision;
- assurance gate state;
- selected response;
- vehicle mode changes;
- timing and resource measurements.

## 4. Controlled spoofing injector

The injector should modify the GNSS measurement before it is consumed by the estimator while preserving an untouched simulator ground-truth channel for evaluation. Two primary profiles are required:

- abrupt bias: a documented step in position and, when used, velocity;
- gradual carry-off: a continuous bias whose position derivative is consistent with the injected velocity bias.

Test multiple magnitudes/rates. Do not select only attacks that are obviously detectable.

## 5. Independent navigation evidence

Use a GNSS-independent estimator available in the selected simulator configuration, such as visual odometry, optical flow, or a deliberately configured inertial/vision estimate. Document its failure modes and uncertainty. The independent source must not be derived from the attacked GNSS signal.

## 6. Response experiment

Compare at least:

- detection only;
- a fixed fail-safe response;
- the proposed bounded context-aware response.

Use the same attack seeds/profiles across policies so the comparison is paired. Do not claim that mission continuation is safer than return-to-base unless the safety model supports that conclusion.

## 7. Required metrics

Detection:
- precision, recall, F1;
- false-positive and false-negative rates;
- detection latency;
- weak-attack sensitivity.

Operational:
- maximum true route deviation;
- recovery time under a defined criterion;
- mission completion/termination;
- safety-boundary violations where the boundary is justified by the test scenario.

Implementation:
- detector processing latency;
- CPU and memory use;
- communication load;
- twin synchronization age;
- end-to-end response time.

## 8. Reproducibility

Archive:

- PX4 commit/release;
- Gazebo/ROS versions;
- attack-injection source code;
- detector source code;
- configuration files;
- mission file/waypoints;
- trial seeds;
- raw logs;
- analysis scripts.

## Primary software reference

Meier, L., and The PX4 Contributors. *PX4 Autopilot*. Zenodo. DOI: 10.5281/zenodo.595432.

Official PX4 documentation consulted for this protocol: current Gazebo SITL and uXRCE-DDS guidance.
