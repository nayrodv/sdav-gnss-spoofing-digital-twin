#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results'
spec=importlib.util.spec_from_file_location('poc',ROOT/'poc_experiment.py')
poc=importlib.util.module_from_spec(spec); sys.modules['poc']=poc; spec.loader.exec_module(poc)

with open(RESULTS/'trained_detector_parameters.json') as f: info=json.load(f)
npz=np.load(RESULTS/'residual_covariances.npz')
inv_twin=np.linalg.inv(npz['C_twin']); inv_ind=np.linalg.inv(npz['C_ind']); inv_dyn=np.linalg.inv(npz['C_dyn'])

scale=SimpleNamespace(mean_=np.array(info['standard_scaler_mean']), scale_=np.array(info['standard_scaler_scale']))
lr=SimpleNamespace(coef_=np.array([info['logistic_coefficients_standardized']]), intercept_=np.array([info['logistic_intercept']]))
detector=SimpleNamespace(named_steps={'scale':scale,'lr':lr})

rows=[]
t0=time.time()
N_PER_SCENARIO=20
for strategy_idx,strategy in enumerate(['detection_only','fixed_rtb','bounded_continue']):
    for s_idx,scenario in enumerate(poc.SCENARIOS):
        for j in range(N_PER_SCENARIO):
            seed=70000+s_idx*10000+j
            rows.append(poc.simulate_closed_loop(seed,scenario,detector,
                float(info['probability_threshold']),int(info['persistence_samples']),
                inv_twin,inv_ind,inv_dyn,float(info['stale_twin_cutoff_s']),
                float(info['high_independent_residual_threshold']),strategy))
    print(strategy,'complete',f'{time.time()-t0:.1f}s',flush=True)

df=pd.DataFrame(rows)
df.to_csv(RESULTS/'response_trials.csv',index=False)
summary=[]
for strategy,g0 in df.groupby('strategy'):
    for subset_name,g in [('all',g0),('attack',g0[g0.attack_trial==1]),('benign',g0[g0.attack_trial==0])]:
        summary.append({
            'strategy':strategy,'subset':subset_name,'n_trials':len(g),
            'alert_rate':float(g.alert.mean()),
            'mission_completion_rate':float(g.mission_completed.mean()),
            'return_home_rate':float(g.returned_home.mean()),
            'median_max_route_error_m':float(g.max_route_error_post_attack_m.median()),
            'p95_max_route_error_m':float(g.max_route_error_post_attack_m.quantile(0.95)),
            'boundary10_violation_rate':float(g.boundary10_violation.mean()),
            'boundary20_violation_rate':float(g.boundary20_violation.mean()),
            'boundary30_violation_rate':float(g.boundary30_violation.mean()),
            'median_route_recovery_time_s':float(g.route_recovery_time_s.median()) if g.route_recovery_time_s.notna().any() else np.nan,
            'median_path_length_m':float(g.path_length_m.median()),
        })
sumdf=pd.DataFrame(summary)
sumdf.to_csv(RESULTS/'response_summary.csv',index=False)
print(sumdf.to_string(index=False))
print('elapsed',time.time()-t0)
