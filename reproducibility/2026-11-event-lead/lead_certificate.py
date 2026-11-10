#!/usr/bin/env python3
"""DGIG conditional early-event lead certificate, source-only implementation.

Inputs: two original unchanged Weber V2 source ZIPs (Tests 4--9); neither input
nor source readings are copied into the output package. Python 3.11+, stdlib only.

The observed 15-minute finite difference and subsequent piecewise-linear
native-gradient replay are SOURCE-COMPATIBLE reconstructions, not historical
PLC semantics. Error box/threshold bands are illustrative, not calibrated.
"""
from __future__ import annotations
import argparse, bisect, csv, hashlib, io, json, math, zipfile
from pathlib import Path

SOURCE = "TR404-108e"
SENSORS = {"TR404-333a": 0, "TR404-018b": 30,
           "TR404-063c": 60, "TR404-085d": 80}
EXPECTED = {
    4:(14766,"985f4452c04e495c6f07227d3ce238975d596caa5a9ea04f8e52fb08645e1d68"),
    5:(16243,"3318140e2de217cce5c407f862b238385f5872e46a11710ef8fed260cce22425"),
    6:(11069,"cbbf5b9846c2bd0945cebf6517f8a9b003f7d4b5aaf54c1de6bc8dc8de1a629b"),
    7:(15935,"19b88ec506a3e2407ca4bb40adeb8247d2467f4913b0a62de39afede45254a6b"),
    8:(9076, "1cbfdd865524224959a0d28836528c79dc7228e37e725e9e4be7b32f4ea799ef"),
    9:(14058,"050bd98e110121a9063e7c361f8a7cbbedad55fea6eed42c05e2e69a22ccbe2e"),
}
W = 15.0  # minutes
TH = 1.0 # K/min
# Parameter settings describe diagnostic error bounds and rule variation;
# they are deliberately not physical probability or calibrated uncertainty.
HALFWIDTHS = (0.0, 0.001, 0.010, 0.020, 0.050)
ERROR_BOUNDS = (0.0, 0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.60, 2.28, 4.57)


def read_inputs(zips: list[Path]):
    result = {}
    for archive in zips:
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None, f"Broken ZIP: {archive}"
            for name in z.namelist():
                if not name.endswith('/MeasurementData.CSV'):
                    continue
                run = int(name.split('/')[-2].split('_')[0])
                if run not in EXPECTED or run in result:
                    raise ValueError(f'Unexpected/duplicate run: {run}')
                raw = z.read(name)
                digest = hashlib.sha256(raw).hexdigest()
                reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),
                                        delimiter=';')
                values = {key: [] for key in
                         ('Time since Start [min]', 'Heater_AO', SOURCE, *SENSORS)}
                nrows = 0
                for row in reader:
                    nrows += 1
                    for key in values:
                        v = float(row[key].replace(',', '.'))
                        if not math.isfinite(v):
                            raise ValueError(f'Nonfinite: run {run}, row {nrows}, {key}')
                        values[key].append(v)
                if (nrows,digest) != EXPECTED[run]:
                    raise ValueError(f'Source SHA/row gate failed: {run}')
                onmask = [h > 4.5 for h in values['Heater_AO']]
                segments = []
                i = 0
                while i < len(onmask):
                    if not onmask[i]:
                        i += 1; continue
                    start = i
                    while i < len(onmask) and onmask[i]: i += 1
                    segments.append((start,i))
                on,action = max(segments,key=lambda p:p[1]-p[0])
                assert action < nrows, 'No recorded heater off sample'
                tim = values['Time since Start [min]'][on:action+1]
                if not all(b>a for a,b in zip(tim,tim[1:])):
                    raise ValueError('Non-increasing native time')
                result[run] = dict(t=tim, command=tim[-1], on=tim[0],
                                   channels={k:vals[on:action+1]
                                             for k,vals in values.items() if k not in ('Time since Start [min]', 'Heater_AO')},
                                   sha256=digest, row_count=nrows)
    assert set(result)==set(EXPECTED),f'Missing runs: {sorted(set(EXPECTED)-set(result))}'
    return result


def strict_preaction_indices(t: list[float], command: float):
    """Eligible separators must STRICTLY precede the recorded heater-off sample.

    The command sample is retained for source-clock context, never as a
    positive-lead certificate endpoint.
    """
    if not all(b > a for a, b in zip(t, t[1:])):
        raise ValueError('Native eligible clock must be strictly increasing')
    return tuple(i for i, ti in enumerate(t) if ti < command)


def gradients(t:list[float], temp:list[float]):
    out_t, g, raw_i = [], [], []
    for i,time in enumerate(t):
        q=time-W
        if q < t[0]:continue
        j=bisect.bisect_right(t,q)-1
        j=min(j,len(t)-2)
        frac=(q-t[j])/(t[j+1]-t[j])
        lag = temp[j]+frac*(temp[j+1]-temp[j])
        out_t.append(time);g.append((temp[i]-lag)/W);raw_i.append(i)
    return out_t,g,raw_i


def first_downcross(t,g,theta=TH):
    for i in range(len(t)-1):
        if g[i]>=theta and g[i+1]<theta:
            return t[i]+(theta-g[i])*(t[i+1]-t[i])/(g[i+1]-g[i])
    return None


def fmt(x):
    return '' if x is None else x


def write_csv(path,rows):
    if not rows:raise ValueError('Cannot write an empty table')
    with open(path,'w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys())
        writer.writeheader();writer.writerows(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-zips',type=Path,nargs=2,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    runs=read_inputs(args.source_zips)
    outputs,nominal,guards=[],[],[]
    for run,v in sorted(runs.items()):
        t,gs,gi=gradients(v['t'],v['channels'][SOURCE])
        prefix=[];current=math.inf
        for s in gs:
            current=min(current,s);prefix.append(current)
        src_event=first_downcross(t,gs)
        assert src_event is not None
        preaction = strict_preaction_indices(t, v['command'])
        assert preaction, 'No pre-action separators'
        for sensor,radius in SENSORS.items():
            tc,ga,ga_i=gradients(v['t'],v['channels'][sensor]);assert t==tc and gi==ga_i
            raw_event=first_downcross(t,ga)
            assert raw_event is not None
            nominal.append(dict(run=run,sensor=sensor,radius_mm=radius,
                                source_event_after_heateron_min=src_event-v['on'],
                                candidate_event_after_heateron_min=raw_event-v['on'],
                                command_lead_min=v['command']-raw_event,
                                reference_lead_min=src_event-raw_event))
            for h in HALFWIDTHS:
                thhi=TH+h;thlo=TH-h
                margins=[min(ga[0]-thhi,prefix[i]-thhi,thlo-ga[i]) for i in range(len(t))]
                kbest=max(preaction,key=lambda k:margins[k])
                radius_cert=max(0.,W/2*margins[kbest])
                guards.append(dict(run=run,sensor=sensor,radius_mm=radius,
                                   halfwidth_K_min=h,max_sign_margin_K_min=margins[kbest],
                                   certificate_error_radius_K=radius_cert,
                                   best_separator_after_heateron_min=t[kbest]-v['on']))
                for delta in ERROR_BOUNDS:
                    eps=2*delta/W
                    kval=next((i for i in preaction
                              if ga[0]>thhi+eps and prefix[i]>thhi+eps and ga[i]<thlo-eps),None)
                    assert kval is None or t[kval] < v['command']
                    outputs.append(dict(run=run,sensor=sensor,radius_mm=radius,
                        halfwidth_K_min=h,delta_raw_K=delta,
                        certified='PASS' if kval is not None else 'NOT_CERTIFIED',
                        sep_eligible_index=fmt(kval),
                        sep_native_min=fmt(t[kval] if kval is not None else None),
                        sep_after_heateron_min=fmt(t[kval]-v['on'] if kval is not None else None),
                        lead_lower_bound_min=fmt(v['command']-t[kval] if kval is not None else None),
                        certificate_radius_K=radius_cert,
                        recorded_command_native_min=v['command'],
                        nominal_command_lead_min=v['command']-raw_event,
                        first_source_gradient_K_min=gs[0],
                        first_candidate_gradient_K_min=ga[0],
                        sep_source_prefix_min_K_min=fmt(prefix[kval] if kval is not None else None),
                        sep_candidate_gradient_K_min=fmt(ga[kval] if kval is not None else None)))
    write_csv(args.out/'joint_lead_grid_24.csv',outputs)
    write_csv(args.out/'nominal_24.csv',nominal)
    write_csv(args.out/'joint_radii_24.csv',guards)
    # Legacy S5.1 reference radii for nearest candidate, DOWN-rounded at 6 digits.
    frozen={4:1.835240,5:1.931502,6:2.103596,7:1.756095,8:1.604085,9:1.881209}
    for d in guards:
        if d['sensor']=='TR404-085d' and d['halfwidth_K_min']==0.:
            assert 0 <= d['certificate_error_radius_K']-frozen[d['run']] < 1.e-6, (d,frozen)
    by_case=[]
    for h in HALFWIDTHS:
      for delta in ERROR_BOUNDS:
        ss=[x for x in outputs if x['halfwidth_K_min']==h and x['delta_raw_K']==delta]
        leads=[x['lead_lower_bound_min'] for x in ss if x['certified']=='PASS']
        nearest=[x for x in ss if x['sensor']=='TR404-085d']
        by_case.append(dict(halfwidth_K_min=h,delta_raw_K=delta,passes_24=sum(x['certified']=='PASS' for x in ss),
                            nearest_passes_6=sum(x['certified']=='PASS' for x in nearest),
                            min_guaranteed_lead_over_certified_min=min(leads) if leads else '',
                            full_24_min_guaranteed_lead_min=min(leads) if len(leads)==24 else '',
                            smallest_nominal_radius_K=min(x['certificate_radius_K'] for x in ss)))
    write_csv(args.out/'summary_grid.csv',by_case)
    focus=[x for x in outputs if x['halfwidth_K_min']==0.01 and x['delta_raw_K'] in (0,0.5,1,1.5,1.6) and x['sensor']=='TR404-085d']
    write_csv(args.out/'nearest_focus.csv',focus)
    qa=dict(status='PASS conditional recorded-trace certificate; not physical measurement budget',
      source_hashes={str(r):v['sha256'] for r,v in runs.items()},
      experimental_units=6,dependent_candidate_run_records=24,
      certificate_rows=len(outputs),halfwidths=HALFWIDTHS,deltas=ERROR_BOUNDS,
      original_radius_parity='6/6 PASS nearest nominal S5.1',
      full_24_at_h0p01_d1=next(x for x in by_case if x['halfwidth_K_min']==.01 and x['delta_raw_K']==1.),
      full_24_at_h0p01_d1p5=next(x for x in by_case if x['halfwidth_K_min']==.01 and x['delta_raw_K']==1.5),
      physical_uncertainty_calibrated=False,shutdown_executed=False,
      no_author_submission_change=True)
    (args.out/'QA_main.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(qa,indent=2))

if __name__=='__main__':main()
