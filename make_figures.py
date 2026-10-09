#!/usr/bin/env python3
import json, sys, importlib.util
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent; R=ROOT/'results'; F=ROOT/'figures'; F.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('poc',ROOT/'poc_experiment.py'); poc=importlib.util.module_from_spec(spec);sys.modules['poc']=poc;spec.loader.exec_module(poc)
info=json.load(open(R/'trained_detector_parameters.json')); npz=np.load(R/'residual_covariances.npz')
inv_t=np.linalg.inv(npz['C_twin']);inv_i=np.linalg.inv(npz['C_ind']);inv_g=np.linalg.inv(npz['C_dyn'])
mean=np.array(info['standard_scaler_mean']);scale=np.array(info['standard_scaler_scale']);coef=np.array(info['logistic_coefficients_standardized']);inter=float(info['logistic_intercept']); features=info['feature_columns']
def probs(X):
 z=(X-mean)/scale; l=np.clip(inter+z@coef,-60,60); return 1/(1+np.exp(-l))
frames=[]
seeds={'nominal':91001,'gnss_degradation':91002,'comm_delay':91003,'abrupt_spoof':91004,'gradual_spoof':91005,'spoof_comm':91006}
for sc,seed in seeds.items():
 d,m=poc.simulate_trace(seed,sc); d=poc.add_features(d,inv_t,inv_i,inv_g); d['p_attack']=probs(d[features].to_numpy()); d['rep_scenario']=sc; frames.append(d)
rep=pd.concat(frames,ignore_index=True); rep.to_csv(R/'representative_traces.csv',index=False)
way=np.array(poc.CFG.waypoints)

def traj(sc,name):
 d=rep[rep.rep_scenario==sc]
 plt.figure(figsize=(7,6))
 plt.plot(way[:,0],way[:,1],linestyle='--',label='Authorized route')
 plt.plot(d.true_x,d.true_y,label='True vehicle')
 plt.plot(d.gps_x,d.gps_y,label='GNSS observation',alpha=.75)
 plt.plot(d.ind_x,d.ind_y,label='Independent odometry',alpha=.75)
 plt.plot(d.twin_x,d.twin_y,label='Digital twin',alpha=.75)
 plt.xlabel('East position (m)'); plt.ylabel('North position (m)'); plt.title(name); plt.legend(); plt.axis('equal'); plt.tight_layout(); plt.savefig(F/f'{sc}_trajectory.png',dpi=220); plt.close()
traj('abrupt_spoof','Representative abrupt-spoofing trajectory')
traj('gradual_spoof','Representative gradual carry-off trajectory')
traj('spoof_comm','Representative spoofing with communication delay')

for sc,title in [('gradual_spoof','Detection probability during gradual carry-off'),('spoof_comm','Detection probability during spoofing with communication delay')]:
 d=rep[rep.rep_scenario==sc]
 plt.figure(figsize=(8,4.8)); plt.plot(d.time_s,d.p_attack,label='Estimated attack probability'); plt.axhline(info['probability_threshold'],linestyle='--',label='Decision threshold'); plt.axvline(poc.CFG.attack_start_s,linestyle=':',label='Attack onset'); plt.xlabel('Time (s)'); plt.ylabel('Attack probability'); plt.ylim(-.02,1.02); plt.title(title); plt.legend(); plt.tight_layout(); plt.savefig(F/f'{sc}_probability.png',dpi=220); plt.close()

d=rep[rep.rep_scenario=='spoof_comm']
plt.figure(figsize=(8,4.8)); plt.plot(d.time_s,d.d2_twin,label='Twin residual statistic'); plt.plot(d.time_s,d.d2_ind,label='Independent-navigation residual statistic'); plt.axvline(poc.CFG.attack_start_s,linestyle=':',label='Attack onset'); plt.xlabel('Time (s)'); plt.ylabel('Dimensionless squared residual'); plt.title('Multi-source residual evidence under spoofing and communication delay'); plt.legend(); plt.tight_layout(); plt.savefig(F/'spoof_comm_residuals.png',dpi=220); plt.close()

summ=pd.read_csv(R/'detection_method_summary.csv')
x=np.arange(len(summ)); width=.36
plt.figure(figsize=(8,5)); plt.bar(x-width/2,summ.trial_recall,width,label='Trial recall'); plt.bar(x+width/2,summ.trial_false_alarm_rate,width,label='Trial false-alarm rate'); plt.xticks(x,summ.method,rotation=15,ha='right'); plt.ylabel('Proportion'); plt.ylim(0,1.05); plt.title('Held-out trial-level detection performance'); plt.legend(); plt.tight_layout(); plt.savefig(F/'detection_performance.png',dpi=220); plt.close()

alerts=pd.read_csv(R/'trial_alerts.csv')
lat=[]; labs=[]
for m in ['Twin residual','Multi-source + assurance']:
 vals=alerts[(alerts.method==m)&(alerts.attack_trial==1)&(alerts.alert==1)].detection_latency_s.dropna().to_numpy(); lat.append(vals); labs.append(m)
plt.figure(figsize=(7,5)); plt.boxplot(lat,tick_labels=labs,showfliers=False); plt.ylabel('Detection latency (s)'); plt.title('Detection latency on held-out attack trials'); plt.xticks(rotation=10,ha='right'); plt.tight_layout(); plt.savefig(F/'detection_latency.png',dpi=220); plt.close()

resp=pd.read_csv(R/'response_trials.csv'); attack=resp[resp.attack_trial==1]
data=[]; labs=[]
for strategy in ['detection_only','fixed_rtb','bounded_continue']:
 data.append(attack[attack.strategy==strategy].max_route_error_post_attack_m.to_numpy()); labs.append(strategy.replace('_',' '))
plt.figure(figsize=(7,5)); plt.boxplot(data,tick_labels=labs,showfliers=False); plt.ylabel('Maximum true route deviation (m)'); plt.title('Response-policy comparison on attack trials'); plt.xticks(rotation=10,ha='right'); plt.tight_layout(); plt.savefig(F/'response_route_deviation.png',dpi=220); plt.close()

stress=pd.read_csv(R/'stress_test_summary.csv'); prop=stress[stress.method=='Multi-source + assurance']
plt.figure(figsize=(7,5)); x=np.arange(len(prop)); plt.bar(x,prop.detection_rate); plt.xticks(x,prop.scenario,rotation=10,ha='right'); plt.ylabel('Detection rate'); plt.ylim(0,1.05); plt.title('Weak-attack stress-test detection rate'); plt.tight_layout(); plt.savefig(F/'stress_detection_rate.png',dpi=220); plt.close()

print('figures:',*[p.name for p in sorted(F.glob('*.png'))],sep='\n')
