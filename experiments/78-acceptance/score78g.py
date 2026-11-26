import json, statistics as st
SQ={'North 1':('I',3018.77),'North 2':('A',98.60),'North 3':('E',397.74),'North 4':('K',1599.87),'North 5':('B',98.97),'North 6':('F',98.93),
    'South 1':('D',399.27),'South 2':('J',3023.17),'South 3':('H',397.40),'South 4':('C',98.87),'South 5':('L',1596.00),'South 6':('G',398.80)}
R=json.load(open('rows78g.json')); order=[f'{r} {i}' for r in ('North','South') for i in range(1,7)]; out=[]
print(f"{'slot':8}{'sq':3}{'cal':>7} | exg err% (run1/2/3)      | grown: read  err%   band% in  (run1 / run2 / run3)")
for s in order:
    sq,truth=SQ[s]; e=[];g=[];ins=[]
    for r in (1,2,3):
        xs=[x for x in R if x['slot']==s and x['run']==r]; b=xs[0]['band']
        me=st.median(x['c3'] for x in xs); mg=st.median(x['g3'] for x in xs)
        e.append((me/truth-1)*100); g.append((mg/truth-1)*100); ok=abs(mg-truth)<=mg*b/100; ins.append(ok)
        out.append(dict(slot=s,sq=sq,truth=truth,run=r,n=len(xs),band=b,exg=me,exg_err=e[-1],grown=mg,grown_err=g[-1],grown_inside=ok,
                        grown_min=min(x['g3'] for x in xs),grown_max=max(x['g3'] for x in xs),exg_inside=abs(me-truth)<=me*b/100))
    print(f"{s:8}{sq:3}{truth:7.1f} | {e[0]:+6.1f} {e[1]:+6.1f} {e[2]:+6.1f} |  {g[0]:+6.1f} {g[1]:+6.1f} {g[2]:+6.1f}   {b:4.1f}  {''.join('Y' if i else 'n' for i in ins)}")
json.dump(out,open('score78g.json','w'))
for r in (1,2,3):
    o=[x for x in out if x['run']==r]
    print('run',r,'exg inside',sum(x['exg_inside'] for x in o),'/12  grown inside',sum(x['grown_inside'] for x in o),'/12  | mean |err| exg',round(st.mean(abs(x['exg_err']) for x in o),1),' grown',round(st.mean(abs(x['grown_err']) for x in o),1))
print('grown errors range (%):',round(min(x['grown_err'] for x in out),1),'to',round(max(x['grown_err'] for x in out),1))
