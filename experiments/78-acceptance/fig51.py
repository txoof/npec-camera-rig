import json
from PIL import Image, ImageDraw, ImageFont
S=json.load(open('score78g.json'))
order=[f'{a} {i}' for a in ('North','South') for i in range(1,7)]
size={'I':55,'A':10,'E':20,'K':40,'B':10,'F':10,'D':20,'J':55,'H':20,'C':10,'L':40,'G':20}
F=lambda n:ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',n)
INK=(30,30,30); GRID=(215,215,215); BAND=(200,200,200); BLUE=(37,125,224); ORG=(244,114,48)
W,H=1800,1500; im=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(im)
def panel(y0,y1,lo,hi,ticks,series,title,note):
    L,R=190,W-60; d.text((L,y0-70),title,fill=INK,font=F(26)); d.text((L,y0-38),note,fill=(90,90,90),font=F(19))
    Y=lambda v:y1-(v-lo)/(hi-lo)*(y1-y0)
    for t in ticks:
        d.line((L,Y(t),R,Y(t)),fill=(120,120,120) if t==0 else GRID,width=2 if t==0 else 1)
        d.text((L-14,Y(t)),f'{t:+d}%' if t else '0%',fill=INK,font=F(19),anchor='rm')
    colw=(R-L)/12
    for i,s in enumerate(order):
        cx=L+colw*(i+.5); rows=[x for x in S if x['slot']==s]; b=rows[0]['band']
        d.rectangle((cx-colw*.42,Y(min(b,hi)),cx+colw*.42,Y(max(-b,lo))),fill=BAND)
        for k,(key,col,shape) in enumerate(series):
            vals=[x[key] for x in rows]; xo=cx+(k-(len(series)-1)/2)*colw*.28
            lo_,hi_=max(min(vals),lo),min(max(vals),hi)
            d.line((xo,Y(hi_),xo,Y(lo_)),fill=col,width=4)
            for v in vals:
                v=min(max(v,lo),hi); r=9
                if shape=='circle': d.ellipse((xo-r,Y(v)-r,xo+r,Y(v)+r),fill=col)
                else: d.rectangle((xo-r,Y(v)-r,xo+r,Y(v)+r),fill='white',outline=col,width=4)
        sq=rows[0]['sq']; d.text((cx,y1+14),s.replace('North ','N').replace('South ','S'),fill=INK,font=F(20),anchor='mt')
        d.text((cx,y1+40),f"{sq} {size[sq]} mm",fill=INK,font=F(18),anchor='mt')
    d.line((L,y0,L,y1),fill=INK,width=2)
    return Y
ex=('exg_err',ORG,'square'); gr=('grown_err',BLUE,'circle')
panel(150,650,-100,20,[-100,-80,-60,-40,-20,0,20],[ex,gr],'Error of each square, both methods (all 12 slots)','Each marker is one run (3 per method per slot); the line joins them. Grey bar: the slot\'s validation band around 0.')
panel(900,1350,-2,12,[0,2,4,6,8,10,12],[gr],'Grow from leaf cores only, enlarged','Same data as above, scale -2% to +12%. A marker inside the grey bar is inside the band.')
d.rectangle((190,1440,214,1464),fill='white',outline=ORG,width=4); d.text((224,1452),'Green threshold, 0.1',fill=INK,font=F(20),anchor='lm')
d.ellipse((520,1440,544,1464),fill=BLUE); d.text((554,1452),'Grow from leaf cores',fill=INK,font=F(20),anchor='lm')
d.rectangle((860,1440,884,1464),fill=BAND); d.text((894,1452),'Validation band of the slot',fill=INK,font=F(20),anchor='lm')
im=im.convert('P',palette=Image.ADAPTIVE,colors=32); im.save('/home/pi/wt/npec-78-acceptance-known-area/docs/figures/51/errors-by-slot-2026-11-26.png',optimize=True)
