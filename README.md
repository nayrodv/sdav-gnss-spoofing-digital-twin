# SDAV GNSS Spoofing Digital Twin Reproducibility Package

Reproducibility materials for the manuscript **Digital Twin Architecture for Cyber Resilient Software Defined Aerial Vehicles: GNSS Spoofing Detection and Bounded Mission Response**.

This repository contains the executed reduced-order proof of concept used to evaluate multi-source GNSS spoofing detection, digital twin evidence, assurance constraints, GNSS isolation, fixed return-to-base response, and bounded mission continuation.

## Scope

The executed model is a three-dimensional translational cyber-physical surrogate. It includes:

- waypoint-following vehicle dynamics;
- nominal GNSS position and velocity observations;
- a GNSS-independent odometry surrogate with measurement noise and random-walk bias;
- an external digital twin predictor corrected with independent odometry;
- abrupt and gradual carry-off GNSS spoofing;
- benign GNSS degradation and communication delay;
- spoofing combined with communication delay;
- covariance-normalized digital twin, independent-navigation, and GNSS-temporal residuals;
- a class-balanced logistic-regression multi-source detector;
- Brier score and 10-bin expected calibration error diagnostics;
- temporal persistence and a stale-twin independent-evidence gate;
- GNSS isolation;
- fixed route-retracing return to base;
- bounded mission continuation using independent navigation.

## Important validation boundary

This repository does **not** constitute PX4, Gazebo, ROS 2, RF-level GNSS, hardware-in-the-loop, flight-test, airworthiness, or operational cyber-resilience validation. Those environments were not used for the reported experiment. The `experimental/px4_gazebo_starter_unexecuted/` directory is retained only as clearly labeled future-stage material and was not used to generate the manuscript results.

## Repository structure

```text
.
├── README.md
├── LICENSE
├── CITATION.cff
├── requirements.txt
├── .gitignore
├── poc_experiment.py
├── run_all.py
├── run_response_stage.py
├── run_one_response_strategy.py
├── run_stress_test.py
├── aggregate_response.py
├── statistical_analysis.py
├── make_figures.py
├── create_report_docx.py
├── results/
├── figures/
├── docs/
├── experimental/
├── src/
├── config/
└── data/
```

The scripts remain at repository root because the executed package used file-relative paths. They were not refactored after the experiment.

## Reference environment

The proof-of-concept package records Python 3.13.5 as the execution version. The accompanying `requirements.txt` pins the Python packages used by the current reproducibility environment.

## Installation

Create a virtual environment, activate it, and install the dependencies:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Reproduce the complete experiment

From the repository root:

```bash
python run_all.py
```

The full pipeline performs calibration, classifier development, held-out testing, response-policy evaluation, weak-attack stress testing, statistical analysis, and figure generation.

## Experimental partitions

- Residual covariance calibration: 25 nominal trials.
- Benign threshold calibration: 10 nominal, 10 temporary GNSS degradation, and 10 communication-delay trials.
- Classifier training: 120 trials, 20 from each of six scenarios.
- Validation: 48 trials, 8 from each scenario.
- Held-out test: 120 trials, comprising 60 attack and 60 benign trials.
- Response-policy evaluation: 360 runs, using matched scenario seeds across three response policies.
- Weak-attack stress test: 90 attack trials, 30 from each attack scenario.

Calibration, training, validation, and held-out testing use disjoint random seeds.

## Main manuscript results represented in the package

On the held-out trial set:

- GNSS-only temporal baseline: 0 of 60 attacks detected and 1 of 60 benign trials alerted.
- Digital twin residual baseline: 54 of 60 attacks detected and 1 of 60 benign trials alerted.
- Multi-source detector with assurance: 60 of 60 attacks detected and 0 of 60 benign trials alerted.

The weak-attack stress test generated eventual alerts in all 90 attack trials, with substantially longer latency for weak gradual and communication-degraded cases.

For the 60 attack trials per response policy, median maximum route deviation was 17.39 m with detection only, 2.89 m with fixed return to base, and 2.63 m with bounded continuation.

These results are conditional on the synthetic simulator, declared attack family, sensor assumptions, and independent-navigation surrogate. They should not be generalized to physical aircraft without subsequent validation.

## Key outputs

`results/` contains detector parameters, calibration artifacts, trial-level outputs, confidence intervals, paired statistical tests, response outcomes, stress-test results, and requirement-verification status.

`figures/` contains the figures generated from the executed proof of concept.

`docs/` contains the executed proof-of-concept report, environment capability check, and next-stage PX4 protocol.

The repository includes a GitHub Actions workflow that reruns the full pipeline on changes to the reproducibility source files and commits the regenerated results, figures, and report back to the repository. This keeps the public artifacts synchronized with the executable code.

## Citation

GitHub will display a **Cite this repository** option using `CITATION.cff`. The manuscript DOI can be added after publication. For archival citation, create a GitHub release and archive it in Zenodo to obtain a permanent DOI.

## License

MIT License. See `LICENSE`.
