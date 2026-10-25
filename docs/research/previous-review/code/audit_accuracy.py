#!/usr/bin/env python3
"""Independent streaming check of the released exp688 accuracy CSV.
This script has not been run on the repository's binary/CSV assets in this review.
Usage: python audit_accuracy.py exp688-exact-subset.csv.gz --out audit.json
A candidate column in the SAME aligned CSV may be passed via --candidate-column.
"""
import argparse, csv, gzip, json, math
from collections import defaultdict
from pathlib import Path

def point_score(g, p):
    if g < 0: raise ValueError('Unreachable labels need an explicitly specified scoring rule.')
    return (100.0 if p == 0 else 0.0) if g == 0 else 100.0*(1.0-math.tanh(4.0*abs(p-g)/g))

def audit(path, candidate=None):
    op = gzip.open if str(path).endswith('.gz') else open
    strata, seen = {}, set()
    total_w = total_s = loss = mae = hit = 0.0
    groups=defaultdict(lambda: [0.,0.,0])
    with op(path, 'rt', encoding='utf-8', newline='') as f:
        reader=csv.DictReader(f)
        required={'sample_index','pair_id','exact_delay','exp688_prediction','population_pair_rows','sample_weight','From','To'}
        if candidate: required.add(candidate)
        if not required.issubset(reader.fieldnames or []): raise ValueError('Missing columns: '+str(required-set(reader.fieldnames or [])))
        for r in reader:
            ix=int(r['sample_index']); h=int(r['pair_id']); g=int(r['exact_delay']); p=int(r['exp688_prediction'])
            if ix in seen: raise ValueError('Repeated sample_index '+str(ix))
            seen.add(ix);w=float(r['sample_weight']);N=int(r['population_pair_rows'])
            if not math.isfinite(w) or w<=0 or N<=0: raise ValueError('Nonpositive weight/population')
            score=point_score(g,p); d=point_score(g,int(r[candidate]))-score if candidate else 0.
            z=strata.setdefault(h,{'N':N,'n':0,'w':w,'mean':0.,'M2':0.,'dmean':0.,'dM2':0.})
            if z['N']!=N or abs(z['w']-w)>1e-8: raise ValueError('Inconsistent within-stratum metadata')
            z['n']+=1;n=z['n'];delta=score-z['mean'];z['mean']+=delta/n;z['M2']+=delta*(score-z['mean'])
            dd=d-z['dmean'];z['dmean']+=dd/n;z['dM2']+=dd*(d-z['dmean'])
            total_w+=w;total_s+=w*score;loss+=w*(100-score);mae+=w*abs(p-g);hit+=w*(p==g)
            delay_bucket='zero' if g==0 else '<128' if g<128 else '128..511' if g<512 else '512..2047' if g<2048 else '>=2048'
            seenflag=r.get('source_pin_seen_in_training','unknown')
            for key in ['delay:'+delay_bucket,'source_seen:'+seenflag]:
                q=groups[key];q[0]+=w;q[1]+=w*(100-score);q[2]+=1
    if not seen: raise ValueError('Empty data')
    for h,z in strata.items():
        if z['n']>z['N']: raise ValueError(f'Stratum {h} has more sampled than population rows')
        if z['n']<2: raise ValueError(f'Stratum {h} has fewer than 2 rows; variance unidentified')
        if abs(z['w']*z['n']-z['N'])>1e-6: raise ValueError(f'Weights do not expand to population in stratum {h}')
    pop=sum(z['N'] for z in strata.values());var=dvar=dmean=0.
    for z in strata.values():
        W=z['N']/pop;fpc=max(0.,1-z['n']/z['N'])
        var+=W*W*fpc*z['M2']/(z['n']-1)/z['n']
        dvar+=W*W*fpc*z['dM2']/(z['n']-1)/z['n'];dmean+=W*z['dmean']
    acc=total_s/total_w;se=math.sqrt(var)
    out={'rows':len(seen),'strata':len(strata),'expanded_rows':total_w,'Acc_percent':acc,'MAE_ps':mae/total_w,'exact_hit_fraction':hit/total_w,'design_SE_pp':se,'normal_95_CI_percent':[acc-1.95996398454*se,acc+1.95996398454*se], 'scope':'SRSWOR within pair strata; normal design interval, not source-cluster sensitivity or new-blind generalization guarantee', 'groups':{k:{'population_share':a[0]/total_w,'total_Acc_loss_pp':a[1]/total_w,'sample_rows':a[2]} for k,a in groups.items()}}
    if candidate:out['paired_delta']={'mean_pp':dmean,'design_SE_pp':math.sqrt(dvar),'normal_95_CI_pp':[dmean-1.95996398454*math.sqrt(dvar),dmean+1.95996398454*math.sqrt(dvar)]}
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('csv_path',type=Path);p.add_argument('--candidate-column');p.add_argument('--out',type=Path);a=p.parse_args()
    result=audit(a.csv_path,a.candidate_column);text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:a.out.write_text(text+'\n',encoding='utf-8')
    else:print(text)
