#!/usr/bin/env python3
"""Illustrative architecture-level Monte Carlo timing model.

This is not empirical flight validation. Replace distributions with measured
PX4/Gazebo or flight-test data before making performance claims.
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
N = 100_000
tri = lambda a,m,b: rng.triangular(a,m,b,N)
d_margin = tri(25.0,45.0,80.0)
v_drift = tri(2.0,5.0,10.0)
t_unsafe = d_margin / v_drift
margin = 1.0

t_base = tri(4.0,8.0,16.0) + tri(0.1,0.3,0.8) + tri(2.0,4.0,7.0)
t_auto = (tri(0.01,0.05,0.15) + tri(0.01,0.03,0.08) + tri(0.8,1.8,4.0)
          + tri(0.05,0.18,0.5) + tri(0.02,0.08,0.2) + tri(0.5,1.3,3.0))
t_network = np.where(rng.random(N)<0.20, tri(0.2,0.8,2.0), tri(0.02,0.08,0.25))
t_operator = np.minimum(rng.lognormal(np.log(3.0),0.5,N),5.0)
t_operator = np.where(rng.random(N)<0.10,5.0,t_operator)
t_rework = np.where(rng.random(N)<0.03,tri(0.5,1.5,3.0),0.0)
t_rework += np.where(rng.random(N)<0.05,tri(1.0,3.0,6.0),0.0)
t_human = t_auto+t_network+t_operator+t_rework

rows=[]
for name,t in {'Fixed RTL baseline':t_base,'Proposed automated response':t_auto,
               'Proposed human-gated response':t_human}.items():
    safe=(t+margin)<t_unsafe
    deviation=np.minimum(v_drift*t,d_margin)
    rows.append([name,t.mean(),np.median(t),np.quantile(t,.95),safe.mean(),deviation.mean(),np.quantile(deviation,.95)])
print(pd.DataFrame(rows,columns=['architecture','mean_s','median_s','p95_s','safe_probability','mean_deviation_m','p95_deviation_m']).to_string(index=False))
