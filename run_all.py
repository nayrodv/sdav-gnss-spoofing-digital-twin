#!/usr/bin/env python3
"""Run the complete reduced-order proof-of-concept pipeline."""
from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parent

def run(args, env=None):
    print('>', ' '.join(map(str,args)), flush=True)
    subprocess.run(args, cwd=ROOT, env=env, check=True)

base_env=os.environ.copy(); base_env['SKIP_RESPONSE']='1'
run([sys.executable, ROOT/'poc_experiment.py'], env=base_env)
for strategy in ['detection_only','fixed_rtb','bounded_continue']:
    run([sys.executable, ROOT/'run_one_response_strategy.py', strategy, '--n', '20'])
run([sys.executable, ROOT/'aggregate_response.py'])
run([sys.executable, ROOT/'run_stress_test.py'])
run([sys.executable, ROOT/'statistical_analysis.py'])
run([sys.executable, ROOT/'make_figures.py'])
print('Complete. Results are in', ROOT/'results')
