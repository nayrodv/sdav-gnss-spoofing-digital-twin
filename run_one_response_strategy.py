#!/usr/bin/env python3
import argparse, json, sys, importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np, pandas as pd
p=argparse.ArgumentParser(); p.add_argument('strategy',choices=['detection_only','fixed_rtb','bounded_continue']); p.add_argument('--n',type=int,default=20); a=p.parse_args()
ROOT=Path(__file__).resolve().parent; R=ROOT/'results'
spec=importlib.util.spec_from_file_location('poc',ROOT/'poc_experiment.py'); poc=importlib.util.module_from_spec(spec);sys.modules['poc']=poc;spec.loader.exec_module(poc)
info=json.load(open(R/'trained_detector_parameters.json')); npz=np.load(R/'residual_covariances.npz')
scale=SimpleNamespace(mean_=np.array(info['standard_scaler_mean']),scale_=np.array(info['standard_scaler_scale'])); lr=SimpleNamespace(coef_=np.array([info['logistic_coefficients_standardized']]),intercept_=np.array([info['logistic_intercept']])); det=SimpleNamespace(named_steps={'scale':scale,'lr':lr})
inv_t=np.linalg.inv(npz['C_twin']); inv_i=np.linalg.inv(npz['C_ind']); inv_g=np.linalg.inv(npz['C_dyn'])
rows=[]
for si,sc in enumerate(poc.SCENARIOS):
 for j in range(a.n):
  seed=70000+si*10000+j
  rows.append(poc.simulate_closed_loop(seed,sc,det,float(info['probability_threshold']),int(info['persistence_samples']),inv_t,inv_i,inv_g,float(info['stale_twin_cutoff_s']),float(info['high_independent_residual_threshold']),a.strategy))
out=pd.DataFrame(rows); path=R/f'response_{a.strategy}.csv'; out.to_csv(path,index=False); print(path); print(out.groupby('scenario')[['alert','mission_completed','returned_home','max_route_error_post_attack_m']].mean().to_string())
