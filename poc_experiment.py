#!/usr/bin/env python3
"""Reproducible reduced-order proof-of-concept for the SDAV GNSS-spoofing architecture.

This is NOT PX4/Gazebo and is not flight validation. It is an executable cyber-physical
surrogate that implements the manuscript's architecture logic:
  vehicle dynamics -> GNSS + independent odometry -> external digital twin prediction
  -> normalized residuals -> multi-source classifier -> assurance gate -> bounded response.

The model is intentionally simple and all numerical parameters are declared as simulation
parameters rather than real UAV specifications.
"""
from __future__ import annotations

import json
import math
import os
import platform
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import sklearn
import scipy

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
RESULTS.mkdir(exist_ok=True)
FIGURES.mkdir(exist_ok=True)

SCENARIOS = ["nominal", "gnss_degradation", "comm_delay", "abrupt_spoof", "gradual_spoof", "spoof_comm"]
BENIGN = {"nominal", "gnss_degradation", "comm_delay"}
ATTACK = {"abrupt_spoof", "gradual_spoof", "spoof_comm"}

@dataclass
class SimConfig:
    dt: float = 0.05                    # 20 Hz dynamics/controller
    duration_s: float = 90.0
    gnss_period_s: float = 0.20         # 5 Hz GNSS
    desired_speed_mps: float = 6.0
    max_accel_mps2: float = 2.0
    waypoint_radius_m: float = 5.0
    attack_start_s: float = 30.0
    event_end_s: float = 50.0

    # declared simulation noise parameters (not sensor specifications)
    process_accel_sigma: float = 0.05
    gnss_pos_sigma_m: float = 1.20
    gnss_vel_sigma_mps: float = 0.15
    ind_pos_sigma_m: float = 0.55
    ind_vel_sigma_mps: float = 0.10
    ind_pos_bias_rw_sigma: float = 0.003
    ind_vel_bias_rw_sigma: float = 0.0007

    # state-estimator reliance on GNSS before isolation
    gnss_nav_weight: float = 0.75

    # twin correction using GNSS-independent odometry
    twin_pos_gain: float = 0.08
    twin_vel_gain: float = 0.15

    # experimental completion/safety metrics
    completion_radius_m: float = 7.0
    recovery_route_threshold_m: float = 3.0
    recovery_hold_s: float = 1.0

    # mission waypoints [m]
    waypoints: Tuple[Tuple[float, float, float], ...] = (
        (0.0, 0.0, 30.0),
        (100.0, 0.0, 30.0),
        (100.0, 100.0, 35.0),
        (200.0, 100.0, 35.0),
        (200.0, 0.0, 30.0),
    )

CFG = SimConfig()


def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else np.zeros_like(v)


def clip_norm(v: np.ndarray, max_norm: float) -> np.ndarray:
    n = np.linalg.norm(v)
    if n <= max_norm or n < 1e-12:
        return v
    return v * (max_norm / n)


def point_segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom < 1e-12:
        return float(np.linalg.norm(p - a))
    t = float(np.dot(p - a, ab) / denom)
    t = min(1.0, max(0.0, t))
    proj = a + t * ab
    return float(np.linalg.norm(p - proj))


def route_distance(p: np.ndarray, waypoints: np.ndarray) -> float:
    return min(point_segment_distance(p, waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1))


def ece_score(y_true: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if not np.any(mask):
            continue
        acc = np.mean(y_true[mask])
        conf = np.mean(p[mask])
        ece += np.mean(mask) * abs(acc - conf)
    return float(ece)


def sample_attack_parameters(scenario: str, rng: np.random.Generator) -> Dict[str, float]:
    theta = rng.uniform(0, 2 * np.pi)
    d = np.array([np.cos(theta), np.sin(theta), 0.0])
    params: Dict[str, float] = {
        "attack_dir_x": float(d[0]),
        "attack_dir_y": float(d[1]),
        "abrupt_pos_bias_m": 0.0,
        "abrupt_vel_bias_mps": 0.0,
        "gradual_rate_mps": 0.0,
        "comm_delay_s": 0.0,
        "degradation_sigma_multiplier": 1.0,
    }
    if scenario == "abrupt_spoof":
        params["abrupt_pos_bias_m"] = float(rng.uniform(12.0, 25.0))
        params["abrupt_vel_bias_mps"] = float(rng.uniform(0.0, 0.8))
    elif scenario in {"gradual_spoof", "spoof_comm"}:
        params["gradual_rate_mps"] = float(rng.uniform(0.25, 0.80))
    if scenario in {"comm_delay", "spoof_comm"}:
        params["comm_delay_s"] = float(rng.uniform(0.55, 1.20))
    if scenario == "gnss_degradation":
        params["degradation_sigma_multiplier"] = float(rng.uniform(2.5, 4.5))
    return params


def attack_bias(t: float, scenario: str, params: Dict[str, float], cfg: SimConfig) -> Tuple[np.ndarray, np.ndarray]:
    pos = np.zeros(3)
    vel = np.zeros(3)
    if t < cfg.attack_start_s:
        return pos, vel
    d = np.array([params["attack_dir_x"], params["attack_dir_y"], 0.0])
    if scenario == "abrupt_spoof":
        pos = d * params["abrupt_pos_bias_m"]
        vel = d * params["abrupt_vel_bias_mps"]
    elif scenario in {"gradual_spoof", "spoof_comm"}:
        tau = t - cfg.attack_start_s
        rate = params["gradual_rate_mps"]
        pos = d * min(rate * tau, 30.0)
        vel = d * rate if rate * tau < 30.0 else np.zeros(3)
    return pos, vel


def comm_delay(t: float, scenario: str, params: Dict[str, float], cfg: SimConfig) -> float:
    if scenario in {"comm_delay", "spoof_comm"} and cfg.attack_start_s <= t <= cfg.event_end_s:
        return params["comm_delay_s"]
    return 0.0


def generate_gnss(
    p: np.ndarray,
    v: np.ndarray,
    t: float,
    scenario: str,
    params: Dict[str, float],
    rng: np.random.Generator,
    cfg: SimConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    mult = 1.0
    benign_bias = np.zeros(3)
    if scenario == "gnss_degradation" and cfg.attack_start_s <= t <= cfg.attack_start_s + 7.0:
        mult = params["degradation_sigma_multiplier"]
        # bounded, transient multipath-like bias surrogate; not labeled as an RF model
        phase = 2 * np.pi * (t - cfg.attack_start_s) / 7.0
        benign_bias = np.array([2.0 * np.sin(phase), 1.5 * np.cos(0.7 * phase), 0.4 * np.sin(0.5 * phase)])
    pos_noise = rng.normal(0.0, cfg.gnss_pos_sigma_m * mult, 3)
    vel_noise = rng.normal(0.0, cfg.gnss_vel_sigma_mps * mult, 3)
    a_pos, a_vel = attack_bias(t, scenario, params, cfg)
    return p + pos_noise + benign_bias + a_pos, v + vel_noise + a_vel


def controller(nav_p: np.ndarray, nav_v: np.ndarray, target: np.ndarray, cfg: SimConfig) -> np.ndarray:
    delta = target - nav_p
    dist = np.linalg.norm(delta)
    speed = cfg.desired_speed_mps * min(1.0, max(0.25, dist / 20.0))
    v_des = unit(delta) * speed
    a = 1.1 * (v_des - nav_v)
    return clip_norm(a, cfg.max_accel_mps2)


def initial_state(cfg: SimConfig) -> Tuple[np.ndarray, np.ndarray]:
    p = np.array(cfg.waypoints[0], dtype=float)
    v = np.zeros(3)
    return p, v


def simulate_trace(seed: int, scenario: str, cfg: SimConfig = CFG) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Open-loop-with-respect-to-detector trace. GNSS attack can influence vehicle controller."""
    rng = np.random.default_rng(seed)
    params = sample_attack_parameters(scenario, rng)
    wp = np.array(cfg.waypoints, dtype=float)
    p, v = initial_state(cfg)
    ind_pos_bias = np.zeros(3)
    ind_vel_bias = np.zeros(3)
    ind_p = p.copy()
    ind_v = v.copy()
    nav_p = p.copy()
    nav_v = v.copy()
    twin_p = p.copy()
    twin_v = v.copy()
    target_idx = 1
    gnss_p = p.copy()
    gnss_v = v.copy()
    prev_gnss_p = None
    prev_gnss_v = None
    prev_gnss_t = None

    steps = int(round(cfg.duration_s / cfg.dt)) + 1
    gnss_stride = max(1, int(round(cfg.gnss_period_s / cfg.dt)))
    hist_ind_p: List[np.ndarray] = []
    hist_ind_v: List[np.ndarray] = []
    hist_cmd: List[np.ndarray] = []
    rows: List[Dict[str, float]] = []

    for k in range(steps):
        t = k * cfg.dt
        # Independent odometry surrogate with low random-walk bias.
        ind_pos_bias += rng.normal(0.0, cfg.ind_pos_bias_rw_sigma, 3)
        ind_vel_bias += rng.normal(0.0, cfg.ind_vel_bias_rw_sigma, 3)
        ind_p = p + ind_pos_bias + rng.normal(0.0, cfg.ind_pos_sigma_m, 3)
        ind_v = v + ind_vel_bias + rng.normal(0.0, cfg.ind_vel_sigma_mps, 3)

        # Update mission target using current navigation estimate.
        if target_idx < len(wp) - 1 and np.linalg.norm(nav_p - wp[target_idx]) <= cfg.waypoint_radius_m:
            target_idx += 1
        a_cmd = controller(nav_p, nav_v, wp[target_idx], cfg)

        # Truth dynamics: reduced-order translational vehicle surrogate.
        a_true = a_cmd + rng.normal(0.0, cfg.process_accel_sigma, 3)
        v = v + a_true * cfg.dt
        p = p + v * cfg.dt

        hist_ind_p.append(ind_p.copy())
        hist_ind_v.append(ind_v.copy())
        hist_cmd.append(a_cmd.copy())

        # Twin propagation + delayed correction from GNSS-independent telemetry.
        delay_s = comm_delay(t, scenario, params, cfg)
        delay_steps = int(round(delay_s / cfg.dt))
        idx = max(0, k - delay_steps)
        delayed_cmd = hist_cmd[idx]
        delayed_ind_p = hist_ind_p[idx]
        delayed_ind_v = hist_ind_v[idx]
        twin_p = twin_p + twin_v * cfg.dt + 0.5 * delayed_cmd * cfg.dt**2
        twin_v = twin_v + delayed_cmd * cfg.dt
        twin_p += cfg.twin_pos_gain * (delayed_ind_p - twin_p)
        twin_v += cfg.twin_vel_gain * (delayed_ind_v - twin_v)

        if k % gnss_stride == 0:
            gnss_p, gnss_v = generate_gnss(p, v, t, scenario, params, rng, cfg)
            # Current navigation estimator surrogate: GNSS-dominant fusion.
            w = cfg.gnss_nav_weight
            nav_p = w * gnss_p + (1.0 - w) * ind_p
            nav_v = w * gnss_v + (1.0 - w) * ind_v

            r_twin = np.concatenate([gnss_p - twin_p, gnss_v - twin_v])
            r_ind = np.concatenate([gnss_p - ind_p, gnss_v - ind_v])
            if prev_gnss_p is None:
                r_dyn = np.zeros(6)
            else:
                dtt = t - prev_gnss_t
                pred_p = prev_gnss_p + prev_gnss_v * dtt
                pred_v = prev_gnss_v
                r_dyn = np.concatenate([gnss_p - pred_p, gnss_v - pred_v])
            row = {
                "seed": seed,
                "scenario": scenario,
                "time_s": t,
                "attack_active": int(scenario in ATTACK and t >= cfg.attack_start_s),
                "twin_age_s": delay_s,
                "route_error_true_m": route_distance(p, wp),
                "route_error_gnss_m": route_distance(gnss_p, wp),
                "true_x": p[0], "true_y": p[1], "true_z": p[2],
                "gps_x": gnss_p[0], "gps_y": gnss_p[1], "gps_z": gnss_p[2],
                "ind_x": ind_p[0], "ind_y": ind_p[1], "ind_z": ind_p[2],
                "twin_x": twin_p[0], "twin_y": twin_p[1], "twin_z": twin_p[2],
            }
            for i in range(6):
                row[f"rt_{i}"] = r_twin[i]
                row[f"ri_{i}"] = r_ind[i]
                row[f"rg_{i}"] = r_dyn[i]
            rows.append(row)
            prev_gnss_p = gnss_p.copy()
            prev_gnss_v = gnss_v.copy()
            prev_gnss_t = t
        else:
            # Between GNSS samples, propagate nav estimate using latest velocity.
            nav_p = nav_p + nav_v * cfg.dt

    meta = dict(params)
    meta.update({"seed": seed, "scenario": scenario})
    return pd.DataFrame(rows), meta


def regularized_cov(X: np.ndarray) -> np.ndarray:
    C = np.cov(X, rowvar=False)
    scale = max(float(np.trace(C) / C.shape[0]), 1e-9)
    return C + np.eye(C.shape[0]) * scale * 1e-6


def mahalanobis_sq(X: np.ndarray, C_inv: np.ndarray) -> np.ndarray:
    return np.einsum("...i,ij,...j->...", X, C_inv, X)


def add_features(df: pd.DataFrame, inv_twin: np.ndarray, inv_ind: np.ndarray, inv_dyn: np.ndarray) -> pd.DataFrame:
    out = df.copy()
    rt = out[[f"rt_{i}" for i in range(6)]].to_numpy()
    ri = out[[f"ri_{i}" for i in range(6)]].to_numpy()
    rg = out[[f"rg_{i}" for i in range(6)]].to_numpy()
    out["d2_twin"] = mahalanobis_sq(rt, inv_twin)
    out["d2_ind"] = mahalanobis_sq(ri, inv_ind)
    out["d2_gpsdyn"] = mahalanobis_sq(rg, inv_dyn)
    out["log_d2_twin"] = np.log1p(out["d2_twin"])
    out["log_d2_ind"] = np.log1p(out["d2_ind"])
    out["log_d2_gpsdyn"] = np.log1p(out["d2_gpsdyn"])
    out["log_route_error_gps"] = np.log1p(out["route_error_gnss_m"])
    return out


def compact_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "seed","scenario","time_s","attack_active","twin_age_s","route_error_true_m","route_error_gnss_m",
        "split","trial_id","d2_twin","d2_ind","d2_gpsdyn","log_d2_twin","log_d2_ind","log_d2_gpsdyn",
        "log_route_error_gps"
    ]
    return df[keep].copy()

def gen_set(name: str, counts: Dict[str, int], base_seed: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    dfs = []
    metas = []
    offset = 0
    for s_idx, scenario in enumerate(SCENARIOS):
        n = counts.get(scenario, 0)
        for j in range(n):
            seed = base_seed + s_idx * 100000 + j
            df, meta = simulate_trace(seed, scenario)
            df["split"] = name
            df["trial_id"] = f"{name}_{scenario}_{j:03d}"
            dfs.append(df)
            meta["split"] = name
            meta["trial_id"] = f"{name}_{scenario}_{j:03d}"
            metas.append(meta)
            offset += 1
    return pd.concat(dfs, ignore_index=True), pd.DataFrame(metas)


def trial_alerts(df: pd.DataFrame, score_col: str, threshold: float, persistence: int, assurance: bool = False,
                 stale_cutoff: float = 0.30, high_ind_threshold: float = np.inf) -> pd.DataFrame:
    rows = []
    kernel = np.ones(persistence, dtype=int)
    for trial_id, g in df.groupby("trial_id", sort=False):
        g = g.sort_values("time_s")
        scores = g[score_col].to_numpy()
        positive = scores >= threshold
        if assurance:
            stale = g["twin_age_s"].to_numpy() > stale_cutoff
            independent_support = g["d2_ind"].to_numpy() >= high_ind_threshold
            positive = positive & (~stale | independent_support)
        alert_time = None
        if len(positive) >= persistence:
            runs = np.convolve(positive.astype(int), kernel, mode="valid")
            idxs = np.flatnonzero(runs >= persistence)
            if len(idxs):
                # convolution index is the start of the persistence window
                alert_idx = int(idxs[0] + persistence - 1)
                alert_time = float(g["time_s"].iloc[alert_idx])
        scenario = g["scenario"].iloc[0]
        attack = scenario in ATTACK
        rows.append({
            "trial_id": trial_id,
            "scenario": scenario,
            "attack_trial": int(attack),
            "alert": int(alert_time is not None),
            "alert_time_s": np.nan if alert_time is None else alert_time,
            "detection_latency_s": np.nan if (alert_time is None or not attack) else max(0.0, alert_time - CFG.attack_start_s),
        })
    return pd.DataFrame(rows)

def event_metrics(alert_df: pd.DataFrame) -> Dict[str, float]:
    y = alert_df["attack_trial"].to_numpy()
    pred = alert_df["alert"].to_numpy()
    cm = confusion_matrix(y, pred, labels=[0,1])
    tn, fp, fn, tp = cm.ravel()
    lat = alert_df.loc[(alert_df.attack_trial == 1) & (alert_df.alert == 1), "detection_latency_s"]
    return {
        "trial_precision": float(tp / (tp + fp)) if tp + fp else np.nan,
        "trial_recall": float(tp / (tp + fn)) if tp + fn else np.nan,
        "trial_f1": float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else np.nan,
        "trial_false_alarm_rate": float(fp / (fp + tn)) if fp + tn else np.nan,
        "trial_miss_rate": float(fn / (fn + tp)) if fn + tp else np.nan,
        "median_detection_latency_s": float(lat.median()) if len(lat) else np.nan,
        "p95_detection_latency_s": float(lat.quantile(0.95)) if len(lat) else np.nan,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def tune_persistence(df_val: pd.DataFrame, score_col: str, threshold: float, assurance: bool,
                     stale_cutoff: float, high_ind_threshold: float) -> Tuple[int, Dict[str, float]]:
    choices = []
    for p in range(1, 7):
        a = trial_alerts(df_val, score_col, threshold, p, assurance, stale_cutoff, high_ind_threshold)
        m = event_metrics(a)
        choices.append((p, m))
    feasible = [(p,m) for p,m in choices if m["trial_false_alarm_rate"] <= 0.05]
    if feasible:
        return max(feasible, key=lambda x: (x[1]["trial_f1"], x[1]["trial_recall"], -x[0]))
    return min(choices, key=lambda x: (x[1]["trial_false_alarm_rate"], -x[1]["trial_f1"]))


def tune_classifier(df_val: pd.DataFrame, prob_col: str, stale_cutoff: float, high_ind_threshold: float) -> Tuple[float,int,Dict[str,float]]:
    y = df_val["attack_active"].to_numpy().astype(int)
    score = df_val[prob_col].to_numpy()
    # Candidate thresholds from score quantiles; select the best sample-level F1
    # subject to <=1% false-positive rate on benign samples when possible.
    candidates = np.unique(np.quantile(score, np.linspace(0.50, 0.999, 120)))
    options = []
    for th in candidates:
        pred = score >= th
        neg = y == 0; pos = y == 1
        fpr = float(np.mean(pred[neg])) if np.any(neg) else 0.0
        tp = int(np.sum(pred & pos)); fp = int(np.sum(pred & neg)); fn = int(np.sum((~pred) & pos))
        f1 = (2*tp/(2*tp+fp+fn)) if (2*tp+fp+fn) else 0.0
        options.append((float(th), fpr, f1))
    feasible = [o for o in options if o[1] <= 0.01]
    th = max(feasible, key=lambda o:o[2])[0] if feasible else max(options, key=lambda o:o[2])[0]
    p, m = tune_persistence(df_val, prob_col, th, True, stale_cutoff, high_ind_threshold)
    return th, p, m

def sample_level_metrics(y: np.ndarray, score: np.ndarray, threshold: float) -> Dict[str, float]:
    pred = (score >= threshold).astype(int)
    out = {
        "sample_precision": precision_score(y, pred, zero_division=0),
        "sample_recall": recall_score(y, pred, zero_division=0),
        "sample_f1": f1_score(y, pred, zero_division=0),
        "sample_accuracy": accuracy_score(y, pred),
    }
    if len(np.unique(y)) == 2:
        out["roc_auc"] = roc_auc_score(y, score)
    return {k: float(v) for k,v in out.items()}


def simulate_closed_loop(seed: int, scenario: str, detector: Pipeline, prob_threshold: float, persistence: int,
                         inv_twin: np.ndarray, inv_ind: np.ndarray, inv_dyn: np.ndarray,
                         stale_cutoff: float, high_ind_threshold: float, strategy: str,
                         cfg: SimConfig = CFG) -> Dict[str, float]:
    """Closed-loop evaluation of response policies using the trained multi-source detector."""
    rng = np.random.default_rng(seed)
    params = sample_attack_parameters(scenario, rng)
    scaler_mean = detector.named_steps["scale"].mean_
    scaler_scale = detector.named_steps["scale"].scale_
    lr_coef = detector.named_steps["lr"].coef_[0]
    lr_intercept = float(detector.named_steps["lr"].intercept_[0])
    wp = np.array(cfg.waypoints, dtype=float)
    p, v = initial_state(cfg)
    ind_pos_bias = np.zeros(3)
    ind_vel_bias = np.zeros(3)
    ind_p = p.copy(); ind_v = v.copy()
    nav_p = p.copy(); nav_v = v.copy()
    twin_p = p.copy(); twin_v = v.copy()
    mission_targets = list(range(1, len(wp)))
    target_idx = 1
    current_target = wp[target_idx].copy()
    mode = "mission"
    gnss_isolated = False
    alert_time = None
    response_time = None
    route_recovery_time = None
    recovery_counter = 0
    mission_completed = False
    returned_home = False
    max_route_error = 0.0
    max_route_error_post_attack = 0.0
    path_length = 0.0
    prev_true_p = p.copy()

    gnss_p = p.copy(); gnss_v = v.copy()
    prev_gnss_p = None; prev_gnss_v = None; prev_gnss_t = None
    hist_ind_p: List[np.ndarray] = []
    hist_ind_v: List[np.ndarray] = []
    hist_cmd: List[np.ndarray] = []
    consecutive = 0

    steps = int(round(cfg.duration_s / cfg.dt)) + 1
    gnss_stride = max(1, int(round(cfg.gnss_period_s / cfg.dt)))

    for k in range(steps):
        t = k * cfg.dt
        ind_pos_bias += rng.normal(0.0, cfg.ind_pos_bias_rw_sigma, 3)
        ind_vel_bias += rng.normal(0.0, cfg.ind_vel_bias_rw_sigma, 3)
        ind_p = p + ind_pos_bias + rng.normal(0.0, cfg.ind_pos_sigma_m, 3)
        ind_v = v + ind_vel_bias + rng.normal(0.0, cfg.ind_vel_sigma_mps, 3)

        # target management
        if mode == "mission":
            if target_idx < len(wp) - 1 and np.linalg.norm(nav_p - wp[target_idx]) <= cfg.waypoint_radius_m:
                target_idx += 1
            current_target = wp[target_idx]
        elif mode == "rtb":
            # retrace preceding mission waypoints to remain near the authorized corridor
            if np.linalg.norm(nav_p - current_target) <= cfg.waypoint_radius_m:
                if target_idx > 0:
                    target_idx -= 1
                    current_target = wp[target_idx]
            if target_idx == 0 and np.linalg.norm(nav_p - wp[0]) <= cfg.completion_radius_m:
                returned_home = True

        a_cmd = controller(nav_p, nav_v, current_target, cfg)
        a_true = a_cmd + rng.normal(0.0, cfg.process_accel_sigma, 3)
        v = v + a_true * cfg.dt
        p = p + v * cfg.dt
        path_length += float(np.linalg.norm(p - prev_true_p)); prev_true_p = p.copy()

        hist_ind_p.append(ind_p.copy()); hist_ind_v.append(ind_v.copy()); hist_cmd.append(a_cmd.copy())
        delay_s = comm_delay(t, scenario, params, cfg)
        delay_steps = int(round(delay_s / cfg.dt)); idx = max(0, k - delay_steps)
        delayed_cmd = hist_cmd[idx]; delayed_ind_p = hist_ind_p[idx]; delayed_ind_v = hist_ind_v[idx]
        twin_p = twin_p + twin_v * cfg.dt + 0.5 * delayed_cmd * cfg.dt**2
        twin_v = twin_v + delayed_cmd * cfg.dt
        twin_p += cfg.twin_pos_gain * (delayed_ind_p - twin_p)
        twin_v += cfg.twin_vel_gain * (delayed_ind_v - twin_v)

        rerr = route_distance(p, wp)
        max_route_error = max(max_route_error, rerr)
        if t >= cfg.attack_start_s:
            max_route_error_post_attack = max(max_route_error_post_attack, rerr)
        if alert_time is not None and mode == "mission":
            if rerr <= cfg.recovery_route_threshold_m:
                recovery_counter += 1
                if route_recovery_time is None and recovery_counter * cfg.dt >= cfg.recovery_hold_s:
                    route_recovery_time = t - alert_time
            else:
                recovery_counter = 0

        if mode == "mission" and target_idx == len(wp)-1 and np.linalg.norm(p - wp[-1]) <= cfg.completion_radius_m:
            mission_completed = True

        if k % gnss_stride == 0:
            gnss_p, gnss_v = generate_gnss(p, v, t, scenario, params, rng, cfg)
            if gnss_isolated:
                nav_p = ind_p.copy(); nav_v = ind_v.copy()
            else:
                w = cfg.gnss_nav_weight
                nav_p = w * gnss_p + (1.0-w) * ind_p
                nav_v = w * gnss_v + (1.0-w) * ind_v

            r_twin = np.concatenate([gnss_p - twin_p, gnss_v - twin_v])
            r_ind = np.concatenate([gnss_p - ind_p, gnss_v - ind_v])
            if prev_gnss_p is None:
                r_dyn = np.zeros(6)
            else:
                dtt = t - prev_gnss_t
                r_dyn = np.concatenate([gnss_p - (prev_gnss_p + prev_gnss_v*dtt), gnss_v - prev_gnss_v])
            d2t = float(mahalanobis_sq(r_twin[None,:], inv_twin)[0])
            d2i = float(mahalanobis_sq(r_ind[None,:], inv_ind)[0])
            d2g = float(mahalanobis_sq(r_dyn[None,:], inv_dyn)[0])
            x = np.array([np.log1p(d2t), np.log1p(d2i), np.log1p(d2g), delay_s, np.log1p(route_distance(gnss_p, wp))])
            z = (x - scaler_mean) / scaler_scale
            logit = lr_intercept + float(np.dot(lr_coef, z))
            prob = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, logit))))
            positive = prob >= prob_threshold
            if positive and delay_s > stale_cutoff:
                positive = d2i >= high_ind_threshold
            consecutive = consecutive + 1 if positive else 0
            if alert_time is None and consecutive >= persistence:
                alert_time = t
                if strategy == "fixed_rtb":
                    gnss_isolated = True
                    mode = "rtb"
                    # nearest previously reached waypoint based on current mission target
                    target_idx = max(0, target_idx - 1)
                    current_target = wp[target_idx]
                    response_time = t
                elif strategy == "bounded_continue":
                    gnss_isolated = True
                    # continue mission using independent state estimate
                    mode = "mission"
                    response_time = t
                elif strategy == "detection_only":
                    response_time = np.nan
            prev_gnss_p = gnss_p.copy(); prev_gnss_v = gnss_v.copy(); prev_gnss_t = t
        else:
            nav_p = nav_p + nav_v * cfg.dt

    attack = scenario in ATTACK
    return {
        "seed": seed,
        "scenario": scenario,
        "strategy": strategy,
        "attack_trial": int(attack),
        "alert": int(alert_time is not None),
        "alert_time_s": np.nan if alert_time is None else alert_time,
        "detection_latency_s": np.nan if (alert_time is None or not attack) else alert_time - cfg.attack_start_s,
        "mission_completed": int(mission_completed),
        "returned_home": int(returned_home),
        "max_route_error_m": max_route_error,
        "max_route_error_post_attack_m": max_route_error_post_attack,
        "route_recovery_time_s": np.nan if route_recovery_time is None else route_recovery_time,
        "path_length_m": path_length,
        "boundary10_violation": int(max_route_error_post_attack > 10.0),
        "boundary20_violation": int(max_route_error_post_attack > 20.0),
        "boundary30_violation": int(max_route_error_post_attack > 30.0),
        **params,
    }


def main():
    import time
    T0=time.time(); last=T0
    def mark(msg):
        nonlocal last
        now=time.time(); print(f"[TIMING] {msg}: {now-last:.2f}s (total {now-T0:.2f}s)", flush=True); last=now
    print("Generating calibration traces...", flush=True)
    calib_nominal, meta_cal = gen_set("cov_calibration", {"nominal": 25}, 10000)
    rt = calib_nominal[[f"rt_{i}" for i in range(6)]].to_numpy()
    ri = calib_nominal[[f"ri_{i}" for i in range(6)]].to_numpy()
    rg = calib_nominal[[f"rg_{i}" for i in range(6)]].to_numpy()
    # discard first few seconds to remove initialization transients
    mask = calib_nominal["time_s"].to_numpy() >= 5.0
    C_twin = regularized_cov(rt[mask]); C_ind = regularized_cov(ri[mask]); C_dyn = regularized_cov(rg[mask])
    inv_twin = np.linalg.inv(C_twin); inv_ind = np.linalg.inv(C_ind); inv_dyn = np.linalg.inv(C_dyn)
    mark("calibration")

    print("Generating threshold, train, validation, and test datasets...", flush=True)
    import gc
    thresh_raw, meta_thresh = gen_set("threshold", {"nominal":10,"gnss_degradation":10,"comm_delay":10}, 20000)
    thresh = compact_feature_frame(add_features(thresh_raw, inv_twin, inv_ind, inv_dyn)); del thresh_raw; gc.collect()
    train_raw, meta_train = gen_set("train", {s:20 for s in SCENARIOS}, 30000)
    train = compact_feature_frame(add_features(train_raw, inv_twin, inv_ind, inv_dyn)); del train_raw; gc.collect()
    val_raw, meta_val = gen_set("validation", {s:8 for s in SCENARIOS}, 40000)
    val = compact_feature_frame(add_features(val_raw, inv_twin, inv_ind, inv_dyn)); del val_raw; gc.collect()
    test_raw, meta_test = gen_set("test", {s:20 for s in SCENARIOS}, 50000)
    test = compact_feature_frame(add_features(test_raw, inv_twin, inv_ind, inv_dyn)); del test_raw; gc.collect()
    mark("dataset generation and feature computation")

    feature_cols = ["log_d2_twin", "log_d2_ind", "log_d2_gpsdyn", "twin_age_s", "log_route_error_gps"]
    X_train = train[feature_cols].to_numpy(); y_train = train["attack_active"].to_numpy()
    X_val = val[feature_cols].to_numpy(); y_val = val["attack_active"].to_numpy()
    X_test = test[feature_cols].to_numpy(); y_test = test["attack_active"].to_numpy()

    clf = Pipeline([
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=7)),
    ])
    clf.fit(X_train, y_train)
    val["p_attack"] = clf.predict_proba(X_val)[:,1]
    test["p_attack"] = clf.predict_proba(X_test)[:,1]
    mark("model fit and probabilities")

    # Thresholds calibrated on benign threshold set.
    q_gpsdyn = float(thresh["d2_gpsdyn"].quantile(0.995))
    q_twin = float(thresh["d2_twin"].quantile(0.995))
    q_ind_high = float(thresh["d2_ind"].quantile(0.999))
    stale_cutoff = max(0.30, float(thresh.loc[thresh.scenario == "nominal", "twin_age_s"].quantile(0.999) + 0.05))

    p_gps, val_gps = tune_persistence(val, "d2_gpsdyn", q_gpsdyn, False, stale_cutoff, q_ind_high)
    p_twin, val_twin = tune_persistence(val, "d2_twin", q_twin, False, stale_cutoff, q_ind_high)
    prob_threshold, p_prop, val_prop = tune_classifier(val, "p_attack", stale_cutoff, q_ind_high)
    mark("threshold/persistence tuning")

    methods = {
        "GNSS-only temporal": ("d2_gpsdyn", q_gpsdyn, p_gps, False),
        "Twin residual": ("d2_twin", q_twin, p_twin, False),
        "Multi-source + assurance": ("p_attack", prob_threshold, p_prop, True),
    }
    summaries = []
    alert_outputs = []
    for name,(score,thr,pers,assure) in methods.items():
        a = trial_alerts(test, score, thr, pers, assure, stale_cutoff, q_ind_high)
        a["method"] = name
        alert_outputs.append(a)
        m = event_metrics(a)
        sm = sample_level_metrics(y_test, test[score].to_numpy(), thr) if score != "p_attack" else sample_level_metrics(y_test, test[score].to_numpy(), thr)
        summaries.append({"method":name,"threshold":thr,"persistence_samples":pers,**m,**sm})
    summary_df = pd.DataFrame(summaries)
    alert_df = pd.concat(alert_outputs, ignore_index=True)
    mark("held-out detection evaluation")

    # Classifier calibration diagnostics on held-out test data.
    p_test = test["p_attack"].to_numpy()
    calibration = {
        "brier_score": float(brier_score_loss(y_test, p_test)),
        "ece_10_bins": ece_score(y_test, p_test, 10),
        "roc_auc_probability": float(roc_auc_score(y_test, p_test)),
    }

    # Scenario-specific event results.
    scenario_rows = []
    for method in methods:
        aa = alert_df[alert_df.method == method]
        for scenario, g in aa.groupby("scenario"):
            attack_trial = scenario in ATTACK
            scenario_rows.append({
                "method": method,
                "scenario": scenario,
                "n_trials": len(g),
                "alert_rate": float(g.alert.mean()),
                "median_latency_s": float(g.detection_latency_s.median()) if attack_trial else np.nan,
                "p95_latency_s": float(g.detection_latency_s.quantile(0.95)) if attack_trial else np.nan,
            })
    scenario_df = pd.DataFrame(scenario_rows)

    mark("scenario summaries")

    # Persist detection-stage artifacts before the closed-loop response stage.
    summary_df.to_csv(RESULTS / "detection_method_summary.csv", index=False)
    scenario_df.to_csv(RESULTS / "detection_by_scenario.csv", index=False)
    alert_df.to_csv(RESULTS / "trial_alerts.csv", index=False)
    np.savez(RESULTS / "residual_covariances.npz", C_twin=C_twin, C_ind=C_ind, C_dyn=C_dyn)
    model_info_early = {
        "feature_columns": feature_cols,
        "standard_scaler_mean": clf.named_steps["scale"].mean_.tolist(),
        "standard_scaler_scale": clf.named_steps["scale"].scale_.tolist(),
        "logistic_coefficients_standardized": clf.named_steps["lr"].coef_[0].tolist(),
        "logistic_intercept": float(clf.named_steps["lr"].intercept_[0]),
        "probability_threshold": float(prob_threshold),
        "persistence_samples": int(p_prop),
        "stale_twin_cutoff_s": float(stale_cutoff),
        "high_independent_residual_threshold": float(q_ind_high),
        "baseline_gnssdyn_threshold": float(q_gpsdyn),
        "baseline_gnssdyn_persistence": int(p_gps),
        "baseline_twin_threshold": float(q_twin),
        "baseline_twin_persistence": int(p_twin),
        "validation_event_metrics": {"gnss_only": val_gps, "twin_residual": val_twin, "proposed": val_prop},
        "test_probability_calibration": calibration,
    }
    with open(RESULTS / "trained_detector_parameters.json", "w") as f:
        json.dump(model_info_early, f, indent=2)

    if os.environ.get("SKIP_RESPONSE", "0") == "1":
        print("\nDETECTION SUMMARY")
        print(summary_df.to_string(index=False))
        print("\nSCENARIO SUMMARY")
        print(scenario_df.to_string(index=False))
        print("\nCALIBRATION", calibration)
        return

    print("Running closed-loop response-policy evaluation...", flush=True)
    response_rows = []
    for strategy_idx, strategy in enumerate(["detection_only", "fixed_rtb", "bounded_continue"]):
        for s_idx, scenario in enumerate(SCENARIOS):
            for j in range(8):
                seed = 70000 + strategy_idx*1000000 + s_idx*10000 + j
                response_rows.append(simulate_closed_loop(seed, scenario, clf, prob_threshold, p_prop,
                                                         inv_twin, inv_ind, inv_dyn, stale_cutoff, q_ind_high,
                                                         strategy))
    response_df = pd.DataFrame(response_rows)

    response_summary_rows = []
    for strategy, g0 in response_df.groupby("strategy"):
        for subset_name, g in [("all",g0), ("attack",g0[g0.attack_trial==1]), ("benign",g0[g0.attack_trial==0])]:
            response_summary_rows.append({
                "strategy":strategy,
                "subset":subset_name,
                "n_trials":len(g),
                "alert_rate":float(g.alert.mean()),
                "mission_completion_rate":float(g.mission_completed.mean()),
                "return_home_rate":float(g.returned_home.mean()),
                "median_max_route_error_m":float(g.max_route_error_post_attack_m.median()),
                "p95_max_route_error_m":float(g.max_route_error_post_attack_m.quantile(0.95)),
                "boundary10_violation_rate":float(g.boundary10_violation.mean()),
                "boundary20_violation_rate":float(g.boundary20_violation.mean()),
                "boundary30_violation_rate":float(g.boundary30_violation.mean()),
                "median_route_recovery_time_s":float(g.route_recovery_time_s.median()) if g.route_recovery_time_s.notna().any() else np.nan,
                "median_path_length_m":float(g.path_length_m.median()),
            })
    response_summary_df = pd.DataFrame(response_summary_rows)

    # Representative traces for reproducible figures.
    reps = []
    for scenario, seed in [("nominal",90001),("gnss_degradation",90002),("comm_delay",90003),("abrupt_spoof",90004),("gradual_spoof",90005),("spoof_comm",90006)]:
        d, m = simulate_trace(seed, scenario)
        d = add_features(d, inv_twin, inv_ind, inv_dyn)
        d["p_attack"] = clf.predict_proba(d[feature_cols].to_numpy())[:,1]
        d["rep_scenario"] = scenario
        reps.append(d)
    rep_df = pd.concat(reps, ignore_index=True)

    # Save artifacts.
    summary_df.to_csv(RESULTS / "detection_method_summary.csv", index=False)
    scenario_df.to_csv(RESULTS / "detection_by_scenario.csv", index=False)
    alert_df.to_csv(RESULTS / "trial_alerts.csv", index=False)
    response_df.to_csv(RESULTS / "response_trials.csv", index=False)
    response_summary_df.to_csv(RESULTS / "response_summary.csv", index=False)
    rep_df.to_csv(RESULTS / "representative_traces.csv", index=False)
    pd.concat([meta_cal, meta_thresh, meta_train, meta_val, meta_test], ignore_index=True).to_csv(RESULTS / "scenario_parameters.csv", index=False)

    np.savez(RESULTS / "residual_covariances.npz", C_twin=C_twin, C_ind=C_ind, C_dyn=C_dyn)
    model_coef = clf.named_steps["lr"].coef_[0]
    model_intercept = clf.named_steps["lr"].intercept_[0]
    scaler_mean = clf.named_steps["scale"].mean_
    scaler_scale = clf.named_steps["scale"].scale_
    model_info = {
        "feature_columns": feature_cols,
        "standard_scaler_mean": scaler_mean.tolist(),
        "standard_scaler_scale": scaler_scale.tolist(),
        "logistic_coefficients_standardized": model_coef.tolist(),
        "logistic_intercept": float(model_intercept),
        "probability_threshold": float(prob_threshold),
        "persistence_samples": int(p_prop),
        "stale_twin_cutoff_s": float(stale_cutoff),
        "high_independent_residual_threshold": float(q_ind_high),
        "baseline_gnssdyn_threshold": float(q_gpsdyn),
        "baseline_gnssdyn_persistence": int(p_gps),
        "baseline_twin_threshold": float(q_twin),
        "baseline_twin_persistence": int(p_twin),
        "validation_event_metrics": {
            "gnss_only": val_gps,
            "twin_residual": val_twin,
            "proposed": val_prop,
        },
        "test_probability_calibration": calibration,
    }
    with open(RESULTS / "trained_detector_parameters.json", "w") as f:
        json.dump(model_info, f, indent=2)

    env = {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "simulation_config": asdict(CFG),
        "scenario_definitions": {
            "abrupt_spoof": "horizontal position step sampled 12-25 m plus 0-0.8 m/s coherent velocity bias from t=30 s",
            "gradual_spoof": "horizontal carry-off rate sampled 0.25-0.80 m/s, capped at 30 m, from t=30 s",
            "spoof_comm": "gradual spoofing plus external twin telemetry delay sampled 0.55-1.20 s during t=30-50 s",
            "gnss_degradation": "temporary 7 s increase in GNSS noise by 2.5-4.5x plus bounded transient bias surrogate",
            "comm_delay": "external twin telemetry delay sampled 0.55-1.20 s during t=30-50 s; GNSS remains benign",
        },
        "important_limitation": "Reduced-order 3D translational simulation; not PX4/Gazebo, not RF GNSS simulation, not flight validation.",
    }
    with open(RESULTS / "execution_environment.json", "w") as f:
        json.dump(env, f, indent=2)

    print("\nDETECTION SUMMARY")
    print(summary_df.to_string(index=False))
    print("\nSCENARIO SUMMARY")
    print(scenario_df.to_string(index=False))
    print("\nCALIBRATION", calibration)
    print("\nRESPONSE SUMMARY")
    print(response_summary_df.to_string(index=False))

if __name__ == "__main__":
    main()
