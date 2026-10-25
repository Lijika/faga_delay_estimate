#!/usr/bin/env python3
"""Evaluate port-compatible local support with a fixed residual budget."""
import gc
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp679/validation").resolve()))
sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp679_hv_cli as deployment
import exp709_cost_skeleton as execution

fit = deployment.fit
ROOT, BUILD = Path("validation/results/exp713"), Path("build/exp713")
PLAN = Path("experiment/实验713-端口兼容的首尾局部支持与同预算残差.md")
execution.ROOT = ROOT
read, write, identity, checked = fit.read, fit.write, fit.identity, fit.checked
SEED, ROWS = 20261025713, 1_000_000
PARAMS = read("../exp640/validation/results/exp640/prepare.json")["params"]
ARCH = Path("../exp652/doc/eda比赛文件/arch")


def support_check(query, original):
    ports = [p["Name"] for p in read(ARCH / "SRB_Port.json")["Port"]]
    ids = {p:i for i,p in enumerate(ports)}
    nets = read(ARCH / "SRB_Net.json")["Nets"]
    arcs = read(ARCH / "SRB_Arc.json")["Arcs"]
    motions = sorted({(n["delta x"], n["delta y"]) for n in nets})
    assert len(motions) == 16
    assert np.array_equal(np.fromfile(BUILD/"motions.i16","<i2").reshape(-1,2), motions)
    exists = np.zeros((550,120),bool)
    for p in read(ARCH / "SRB_Inst.json")["Inst"]:
        exists[p["y"],p["x"]] = True
    yy,xx = np.indices(exists.shape)
    cells = np.zeros((550,120,2),"<u2")
    net_motion, after = {}, np.arange(496)
    for n in nets:
        code = motions.index((n["delta x"],n["delta y"]))
        net_motion[ids[n["from"]]] = code
        after[ids[n["from"]]] = ids[n["to"]]
    for code,(dx,dy) in enumerate(motions):
        compressed = xx - 14*((yy%100<50)&(xx>=90))
        shifted = compressed+dx
        tx = shifted+14*((yy%100<50)&(shifted>=76)) if dx else xx.copy()
        ty = yy+dy
        valid = exists & (tx>=0)&(tx<120)&(ty>=0)&(ty<550)
        valid[valid] &= exists[ty[valid],tx[valid]]
        cells[:,:,0][valid] |= np.uint16(1<<code)
        np.bitwise_or.at(cells[:,:,1], (ty[valid],tx[valid]), np.uint16(1<<code))
    ptable = np.zeros((496,2),"<u2")
    for a in arcs:
        p,t = ids[a["from"]],ids[a["to"]]
        if t in net_motion:
            ptable[p,0] |= np.uint16(1<<net_motion[t])
    for n in nets:
        m = net_motion[ids[n["from"]]]
        terminal = ids[n["to"]]
        ptable[terminal,1] |= np.uint16(1<<m)
        for a in arcs:
            if ids[a["from"]] == terminal:
                ptable[ids[a["to"]],1] |= np.uint16(1<<m)
    assert np.array_equal(cells,np.fromfile(BUILD/"cells.u16","<u2").reshape(550,120,2))
    assert np.array_equal(ptable,np.fromfile(BUILD/"ports.u16","<u2").reshape(496,2))
    generated = np.fromfile(BUILD/"features.u16","<u2").reshape(ROWS,4)
    assert np.array_equal(query[:,:4],original[:,[26,27,30,31]])
    assert np.array_equal(generated[:,:2],original[:,28:30])
    ax,ay = generated[:,0].astype("i4"),generated[:,1].astype("i4")
    tx,ty,sp,tp = (query[:,j] for j in (2,3,8,9))
    masks = np.column_stack((cells[ay,ax,0]&ptable[after[sp],0],
                            cells[ty,tx,1]&ptable[tp,1]))
    assert np.array_equal(generated[:,2:],masks)
    features = ((masks[:,:,None] >> np.arange(16))&1).reshape(ROWS,32).astype("<f4")
    write(ROOT/"support-check.json",dict(all_equal=True,positions=66000,ports=496,
        motions=motions,rows=ROWS,table_bytes=cells.nbytes+ptable.nbytes+64,
        support_bit_population=features.mean(axis=0).tolist(),
        unique_cell_masks=[len(np.unique(cells[:,:,i])) for i in range(2)],
        tables=[identity(BUILD/p) for p in ("cells.u16","ports.u16","motions.i16","features.u16")]))
    return features


def training(features, data, arm):
    raw = np.full(ROWS,np.nan,"<f8")
    predict = fit.decoder()
    target = (data["d0"]-data["base"]).astype("f4")
    weight = (1000/np.maximum(data["d0"]+data["mandatory"],128)).astype("f4")
    records = []
    for fold in range(3):
        for route in range(16):
            members = data["routes"]==route
            learn = members & (data["folds"]!=fold)
            test = members & (data["folds"]==fold)
            assert not np.intersect1d(data["clusters"][learn],data["clusters"][test]).size
            model = fit.cb.CatBoostRegressor(**PARAMS)
            model.fit(features[learn],target[learn],sample_weight=weight[learn])
            path = BUILD/f"{arm}-{fold}-{route}.json"
            model.save_model(str(path),format="json")
            values,leaves = predict(read(path),features[test],8)
            native = model.predict(features[test],ntree_end=8,thread_count=1)
            assert np.array_equal(leaves,model.calc_leaf_indexes(features[test],ntree_end=8,thread_count=1))
            assert np.allclose(values,native,rtol=0,atol=1e-10)
            assert np.array_equal(fit.decode(values,data["base"][test],data["mandatory"][test]),
                                  fit.decode(native,data["base"][test],data["mandatory"][test]))
            raw[test] = values
            records.append(dict(fold=fold,route=route,source_pin_overlap=0,
                train_rows=int(learn.sum()),test_rows=int(test.sum()),model=identity(path),
                leaf_indices_equal=True,integer_prediction_equal=True))
            del model,leaves
            gc.collect()
        print("EXP713_TRAINED",arm,fold,flush=True)
    assert np.isfinite(raw).all() and len(records)==48
    raw.tofile(BUILD/(arm+"-raw.f64"))
    write(ROOT/(arm+"-training.json"),dict(complete=True,records=records,
        params=PARAMS,prefix=8,raw=identity(BUILD/(arm+"-raw.f64"))))
    return raw


def evaluate(data,event,raws):
    predictions = {a:fit.decode(v,data["base"],data["mandatory"]) for a,v in raws.items()}
    truth,x = data["truth"],data["features"]
    dx,dy = x[:,8]+x[:,6],x[:,9]+x[:,7]
    family = x[:,0].astype("i4")
    groups = dict(source_family=family,target_family=x[:,2].astype("i4"),
        distance=np.searchsorted([24,100,300],np.abs(dx)+np.abs(dy)),
        near_axis=((np.abs(dx)<20)|(np.abs(dy)<24)).astype("i4"),
        direction=2*(dx<0)+(dy<0),event=event,fold=data["folds"],route=data["routes"])
    counts = np.bincount(family,minlength=26)
    draws = np.random.default_rng(SEED).integers(26,size=(9999,26))
    scores = {a:fit.points(p,truth) for a,p in predictions.items()}
    comparisons,passed = {},[]
    for arm in ("P","R"):
        assert np.array_equal(predictions[arm][event==2],predictions["A"][event==2])
        eligible = True
        for reference in ("A","C"):
            result = fit.transition(predictions[arm],predictions[reference],truth,groups)
            delta = scores[arm]-scores[reference]
            total = np.bincount(family,weights=delta,minlength=26)
            interval = np.quantile(total[draws].sum(axis=1)/counts[draws].sum(axis=1),[.00625,.99375])
            result["four_comparison_simultaneous_family_ci95_pp"] = interval.tolist()
            result["changed_rows"] = int(np.count_nonzero(predictions[arm]!=predictions[reference]))
            minimum = min(v["delta_accuracy_pp"] for key,g in result["groups"].items()
                          if key in ("distance","near_axis","direction") for v in g.values())
            result["quality_gate"] = bool(result["delta_accuracy_pp"]>=.05 and interval[0]>0 and minimum>=-.03)
            eligible &= result["quality_gate"]
            comparisons[arm+"-"+reference] = result
        if eligible:
            passed.append(arm)
    selected = max(passed,key=lambda a:(float(scores[a].mean()),a=="R")) if passed else None
    for arm,value in predictions.items():
        value.astype("<i4").tofile(BUILD/(arm+"-prediction.i32"))
    return dict(all_checks_passed=True,comparisons=comparisons,
        metrics={a:fit.stats(v,truth) for a,v in predictions.items()},selected=selected,
        independent_requests=False,new_exact_rows=0,full_estimator_runs=0,
        V_predictions_unchanged=True,source_pin_overlap=0,static_elf_and_cpu_verified=False)


def main():
    assert socket.gethostname()=="lhj-R4900-G3"
    assert Path.cwd()==Path("/home/lhj/lhjwork/eda2026/research/exp713")
    assert os.environ["OPENBLAS_NUM_THREADS"]==os.environ["OMP_NUM_THREADS"]=="1"
    assert fit.cb.__version__=="1.2.8"
    assert read("../exp712/validation/results/exp712/report.json")["all_checks_passed"]
    assert not ROOT.exists() and not BUILD.exists()
    resource.setrlimit(resource.RLIMIT_CPU,(1800,1800))
    resource.setrlimit(resource.RLIMIT_AS,(8<<30,8<<30))
    started,cpu = time.monotonic(),time.process_time()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN,ROOT/"protocol-original.md")
    assert PARAMS==read("../exp656/validation/results/exp656/prepare.json")["params"]
    (ROOT/"installed-catboost-help.txt").write_text(fit.cb.__version__+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor.fit))+"\n"+
        fit.cb.CatBoostRegressor.save_model.__doc__)
    inputs = []
    for path,expected in (
        (fit.prior.OLD_RAW,read("../exp640/validation/results/exp640/training.json")["raw"]["S8"]),
        (Path("../exp656/build/exp656/S8-raw.f64"),read("../exp656/validation/results/exp656/training.json")["raw"]["S8"]),
        (Path("../exp678/build/exp678/HV8-raw.f64"),read("../exp678/validation/results/exp678/training.json")["raw"]["8"]),
        (fit.prior.CURVES,read("../exp654/validation/results/exp654/freeze.json")["asset"]),
    ):
        checked(path,expected)
        inputs.append(identity(path))
    qpath = Path("../exp535/build/exp535/queries.bin")
    checked(qpath,read("../exp535/validation/results/exp535/input.json")["queries"])
    dependencies = [Path("../exp580/build/exp580/architecture-resolver.o"),
                    Path("../exp579/build/exp579/arch-text.o")]
    command = ["g++","-std=c++17","-O3","-Wall","-Wextra","-Werror",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH","-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "-I","../exp589/src","tests/exp713_local_support.cpp",
        *map(str,dependencies),"-static","-o",str(BUILD/"support")]
    execution.measured(command,"compile")
    assert not (ROOT/"compile.stderr").read_bytes()
    execution.measured([str(BUILD/"support"),str(qpath),str(BUILD)],"component")
    assert read(ROOT/"component.stdout")["rows"]==ROWS
    data = fit.prior.source.load()
    data["base"] = fit.prior.curve_base(data)
    x = data["features"]
    gap = read(ARCH/"SRB_Gap.json")["Gap"]
    h,v,_,_ = fit.prior.events(x[:,28:32],gap["Block"])
    event = h.astype("u1")+2*v
    frozen_v = np.fromfile("../exp678/build/exp678/HV8-raw.f64","<f8")
    raws = dict(A=np.fromfile(fit.prior.OLD_RAW,"<f8"),
                C=np.fromfile("../exp656/build/exp656/S8-raw.f64","<f8"))
    for raw in raws.values():
        raw[event==2] = frozen_v[event==2]
    baseline = fit.stats(fit.decode(raws["A"],data["base"],data["mandatory"]),data["truth"])
    expected = read("../exp700/validation/results/exp700/report.json")["baseline_metrics"]
    assert all(abs(baseline[k]-expected[k])<1e-10 for k in baseline)
    q = np.fromfile(qpath,"<i4",offset=12).reshape(ROWS,10)
    support = support_check(q,x)
    files = [Path(__file__),PLAN,ROOT/"protocol-original.md",Path("tests/exp713_local_support.cpp"),
        qpath,*dependencies,*ARCH.glob("*.json"),Path(fit.__file__),Path(fit.prior.__file__),
        Path(fit.prior.source.__file__),fit.DECODER,
        Path("../exp623/build/exp623/data.npz"),Path("../exp585/build/exp585/training.npz"),
        Path("../exp593/build/exp593/targets.npz"),
        Path("../exp656/validation/results/exp656/prepare.json")]
    write(ROOT/"freeze.json",dict(inputs=inputs+[identity(p) for p in files],params=PARAMS,
        seed=SEED,baseline_metrics=baseline,columns=dict(P=85,R=61),
        component_binary=identity(BUILD/"support"),compile_command=command,
        python=sys.version,numpy=np.__version__,disk_free_start_bytes=shutil.disk_usage(".").free))
    for arm in ("P","R"):
        original = x if arm=="P" else np.column_stack((x[:,:26],x[:,50:53]))
        features = np.column_stack((original,support)).astype("<f4")
        assert features.shape==(ROWS,85 if arm=="P" else 61)
        raw = training(features,data,arm)
        raw[event==2] = frozen_v[event==2]
        raws[arm] = raw
        del features,original
        gc.collect()
    result = evaluate(data,event,raws)
    result["resources"] = dict(cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        disk_free_end_bytes=shutil.disk_usage(".").free)
    assert result["resources"]["cpu_s"]<=1800 and result["resources"]["wall_s"]<=1800
    assert result["resources"]["rss_bytes"]<=2_000_000_000
    write(ROOT/"report.json",result)
    print("EXP713_COMPLETE",result["selected"],
          {k:v["delta_accuracy_pp"] for k,v in result["comparisons"].items()},flush=True)


if __name__=="__main__":
    main()
