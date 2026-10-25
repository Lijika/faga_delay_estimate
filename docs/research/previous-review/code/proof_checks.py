#!/usr/bin/env python3
import json,math
from pathlib import Path
r={}
r['gaps']={'to_99_pp':99-98.52,'to_99_1_pp':99.1-98.52,'speedup_100':220/100,'speedup_90':220/90,'time_reduction_100':1-100/220,'time_reduction_90':1-90/220,'loss_reduction_99':(99-98.52)/(100-98.52),'loss_reduction_99_1':(99.1-98.52)/(100-98.52)}
r['counts']={'full_states':60200*496,'z_states':60200*160,'nominal_cells':59904*264960,'nominal_u16_B':59904*264960*2,'all_role_queries_upper':60200**2*59904,'all_role_queries_u16_B':60200**2*59904*2,'word_bitmaps_B':239616*((60200+7)//8),'full_vertex_offset_u32_B':60200*496*4,'alt16_bidir_u32_B':60200*496*16*2*4,'right_sum_i16_B':(4800*8+260160)*2,'source_motion_cell_port_B':16*66000*8+66000*16+496*16}
r['conservative_elf']={'baseline':93402392,'condition_assets':3000000,'workers':524288,'indices_headers':262144,'padding':65536};r['conservative_elf_total']=sum(r['conservative_elf'].values());r['conservative_elf_headroom']=100000000-r['conservative_elf_total']
r['conservative_peak_rss_budget']={'baseline_peak':206372864,'new_elf_pages':3851968,'compiled_records':9511936,'vnni_right_sums':597120,'new_assets_restored_cap':33554432,'restore_scratch_cap':8388608,'extra_io_buffers_cap':8388608,'extra_stack_state_cap':2097152}
r['conservative_peak_rss_budget_total']=sum(r['conservative_peak_rss_budget'].values())
r['conservative_peak_rss_budget_headroom']=300000000-r['conservative_peak_rss_budget_total']
r['new_elf']={'u16_recipe_directory':59904*480*2,'recipes':8388608,'guards':8388608,'residual':4194304,'compact_near_fallback':8388608,'scales_headers':1048576,'shared_baseline_remainder':93402392-56503992-29308992,'new_workers':524288,'new_padding':262144};r['new_elf_total']=sum(r['new_elf'].values());r['new_elf_headroom']=100000000-r['new_elf_total']
r['dot_bounds']={'signed64_min':64*(-128*127),'signed64_max':64*128*128,'unsigned_signed64_min':64*255*(-128),'unsigned_signed64_max':64*255*127,'sum_b_min':64*(-128),'sum_b_max':64*127}
# Small exhaustive synthetic check; proof in the report establishes the general case.
cases=0
for g in range(1,33):
 for l in range(0,g+1,2):
  for u in range(g,40,3):
   for pred in range(-3,44):
    clamped=min(u,max(l,pred))
    assert abs(clamped-g)<=abs(pred-g)
    assert math.tanh(4*abs(clamped-g)/g)<=math.tanh(4*abs(pred-g)/g)+1e-15
    cases+=1
r['synthetic_clamp_cases']=cases;r['status']='pass';r['scope']='Arithmetic counts and synthetic projection cases, not project dataset evaluation'
print(json.dumps(r,ensure_ascii=False,indent=2))
