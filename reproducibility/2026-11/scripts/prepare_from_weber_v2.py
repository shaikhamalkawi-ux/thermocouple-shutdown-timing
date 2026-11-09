#!/usr/bin/env python3
"""Build a fresh local DGIG primary + D50 worktree from independently obtained Weber V2 files.
This utility does not download or distribute Weber's measurements. It verifies every
source CSV by SHA-256 BEFORE creating derived compact source ZIPs; never overwrites.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,zipfile,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
GROUPS={
 'DGIG_WEBER_CORE_ANCILLARY_tests1_3.zip':[1,2,3],
 'DGIG_WEBER_CORE_PRIMARY_A_tests4_6.zip':[4,5,6],
 'DGIG_WEBER_CORE_PRIMARY_B_tests7_9.zip':[7,8,9],
}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--upstream',required=True,type=Path,help='Extracted UNMODIFIED Weber V2 Mendeley Data directory')
 a.add_argument('--output',required=True,type=Path,help='NEW directory, cannot exist')
 args=a.parse_args();src=args.upstream.resolve();out=args.output.resolve()
 if not src.is_dir():raise SystemExit('ERROR: source directory absent')
 if out.exists():raise SystemExit('ERROR: output exists: '+str(out))
 manifest=json.loads((HERE/'EXPECTED_UPSTREAM_SOURCE_FILES.json').read_text())['members']
 located={}
 for x in manifest:
  rel=Path(x['relative_source_path'])
  found=[p for p in src.rglob(rel.name) if p.parent.name==rel.parent.name and p.is_file()]
  if len(found)!=1:raise SystemExit(f'ERROR: run {x["run"]} expected one {rel.parent.name}/{rel.name}; found {len(found)}')
  p=found[0]
  if p.stat().st_size!=x['bytes'] or digest(p)!=x['sha256']:
   raise SystemExit(f'ERROR: Weber V2 source bytes do not match frozen manifest, run {x["run"]}')
  located[x['run']]=(p,str(rel))
 if len(located)!=9:raise SystemExit('ERROR: expected exactly 9 source runs')
 # Source validation is completed before any output directory is created.
 out.mkdir(parents=True)
 try:
  primary=out/'primary'; shutil.copytree(HERE/'primary',primary)
  zippedir=primary/'source_zips';zippedir.mkdir()
  for name, runs in GROUPS.items():
   with zipfile.ZipFile(zippedir/name,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for run in runs:
     p,rel=located[run];z.write(p,arcname=rel)
  work=out/'d50';shutil.copytree(HERE/'d50',work)
  d50src=work/'DGIG_OVERNIGHT_AUTONOMOUS_BUILD_WORK/R2E_REPRO_CLEAN_20260920/source_zips'
  d50src.mkdir()
  for name in GROUPS:
   if 'ANCILLARY' not in name:shutil.copy2(zippedir/name,d50src/name)
  (out/'expected').mkdir();
  for f in (HERE/'expected').iterdir():shutil.copy2(f,out/'expected'/f.name)
  (out/'SOURCE_ADMISSION_RECEIPT.json').write_text(json.dumps({
     'dataset_doi':manifest[0]['relative_source_path'] and '10.17632/3pp86gdvh4.2',
     'verified_files':9,'verified_sha256':True,
     'actual_source_files':[{'run':r,'sha256':digest(located[r][0])} for r in sorted(located)],
     'note':'These are published third-party measurements, not newly generated experimental data.'
  },indent=2)+'\n')
 except BaseException:
  shutil.rmtree(out,ignore_errors=True)
  raise
 print('PASS: 9/9 Weber Version-2 source SHA-256 checks; populated local primary and D50 worktrees:',out)
if __name__=='__main__':main()
