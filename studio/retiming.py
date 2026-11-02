"""Monotone source/work-time mapping. No original subtitle timestamps are edited."""
from bisect import bisect_right
import math


def voice_timing(project, rows):
    measured={r['id']:r for r in rows}
    groups=[]
    for cue in sorted(project.cues,key=lambda c:c.start):
        if not groups or cue.start!=groups[-1][0].start:groups.append([])
        groups[-1].append(cue)
    spans=[];scheduled={};cursor=0.;out=0.
    def append(a,b,length):
        nonlocal out
        if b<=a:return
        spans.append(dict(start=a,end=b,out_start=out,out_end=out+length))
        out+=length
    for i,group in enumerate(groups):
        start=group[0].start
        if start>=project.duration:continue
        if start>cursor:append(cursor,start,(start-cursor)/project.work_speed)
        end=min(project.duration,max(c.end for c in group),groups[i+1][0].start if i+1<len(groups) else project.duration)
        selected=[c for c in group if c.id in measured]
        # Concurrent source cues are spoken sequentially in stable SRT order.
        lengths=[max(0.,float(measured[c.id]['duration'])) for c in selected]
        needed=sum(lengths)+.04*max(0,len(lengths)-1)
        length=max((end-start)/project.work_speed,needed)
        position=out
        append(start,end,length)
        for cue,duration in zip(selected,lengths):
            scheduled[cue.id]=dict(start=position,end=position+duration,
                cue_end=out,applied=1.,ok=True,spill=0.)
            position+=duration+.04
        cursor=end
    if cursor<project.duration:append(cursor,project.duration,(project.duration-cursor)/project.work_speed)
    return dict(spans=spans,rows=scheduled,duration=out)


def map_time(timing,value,inverse=False):
    spans=timing['spans']
    if not spans:return 0.
    a,b,c,d=('out_start','out_end','start','end') if inverse else ('start','end','out_start','out_end')
    index=max(0,min(len(spans)-1,bisect_right([s[a] for s in spans],value)-1))
    s=spans[index];fraction=max(0.,min(1.,(value-s[a])/(s[b]-s[a])))
    return s[c]+fraction*(s[d]-s[c])


def source_rate(timing,value,final_speed=1.):
    spans=timing['spans']
    if not spans:return final_speed
    i=max(0,min(len(spans)-1,bisect_right([s['start'] for s in spans],value)-1))
    s=spans[i]
    return (s['end']-s['start'])/(s['out_end']-s['out_start'])*final_speed


def validate_framing(p):
    f=p.framing
    if not isinstance(f,dict) or set(f)!={'zoom','x','y','flip'}:raise ValueError('Khung cắt không hợp lệ.')
    for key,low,high in [('zoom',1,4),('x',0,100),('y',0,100)]:
        if not isinstance(f[key],(int,float)) or not math.isfinite(f[key]) or not low<=f[key]<=high:raise ValueError('Khung cắt nằm ngoài giới hạn.')
    if not isinstance(f['flip'],bool):raise ValueError('Thiết lập lật hình không hợp lệ.')


def framing_pixels(p):
    """Keep source aspect ratio and output size; crop first, then scale to fill."""
    f=p.framing
    if f['zoom']==1:return 0,0,p.width,p.height
    w=max(2,int(p.width/f['zoom'])//2*2);h=max(2,int(p.height/f['zoom'])//2*2)
    w=min(p.width,w);h=min(p.height,h)
    x=int((p.width-w)*f['x']/100)//2*2;y=int((p.height-h)*f['y']/100)//2*2
    return x,y,w,h


def framing_filter(p):
    x,y,w,h=framing_pixels(p)
    filters=[f'crop={w}:{h}:{x}:{y}',f'scale={p.width}:{p.height}', 'setsar=1'] if p.framing['zoom']>1 else ['null']
    if p.framing['flip']:filters.append('hflip')
    return ','.join(filters)
