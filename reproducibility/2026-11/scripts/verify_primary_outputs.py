#!/usr/bin/env python3
"""Compare fresh primary replay outputs with immutable expected research-derived tables."""
import argparse,hashlib,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--results',required=True,type=Path);a=p.parse_args()
files=('primary_same_level_results.csv','source_rule_reconstruction.csv','r2e_scientific_summary.json')
for name in files:
 expected=HERE/'expected'/name;actual=a.results/name
 if not actual.exists() or expected.read_bytes()!=actual.read_bytes():
  raise SystemExit('FAIL: missing/different '+name)
 print('PASS:',name,'byte-identical; SHA256:',hashlib.sha256(actual.read_bytes()).hexdigest())
print('PASS 3/3 result-table byte identities')
