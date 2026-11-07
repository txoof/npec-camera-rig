import csv
from pathlib import Path
from collections import Counter
cells4x5=[f"{c}{r}" for c in "ABCD" for r in range(1,6) if f"{c}{r}"!="A1"]
L=[]
def add(rig,exp,tray,cell,contents,outcome,ed,note=""):
    L.append(dict(rig=rig,experiment_id=exp,tray_id=tray,cell=cell,contents=contents,outcome=outcome,emerged_day="" if ed is None else ed,note=note))
exc={(1,"A3"):(0,"seedling small and faint at day 0"),(1,"A4"):(0,"seedling small and faint at day 0"),
     (3,"A4"):(1,""),(3,"D3"):(2,""),(3,"D5"):(1,"possibly faint at day 0"),
     (4,"A4"):(1,""),(4,"A5"):(4,"late seedling; possibly a faint trace on day 3"),(4,"C1"):(1,"possibly faint at day 0"),
     (6,"A2"):(3,"late seedling"),(6,"D2"):(1,"")}
T6="day 0 crop: cells placed about a third of a cell south of the openings"
for t in range(1,7):
    for c in cells4x5:
        ed,n=exc.get((t,c),(0,""))
        parts=[]
        if ed==0 and "faint" not in n: parts.append("already emerged at the first photo (sown before the experiment started)")
        if n: parts.append(n)
        if t==6: parts.append(T6)
        add("prod",18,t,c,"soil","plant",ed,"; ".join(parts))
soil7={"A2","B1","B2","C1","C2","D1"}
green7={"A3","A4","A5","B3","B4","B5","C3","C4","C5","D2","D3","D4"}
for c in cells4x5:
    if c in soil7: add("prod",18,7,c,"soil","plant",0,"already emerged at the first photo")
    else: add("prod",18,7,c,"bare cell (no soil)","empty",None,"green test square on it in late photos" if c in green7 else "black empty pot in late photos")
notes={8:"no soil; yellow board with green plastic plant models over B3 B4 C3 C4 (and over others in some photos)",
       9:"no soil; tag sheets, black pots and green squares in some photos",10:"no soil; tag sheets, black pots and large green sheets in some photos",
       11:"no soil; tag sheets, black pots and green squares in some photos",12:"no soil; tag sheets, black pots and green squares in some photos"}
for t,n in notes.items():
    for c in cells4x5: add("prod",18,t,c,"no soil, test objects","empty",None,n)
dev={76:"PPPP",77:"PPPP",78:"PPPP",79:"PPPP",80:"PPPP",81:"PPPP",85:"PPEE",86:"PPEP",87:"PPPE"}
devnote={79:"large plants, leaves cover neighbours",80:"green algae on the sand from about day 5",81:"plants lean out of their pots; late photos show stems only in some pots",87:"a neighbour's leaves lie over it"}
for t,s in dev.items():
    for c,k in zip(["A1","A2","B1","B2"],s):
        for exp in (2,3):
            if k=="P": add("dev",exp,t,c,"sand-filled pot","plant",0,"; ".join(x for x in ["plantlet present from the first photo (transplanted)",devnote.get(t,"") if t!=87 else ""] if x))
            else: add("dev",exp,t,c,"no pot (open tray grid)","empty",None,devnote.get(t,"") if t==87 else "")
with open(Path.home()/"scratch/375-cell-floor/data/labels.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(L[0])); w.writeheader(); w.writerows(L)
print(Counter((l["rig"],l["outcome"]) for l in L if not (l["rig"]=="dev" and l["experiment_id"]==3)))
