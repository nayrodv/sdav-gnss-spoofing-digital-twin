from pathlib import Path
import numpy as np, pandas as pd
R=Path(__file__).resolve().parent/'results'
files=[R/'response_detection_only.csv',R/'response_fixed_rtb.csv',R/'response_bounded_continue.csv']
df=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
df.to_csv(R/'response_trials.csv',index=False)
rows=[]
for strategy,g0 in df.groupby('strategy'):
    for subset_name,g in [('all',g0),('attack',g0[g0.attack_trial==1]),('benign',g0[g0.attack_trial==0])]:
        rows.append({
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
s=pd.DataFrame(rows); s.to_csv(R/'response_summary.csv',index=False); print(s.to_string(index=False))
