#!/usr/bin/env python3
from pathlib import Path
import json
import numpy as np,pandas as pd
from scipy.stats import wilcoxon
from statsmodels.stats.proportion import proportion_confint
R=Path(__file__).resolve().parent/'results'

def wilson(k,n):
    lo,hi=proportion_confint(k,n,alpha=.05,method='wilson'); return float(lo),float(hi)

det=pd.read_csv(R/'trial_alerts.csv')
rows=[]
for method,g in det.groupby('method'):
    atk=g[g.attack_trial==1]; ben=g[g.attack_trial==0]
    k=int(atk.alert.sum()); n=len(atk); lo,hi=wilson(k,n)
    f=int(ben.alert.sum()); nb=len(ben); flo,fhi=wilson(f,nb)
    lat=atk.loc[atk.alert==1,'detection_latency_s'].dropna()
    rows.append({'method':method,'attack_detected':k,'attack_trials':n,'recall':k/n,'recall_ci95_low':lo,'recall_ci95_high':hi,'benign_false_alerts':f,'benign_trials':nb,'false_alarm_rate':f/nb,'far_ci95_low':flo,'far_ci95_high':fhi,'median_latency_s':lat.median() if len(lat) else np.nan,'iqr_latency_s':(lat.quantile(.75)-lat.quantile(.25)) if len(lat) else np.nan})
out=pd.DataFrame(rows);out.to_csv(R/'detection_confidence_intervals.csv',index=False)

resp=pd.read_csv(R/'response_trials.csv')
atk=resp[resp.attack_trial==1].copy()
# Pair by scenario+seed
pivot=atk.pivot_table(index=['scenario','seed'],columns='strategy',values='max_route_error_post_attack_m',aggfunc='first').dropna()
comparisons=[]
for a,b in [('detection_only','bounded_continue'),('fixed_rtb','bounded_continue'),('detection_only','fixed_rtb')]:
    stat,p=wilcoxon(pivot[a],pivot[b],alternative='two-sided',zero_method='wilcox')
    diff=pivot[a]-pivot[b]
    comparisons.append({'metric':'max_route_error_post_attack_m','strategy_a':a,'strategy_b':b,'n_pairs':len(diff),'median_a':float(pivot[a].median()),'median_b':float(pivot[b].median()),'median_paired_difference_a_minus_b':float(diff.median()),'wilcoxon_statistic':float(stat),'p_value':float(p)})
pd.DataFrame(comparisons).to_csv(R/'response_paired_tests.csv',index=False)

# response outcome confidence intervals
orows=[]
for strategy,g in atk.groupby('strategy'):
    for col in ['mission_completed','returned_home','boundary10_violation','boundary20_violation']:
        k=int(g[col].sum()); n=len(g);lo,hi=wilson(k,n)
        orows.append({'strategy':strategy,'outcome':col,'count':k,'n':n,'rate':k/n,'ci95_low':lo,'ci95_high':hi})
pd.DataFrame(orows).to_csv(R/'response_outcome_confidence_intervals.csv',index=False)
print(out.to_string(index=False))
print('\nPaired response tests')
print(pd.DataFrame(comparisons).to_string(index=False))
print('\nOutcome CIs')
print(pd.DataFrame(orows).to_string(index=False))
