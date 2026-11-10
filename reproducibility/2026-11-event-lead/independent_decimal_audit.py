#!/usr/bin/env python3
"""Independent decimal replay of DGIG event-lead witnesses from Weber original CSV.

No dependency on lead_certificate.py; parses original source decimal strings and
checks every exported certificate status/earliest separator with Decimal algebra.
"""
import argparse, bisect, csv, hashlib, io, json, zipfile
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path
getcontext().prec=38
D=Decimal
HASHES={
4:(14766,'985f4452c04e495c6f07227d3ce238975d596caa5a9ea04f8e52fb08645e1d68'),
5:(16243,'3318140e2de217cce5c407f862b238385f5872e46a11710ef8fed260cce22425'),
6:(11069,'cbbf5b9846c2bd0945cebf6517f8a9b003f7d4b5aaf54c1de6bc8dc8de1a629b'),
7:(15935,'19b88ec506a3e2407ca4bb40adeb8247d2467f4913b0a62de39afede45254a6b'),
8:(9076,'1cbfdd865524224959a0d28836528c79dc7228e37e725e9e4be7b32f4ea799ef'),
9:(14058,'050bd98e110121a9063e7c361f8a7cbbedad55fea6eed42c05e2e69a22ccbe2e')}
SENSOR_NAMES=['TR404-108e','TR404-333a','TR404-018b','TR404-063c','TR404-085d']


def load(zips):
 out={}
 for fp in zips:
  with zipfile.ZipFile(fp) as z:
   assert z.testzip() is None
   for fn in z.namelist():
    if not fn.endswith('/MeasurementData.CSV'):continue
    run=int(fn.split('/')[-2].split('_')[0]);raw=z.read(fn)
    lines=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';')
    data={s:[] for s in ['Time since Start [min]','Heater_AO']+SENSOR_NAMES};num=0
    for row in lines:
     num+=1
     for c in data:data[c].append(D(row[c].replace(',','.')))
    assert (num,hashlib.sha256(raw).hexdigest())==HASHES[run]
    h=data['Heater_AO']; spans=[];i=0
    while i<len(h):
     if h[i]<=D('4.5'):i+=1;continue
     st=i
     while i<len(h) and h[i]>D('4.5'):i+=1
     spans.append((st,i))
    a,b=max(spans,key=lambda x:x[1]-x[0]); assert b<len(h)
    td=data['Time since Start [min]'][a:b+1]
    assert all(td[i]<td[i+1] for i in range(len(td)-1))
    out[run]={'t':td,'command':td[-1],'channels':{k:v[a:b+1] for k,v in data.items() if k in SENSOR_NAMES}}
 return out


def grad(t,y):
 times,values=[],[]
 for i,tt in enumerate(t):
  target=tt-D(15)
  if target<t[0]:continue
  j=min(bisect.bisect_right(t,target)-1,len(t)-2)
  q=(target-t[j])/(t[j+1]-t[j]);lag=(D(1)-q)*y[j]+q*y[j+1]
  times.append(tt);values.append((y[i]-lag)/D(15))
 return times,values


def rows_csv(p):
 with open(p,newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def verify(zips,folder):
 data=load(zips)
 records=rows_csv(folder/'joint_lead_grid_24.csv')
 grouped=defaultdict(list)
 for r in records:grouped[(int(r['run']),r['sensor'])].append(r)
 checks=0; status_matches=0;lead_checks=0;radius_checks=0
 examples={}
 for run,rr in sorted(data.items()):
  tt,gs=grad(rr['t'],rr['channels']['TR404-108e'])
  pref=[];mn=D('Infinity')
  for g in gs:mn=min(mn,g);pref.append(mn)
  for sensor in SENSOR_NAMES[1:]:
   tc,gc=grad(rr['t'],rr['channels'][sensor]);assert tc==tt
   for case in grouped[(run,sensor)]:
    h=D(case['halfwidth_K_min']);delta=D(case['delta_raw_K'])
    hi=D(1)+h+delta*D(2)/D(15)
    lo=D(1)-h-delta*D(2)/D(15)
    # Independent exhaustive separator search in exact source-decimal arithmetic.
    eligible=[]
    if gc[0]>hi:
     eligible=[i for i,(tm,src,cand) in enumerate(zip(tt,pref,gc))
               if tm<rr['command'] and src>hi and cand<lo]
    first=eligible[0] if eligible else None
    claimed=case['certified']=='PASS'
    assert claimed==(first is not None),(run,sensor,h,delta,'status')
    status_matches+=1
    if first is not None:
     assert int(case['sep_eligible_index'])==first,(run,sensor,h,delta,'first separator')
     assert tt[first] < rr['command'], (run,sensor,h,delta,'must precede command')
     assert abs(D(case['lead_lower_bound_min'])-(rr['command']-tt[first]))<D('1e-7')
     # Full strict sign check from original raw source decimal values.
     assert gc[0]>hi and min(gs[:first+1])>hi and gc[first]<lo
     lead_checks+=1
    # Verify exported maximum nominal radius by scanning same native grid.
    vals=[min(gc[0]-D(1)-h,p-D(1)-h,D(1)-h-g)
          for tm,p,g in zip(tt,pref,gc) if tm < rr['command']]
    rad=max(max(vals)*D(15)/D(2),D(0))
    assert abs(rad-D(case['certificate_radius_K']))<D('1e-8'),(run,sensor,h,delta,'radius')
    radius_checks+=1
    checks+=1
   if sensor=='TR404-085d':
    examples[str(run)]={"source_eligible_n":len(tt),"initial_gradient_source":str(gs[0]),
                        "initial_gradient_candidate":str(gc[0])}
 assert checks==1200 and status_matches==1200 and radius_checks==1200
 out={'result':'PASS','source_decimal_validation':True,'input_sha256_admission':'6/6 PASS',
      'all_conditional_statuses_earliest_separators':'1200/1200 PASS',
      'all_certificate_radii_decimal':'1200/1200 PASS',
      'observed_lead_decimals_checked':lead_checks,
      'source_eligible_gradients':examples,
      'claim_boundary':'conditional on fixed recorded grid, rule, threshold band and raw-sample box; neither uncertainty coverage nor prospective action'}
 (folder/'QA_independent_decimal.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-zips',nargs=2,type=Path,required=True);p.add_argument('--result-dir',type=Path,required=True)
 x=p.parse_args();verify(x.source_zips,x.result_dir)
