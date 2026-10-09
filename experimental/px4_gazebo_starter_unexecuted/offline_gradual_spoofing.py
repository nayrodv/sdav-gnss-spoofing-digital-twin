#!/usr/bin/env python3
"""Inject a gradual position bias into a CSV telemetry trace for offline testing.

Expected columns: time_s, gps_n_m, gps_e_m, pred_n_m, pred_e_m.
The script adds a linear carry-off bias after attack_start_s and writes a new CSV.
"""
import argparse
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('input_csv')
p.add_argument('output_csv')
p.add_argument('--attack-start-s',type=float,default=30.0)
p.add_argument('--north-rate-mps',type=float,default=1.5)
p.add_argument('--east-rate-mps',type=float,default=0.5)
a=p.parse_args()
df=pd.read_csv(a.input_csv)
dt=(df['time_s']-a.attack_start_s).clip(lower=0)
df['gps_n_m']=df['gps_n_m']+dt*a.north_rate_mps
df['gps_e_m']=df['gps_e_m']+dt*a.east_rate_mps
df.to_csv(a.output_csv,index=False)
