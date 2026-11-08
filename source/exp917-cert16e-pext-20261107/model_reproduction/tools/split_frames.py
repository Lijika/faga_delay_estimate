#!/usr/bin/env python3
"""Losslessly split existing FRAMES.BIN into 832 original compressed frames.

NOTE: this is archive restoration, *not* recomputation from FPGA graph.
"""
from pathlib import Path
import argparse,re,json
from asset_codec import decode

ROOT=Path(__file__).resolve().parents[1]
LEVELS=[0,1,2,3,4,5,6,8,10]
def sizes(path):
    txt=path.read_text()
    m=re.search(r'frameBytes\[832\]\s*=\s*\{([^{}]+)\}',txt)
    if not m:raise ValueError('no 832-entry frameBytes array')
    arr=[int(x.strip()) for x in m.group(1).split(',')]
    assert len(arr)==832
    return arr

def parse_payload(buf):
    if len(buf)<17280:raise ValueError('short frame')
    nib=buf[:17280]
    inds=[(b&15) for b in nib]+[(b>>4) for b in nib] # stats only
    if max(inds)>=9:raise ValueError('invalid rate nibble')
    counts=[0]*9
    for b in nib:counts[b&15]+=1;counts[b>>4]+=1
    if sum(counts)!=34560:raise AssertionError('rate count mismatch')
    n=17280+sum(counts[j]*LEVELS[j] for j in range(9))
    if n!=len(buf):raise ValueError(f'wrong byte count expected {n}, actual {len(buf)}')
    return counts

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--frames',type=Path,required=True)
 ap.add_argument('--lengths',type=Path,default=ROOT/'frozen/frameBytes.inc')
 ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--reencode',action='store_true',help='re-encode all decompressed code streams with Zstd-8 --no-check, compare bytes (requires zstd CLI)')
 ap.add_argument('--limit',type=int,default=832,help='number of first frames to inspect')
 a=ap.parse_args()
 frame_lens=sizes(a.lengths)
 data=a.frames.read_bytes()
 if sum(frame_lens)!=len(data):raise ValueError('concatenation size does not match frameBytes')
 a.out.mkdir(parents=True,exist_ok=True)
 from collections import Counter
 from tempfile import TemporaryDirectory
 import subprocess
 total=Counter();out=[];pos=0;encoded_equal=0;rawbytes=0
 for k,L in enumerate(frame_lens):
    frame=data[pos:pos+L];pos+=L
    if k>=a.limit:continue
    s,d=divmod(k,4)
    payload=decode(frame,400000)
    counts=parse_payload(payload);rawbytes+=len(payload);total.update({LEVELS[i]:c for i,c in enumerate(counts)})
    (a.out/f'c{s}-{d}.zst').write_bytes(frame)
    if a.reencode:
        # use a file input so zstd records frame content size; disabled checksum is crucial
        with TemporaryDirectory() as tmp:
            raw=Path(tmp)/'wire.raw';raw.write_bytes(payload)
            outbytes=subprocess.run(['zstd','-8','--no-check','--single-thread','-q','-c',str(raw)],stdout=subprocess.PIPE,check=True).stdout
        if outbytes!=frame:raise ValueError(f'frame {k} does not match re-encoded payload')
        encoded_equal+=1
 if a.limit==832:
    assert pos==len(data)
 receipt={'inspected_frames':min(a.limit,832),'total_compressed_bytes':sum(frame_lens[:a.limit]),'total_uncompressed_bytes':rawbytes,'rate_histogram':dict(sorted(total.items())),'zstd8_identical_reencodings':encoded_equal}
 (a.out/'decode-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
