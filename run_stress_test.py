#!/usr/bin/env python3
import json,sys,importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent; R=ROOT/'results'
spec=importlib.util.spec_from_file_location('poc',ROOT/'poc_experiment.py'); poc=importlib.util.module_from_spec(spec);sys.modules['poc']=poc;spec.loader.exec_module(poc)
info=json.load(open(R/'trained_detector_parameters.json')); npz=np.load(R/'residual_covariances.npz')
inv_t=np.linalg.inv(npz['C_twin']);inv_i=np.linalg.inv(npz['C_ind']);inv_g=np.linalg.inv(npz['C_dyn'])
# override attack parameter sampler for attacks weaker than the training range
orig=poc.sample_attack_parameters
def stress_sampler(scenario,rng):
    p=orig(scenario,rng)
    if scenario=='abrupt_spoof':
        p['abrupt_pos_bias_m']=float(rng.uniform(6.0,12.0)); p['abrupt_vel_bias_mps']=float(rng.uniform(0.0,0.30))
    elif scenario in {'gradual_spoof','spoof_comm'}:
        p['gradual_rate_mps']=float(rng.uniform(0.10,0.25))
        if scenario=='spoof_comm': p['comm_delay_s']=float(rng.uniform(0.8,1.5))
    return p
poc.sample_attack_parameters=stress_sampler
feature_cols=info['feature_columns']
mean=np.array(info['standard_scaler_mean']);scale=np.array(info['standard_scaler_scale']);coef=np.array(info['logistic_coefficients_standardized']);inter=float(info['logistic_intercept'])
def prob(X):
    z=(X-mean)/scale; l=inter+z@coef; l=np.clip(l,-60,60); return 1/(1+np.exp(-l))
frames=[]
for si,sc in enumerate(['abrupt_spoof','gradual_spoof','spoof_comm']):
    for j in range(30):
        d,m=poc.simulate_trace(88000+si*10000+j,sc)
        d=poc.add_features(d,inv_t,inv_i,inv_g)
        d['p_attack']=prob(d[feature_cols].to_numpy()); d['split']='stress'; d['trial_id']=f'stress_{sc}_{j:03d}'
        frames.append(poc.compact_feature_frame(d.assign(p_attack=d['p_attack'])) if False else d)
df=pd.concat(frames,ignore_index=True)
# Keep only needed cols for artifact size
keep=['seed','scenario','time_s','attack_active','twin_age_s','d2_twin','d2_ind','d2_gpsdyn','p_attack','trial_id']
df[keep].to_csv(R/'stress_test_samples.csv',index=False)
methods={
 'GNSS-only temporal':('d2_gpsdyn',float(info['baseline_gnssdyn_threshold']),int(info['baseline_gnssdyn_persistence']),False),
 'Twin residual':('d2_twin',float(info['baseline_twin_threshold']),int(info['baseline_twin_persistence']),False),
 'Multi-source + assurance':('p_attack',float(info['probability_threshold']),int(info['persistence_samples']),True),
}
rows=[]
for name,(score,thr,pers,assure) in methods.items():
    a=poc.trial_alerts(df,score,thr,pers,assure,float(info['stale_twin_cutoff_s']),float(info['high_independent_residual_threshold']))
    for sc,g in a.groupby('scenario'):
        rows.append({'method':name,'scenario':sc,'n_trials':len(g),'detection_rate':float(g.alert.mean()),'median_latency_s':float(g.detection_latency_s.median()),'p95_latency_s':float(g.detection_latency_s.quantile(.95))})
out=pd.DataFrame(rows); out.to_csv(R/'stress_test_summary.csv',index=False); print(out.to_string(index=False))
