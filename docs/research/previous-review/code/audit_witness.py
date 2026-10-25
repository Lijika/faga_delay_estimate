#!/usr/bin/env python3
"""Validate unpacked exp705 arrays and produce descriptive (not blind-test) statistics.
Run the repository's path_witness/unpack.py with its SHA checks FIRST.
Requires NumPy. This audit is not an independent graph shortest-path solver.
"""
import argparse,json
from pathlib import Path
import numpy as np

def load(root,name,dtype,shape):
    matches=list(root.rglob(name))
    if len(matches)!=1:raise ValueError(f'Expected exactly one {name}: {matches}')
    arr=np.fromfile(matches[0],dtype=dtype)
    if arr.size!=int(np.prod(shape)):raise ValueError(f'Bad size for {name}: {arr.size}')
    return arr.reshape(shape)

def audit(root):
    n=239616;pairs=59904
    qpath=list(root.rglob('queries.bin'))
    if len(qpath)!=1:raise ValueError('queries.bin absent or ambiguous')
    with qpath[0].open('rb') as f:
        head=f.read(12)
        if head[:8]!=b'EX535Q01' or int.from_bytes(head[8:],'little')!=n:raise ValueError('Header mismatch')
        q=np.frombuffer(f.read(),dtype='<i4').reshape(n,10)
    length=load(root,'paths.lengths.u32','<u4',(n,));words=load(root,'paths.words.u8','u1',(5558667,))
    summary=load(root,'paths.summary.i32','<i4',(n,8));norm=load(root,'normalized.i32','<i4',(pairs,4));cross=load(root,'cross.i32','<i4',(pairs,4,4,7))
    checks={'sum_lengths':int(length.sum())==words.size,'word_domain':bool(np.all(words<160)),'net_hops':bool(np.array_equal(length,summary[:,5])),'line_zero':bool(np.all(summary[:,1]==0)),'x_conservation':bool(np.array_equal(q[:,2]-q[:,0],summary[:,3]+summary[:,7])),'y_conservation':bool(np.array_equal(q[:,3]-q[:,1],summary[:,4]))}
    if not all(checks.values()):raise ValueError('Failed conservation check: '+str(checks))
    D0=summary[:,:3].astype(np.int64).sum(axis=1).reshape(pairs,4)
    valid=np.isin(cross[:,:,:,0],[0,4]);delta=cross[:,:,:,5]
    costconsistent=np.all((cross[:,:,:,4]-D0[:,None,:])[valid]==delta[valid])
    if not costconsistent:raise ValueError('Valid replay cost-minus-D0 inconsistency')
    if np.any(delta[valid]<0):raise ValueError('A legal replay beats the saved D0; investigate labels or semantics')
    own=np.eye(4,dtype=bool)[None,:,:];other=valid&~own
    has=np.any(other,axis=1);exact=np.any(other&(delta==0),axis=1)
    changed=cross[:,:,:,0]==3;target_x=q[:,2].reshape(pairs,4)[:,None,:];target_y=q[:,3].reshape(pairs,4)[:,None,:]
    dx=(cross[:,:,:,2]-target_x)[changed];dy=(cross[:,:,:,3]-target_y)[changed]
    shifts,counts=np.unique(np.stack([dx,dy],axis=1),axis=0,return_counts=True)
    return {'scope':'Historical four-position diagnostic, D0 only; no deployment selection or population claim','checks':checks,'queries':n,'tokens':int(words.size),'normalized_varying_pairs':int(np.count_nonzero(np.ptp(norm,axis=1))),'normalized_range_ge20_pairs':int(np.count_nonzero(np.ptp(norm,axis=1)>=20)),'other_word_legal_coverage':int(has.sum()),'other_word_exact_D0':int(exact.sum()),'all_replay_reason_histogram':{str(i):int(np.sum(cross[:,:,:,0]==i)) for i in range(5)},'all_reason3_shifts':[{'dx':int(v[0]),'dy':int(v[1]),'count':int(c)} for v,c in zip(shifts,counts)]}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('unpacked_root',type=Path);p.add_argument('--out',type=Path);a=p.parse_args();text=json.dumps(audit(a.unpacked_root),ensure_ascii=False,indent=2)
    if a.out:a.out.write_text(text+'\n',encoding='utf-8')
    else:print(text)
