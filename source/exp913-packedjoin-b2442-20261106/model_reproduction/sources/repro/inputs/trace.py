import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
s=a.source.resolve();o=a.out.resolve();o.mkdir(exist_ok=True,parents=True)
t=(s/'src/worker.cpp').read_text()
def rep(old,new):
 global t
 assert t.count(old)==1,old
 t=t.replace(old,new)
# The bundled EAT117 uses surface words; retain the six-column trace layout.
rep('    bool override_cycle=false, ready=false;',
    '    bool override_cycle=false, ready=false, ordinary=false;')
rep('    state.cycle=sd.cycle; state.ready=true;',
    '    state.cycle=sd.cycle; state.ready=true;\n    state.ordinary=(event==0 && !state.override_cycle);')
rep('    initialize();\n    CsvViewReader','    initialize(); FILE *diagnostic=std::fopen("nomtrace.bin","wb"); require(diagnostic,"trace"); static char diagbuf[65536]; std::setvbuf(diagnostic,diagbuf,_IOFBF,sizeof(diagbuf));\n    CsvViewReader')
rep('            const int answer=answers[i];','''            const auto& v=states[i];unsigned j=v.qx*46+v.qy;
            unsigned d=v.context/120;
            int response=v.ready?surface779(v.word,v.context,v.qx,v.qy):0;
            int32_t row[]={int32_t(v.pair*480+v.context),int32_t(j),int32_t(v.ready)+2*int32_t(v.ordinary),response,std::max(0,response+125*int(v.qx)+int(d%2?125:127)*int(v.qy)),answers[i]};
            require(std::fwrite(row,4,6,diagnostic)==6,"trace write");
            const int answer=answers[i];''')
rep('    querying=false;\n    require(std::fclose(out)','    querying=false; std::fclose(diagnostic);\n    require(std::fclose(out)')
w=o/'worker.cpp';w.write_text(t);cmd=json.loads((s/'build/build-report.json').read_text())['commands'];cc=list(cmd[0]);ld=list(cmd[-1])
output=cc.index('-o')+1;old=cc[output];cc[cc.index('src/worker.cpp')]=str(w);cc[output]=str(o/'worker.o');ld[ld.index(old)]=cc[output];ld[ld.index('-o')+1]=str(o/'estimate')
for c in [cc,ld]:subprocess.run(c,cwd=s,check=True)
