"""Original-media timestamps are canonical; speed is a non-destructive transform."""
from __future__ import annotations
import asyncio, hashlib, json, math, os, re, shutil, subprocess, threading, time, uuid, wave
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

RATE = 24000
ROOT = Path(__file__).resolve().parent.parent

@dataclass
class Cue:
    start: float
    end: float
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    voice: str = ''
    tts_rate: int = 0

@dataclass
class Project:
    version: int = 1
    video: str = ''
    video_codec: str = ''
    duration: float = 0
    width: int = 1920
    height: int = 1080
    has_audio: bool = False
    cues: list[Cue] = field(default_factory=list)
    work_speed: float = 1.0
    final_speed: float = 1.0
    voice: str = 'vi-VN-NamMinhNeural'
    tts_rate: int = 0
    tts_workers: int = 3
    voice_batch_minutes: int = 10
    voice_batch_index: int = 0
    batch_reviewed: dict = field(default_factory=dict)
    voice_batch_kept: list = field(default_factory=list)
    export_preset: str = "veryfast"
    max_fit: float = 1.6
    music_clean: dict = field(default_factory=dict)
    music_threads: int = 2
    music_backend: str = "cpu"
    original_volume: float = .12
    voice_volume: float = 1.0
    style: dict = field(default_factory=lambda: dict(font='Arial', size=52, color='#FFFFFF', outline=3, shadow=2, bold=True, x=50., y=88., width=88., box=False))
    screen_regions: list = field(default_factory=list)
    mask: dict = field(default_factory=lambda: dict(enabled=False, mode='blur', x=8., y=80., w=84., h=14., opacity=1.0, color='#171717'))

    @property
    def speed(self): return self.work_speed * self.final_speed
    @property
    def output_duration(self): return self.duration / self.speed

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, data):
        if data.get('version') != 1: raise ValueError('Phiên bản dự án chưa được hỗ trợ.')
        data = dict(data); data['cues'] = [Cue(**c) for c in data.get('cues', [])]
        p = cls(**data)
        if not (.25 <= p.work_speed <= 2 and .25 <= p.final_speed <= 4): raise ValueError('Tốc độ không hợp lệ.')
        if not 1<=p.tts_workers<=6:raise ValueError('Số luồng TTS phải trong khoảng 1–6.')
        if not isinstance(p.voice_batch_minutes,int) or not 1<=p.voice_batch_minutes<=120:raise ValueError('Đợt voice phải dài từ 1 đến 120 phút.')
        if not isinstance(p.voice_batch_index,int) or p.voice_batch_index<0:raise ValueError('Số thứ tự đợt voice không hợp lệ.')
        if not isinstance(p.batch_reviewed,dict):raise ValueError('Trạng thái rà lô không hợp lệ.')
        if not isinstance(p.voice_batch_kept,list):raise ValueError('Danh sách lô đã giữ không hợp lệ.')
        last=0
        for bounds in p.voice_batch_kept:
            if not isinstance(bounds,(list,tuple)) or len(bounds)!=2:raise ValueError('Mốc lô không hợp lệ.')
            a,b=bounds
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in bounds) or not 0<=a<b or a<last:raise ValueError('Các lô đã giữ bị chồng mốc.')
            last=b
        if p.music_backend not in ('cpu','dml'):raise ValueError('Chế độ giảm nhạc không hợp lệ.')
        if not isinstance(p.music_threads,int) or not 1<=p.music_threads<=8:raise ValueError('Số luồng giảm nhạc phải từ 1 đến 8.')
        if not isinstance(p.music_clean,dict):raise ValueError('Cấu hình giảm nhạc không hợp lệ.')
        if p.export_preset not in ('ultrafast','veryfast','medium'):raise ValueError('Chế độ xuất không hợp lệ.')
        for region in p.screen_regions:validate_screen_region(region,p.duration)
        if len({r["id"] for r in p.screen_regions})!=len(p.screen_regions):raise ValueError("ID vùng chữ bị trùng.")
        for c in p.cues: validate_cue(c)
        if len({c.id for c in p.cues}) != len(p.cues): raise ValueError('ID phụ đề bị trùng.')
        p.cues.sort(key=lambda c: c.start)
        return p

TIME_RE = r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})'
TIMING = re.compile(r'^\s*'+TIME_RE+r'\s*-->\s*'+TIME_RE+r'(?:\s+.*)?$')

def seconds(parts):
    h,m,s,ms = map(int,parts)
    if m>59 or s>59: raise ValueError('Mốc thời gian không hợp lệ.')
    return h*3600+m*60+s+ms/1000

def parse_time(s):
    m = re.fullmatch(TIME_RE,s.strip())
    if not m: raise ValueError('Nhập mốc dạng 00:01:23,456.')
    return seconds(m.groups())

def stamp(t, ass=False):
    n = max(0,round(t*(100 if ass else 1000)))
    unit = 100 if ass else 1000
    sec, sub = divmod(n,unit); h,sec=divmod(sec,3600); m,s=divmod(sec,60)
    return f'{h}:{m:02}:{s:02}.{sub:02}' if ass else f'{h:02}:{m:02}:{s:02},{sub:03}'

def validate_cue(c):
    if not math.isfinite(c.start) or not math.isfinite(c.end) or c.start < 0 or c.end <= c.start:
        raise ValueError('Phụ đề phải có kết thúc sau bắt đầu, không dùng thời gian âm.')

def parse_srt(text):
    lines=text.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n').split('\n')
    cues=[]; i=0
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        if lines[i].strip().isdigit(): i+=1
        if i>=len(lines): raise ValueError('Thiếu mốc thời gian cuối SRT.')
        m=TIMING.match(lines[i])
        if not m: raise ValueError(f'SRT lỗi tại dòng {i+1}: {lines[i][:80]}')
        c=Cue(seconds(m.groups()[:4]),seconds(m.groups()[4:8]),''); i+=1; body=[]
        while i<len(lines) and lines[i].strip(): body.append(lines[i]); i+=1
        c.text='\n'.join(body); validate_cue(c); cues.append(c)
    if not cues: raise ValueError('SRT không có mốc thời gian.')
    return sorted(cues,key=lambda c:c.start)

def read_srt(path):
    b=Path(path).read_bytes()
    if b.startswith((b'\xff\xfe',b'\xfe\xff')): return parse_srt(b.decode('utf-16'))
    return parse_srt(b.decode('utf-8-sig'))

def write_srt(path,cues,speed=1):
    Path(path).write_text('\n\n'.join(f'{i+1}\n{stamp(c.start/speed)} --> {stamp(c.end/speed)}\n{c.text}' for i,c in enumerate(cues))+'\n',encoding='utf-8-sig')

def plain(s):
    import html
    return html.unescape(re.sub(r'</?(?:b|i|u|font)(?:\s[^>]*)?>','',s,flags=re.I)).strip()

def binary(name):
    local=ROOT/'tools'/(name+'.exe' if os.name=='nt' else name)
    found=str(local) if local.is_file() else shutil.which(name)
    if not found: raise RuntimeError(f'Không tìm thấy {name}. Thêm FFmpeg vào PATH hoặc đặt ffmpeg.exe và ffprobe.exe vào thư mục tools.')
    return found

def run(args,cancel=None,cwd=None,progress=None,total=0,capture=False):
    """No shell. Drain output continuously; polling remains cancellable during silence."""
    import queue
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    proc=subprocess.Popen([str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',errors='replace',cwd=cwd,creationflags=flags)
    q=queue.Queue(); tail=[]
    def read():
        for line in proc.stdout: q.put(line)
        q.put(None)
    reader=threading.Thread(target=read,daemon=True);reader.start()
    try:
        while True:
            if cancel and cancel.is_set(): raise InterruptedError('Đã hủy. Dữ liệu đã tạo vẫn được giữ để tiếp tục.')
            try: line=q.get(timeout=.1)
            except queue.Empty: continue
            if line is None: break
            tail.append(line)
            if len(tail)>100 and not capture: tail.pop(0)
            if progress and total and line.startswith('out_time_us='):
                try: progress(min(99,100*int(line.split('=')[1])/1e6/total))
                except ValueError: pass
        code=proc.wait()
        if code: raise RuntimeError('Lệnh xử lý thất bại:\n'+''.join(tail)[-5000:])
        return ''.join(tail)
    finally:
        if proc.poll() is None: proc.kill();proc.wait()
        reader.join(timeout=2);proc.stdout.close()

def probe(path):
    data=json.loads(run([binary('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',path],capture=True))
    v=next((x for x in data['streams'] if x['codec_type']=='video'),None)
    duration=float(data.get('format',{}).get('duration') or next((x.get('duration') for x in data['streams'] if x.get('duration')),0))
    if duration<=0: raise ValueError('Không đọc được thời lượng tệp.')
    width,height=(int(v['width']),int(v['height'])) if v else (0,0)
    if v:
        rotation=float(v.get('tags',{}).get('rotate',0))
        for d in v.get('side_data_list',[]): rotation=float(d.get('rotation',rotation))
        if round(rotation)%180: width,height=height,width
    return dict(duration=duration,width=width,height=height,has_audio=any(x['codec_type']=='audio' for x in data['streams']),video_codec=v.get('codec_name','') if v else '')

def atempo(speed):
    if speed<=0: raise ValueError('Tốc độ phải lớn hơn 0.')
    parts=[]
    while speed>2: parts.append('atempo=2');speed/=2
    while speed<.5: parts.append('atempo=0.5');speed/=.5
    parts.append(f'atempo={speed:.9f}')
    return ','.join(parts)

def ass_color(color):
    if not re.fullmatch(r'#[a-fA-F0-9]{6}',color): raise ValueError('Màu không hợp lệ.')
    return '&H00'+color[5:7]+color[3:5]+color[1:3]

def ass_text(text):
    # ASS overrides must never execute supplied SRT text.
    return plain(text).replace('\\','\\\u200b').replace('{','｛').replace('}','｝').replace('\n',r'\N')

def write_ass(path,p):
    st=p.style; w,h=p.width,p.height
    # Font size is specified on a 1080-high canvas, proportional for other resolutions.
    scale=h/1080
    margin=max(0,round(w*(100-st['width'])/200))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st['font'].replace(',', '')},{st['size']*scale:.3f},{ass_color(st['color'])},&H000000FF,&H00000000,&H80000000,{-1 if st['bold'] else 0},0,0,0,100,100,0,0,{3 if st['box'] else 1},{st['outline']*scale:.3f},{st['shadow']*scale:.3f},2,{margin},{margin},10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    for c in p.cues:
        if not plain(c.text): continue
        text=ass_text(c.text)
        events.append(f'Dialogue: 0,{stamp(c.start,True)},{stamp(c.end,True)},Default,,0,0,0,,{{\\pos({w*st["x"]/100:.2f},{h*st["y"]/100:.2f})}}{text}')
    for r in p.screen_regions:
        if not r.get('enabled',True) or not plain(r['text']):continue
        x,y,rw,rh=region_pixels(p,r);cx=x+rw/2;cy=y+rh/2
        tags=(r'\an5\q0'+f'\\pos({cx:.2f},{cy:.2f})'+f'\\fs{r["size"]*scale:.2f}'+f'\\bord{3*scale:.3f}\\shad{scale:.3f}\\b1'+r'\1c'+ass_color(r['color']))
        events.append(f'Dialogue: 1,{stamp(r["start"],True)},{stamp(r["end"],True)},Default,,{x},{max(0,w-x-rw)},0,,{{{tags}}}{ass_text(r["text"])}')
    Path(path).write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')

def video_filter(p,ass_name='subtitles.ass'):
    regions=[]
    if p.mask['enabled']:regions.append(dict(p.mask,start=0,end=p.duration,strength=20))
    regions.extend(dict(r,fill='#171717') for r in p.screen_regions if r.get('enabled',True) and r['mode']!='none')
    filters=[];source='[0:v]'
    for i,r in enumerate(regions):
        x,y,w,h=region_pixels(p,r);out=f'[mask{i}]'
        enable=f"gte(t,{r['start']:.6f})*lt(t,{r['end']:.6f})"
        if r['mode']=='blur':
            radius=max(1,min(int(r.get('strength',20)),w//4,h//4))
            filters.append(f"{source}split[base{i}][crop{i}];[crop{i}]crop={w}:{h}:{x}:{y},boxblur={radius}:2[patch{i}];[base{i}][patch{i}]overlay={x}:{y}:enable='{enable}'{out}")
        else:
            color=r.get('fill',r.get('color','#171717'));ass_color(color)
            filters.append(f"{source}drawbox=x={x}:y={y}:w={w}:h={h}:color={color}@{r.get('opacity',1)}:t=fill:enable='{enable}'{out}")
        source=out
    filters.append(source+f"subtitles=filename='{ass_name}',setpts=(PTS-STARTPTS)/{p.speed:.9f},pad=ceil(iw/2)*2:ceil(ih/2)*2[v]")
    return ';'.join(filters)


def raw_key(c,p):
    value=[plain(c.text),c.voice or p.voice,p.tts_rate+c.tts_rate]
    return hashlib.sha256(json.dumps(value,ensure_ascii=False).encode()).hexdigest()[:24]

def signature(p):
    return hashlib.sha256(json.dumps([p.duration,p.work_speed,p.max_fit,[[c.id,c.start,c.end,raw_key(c,p)] for c in p.cues]],sort_keys=True).encode()).hexdigest()

def load_manifest(cache):
    try: return json.loads((Path(cache)/'voices.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

def atomic_json(path,data):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def voice_ready(p,cache):
    m=load_manifest(cache)
    if m.get('signature')!=signature(p) or not voice_track_path(cache).is_file():return False
    missing=set(m.get('missing',[]))
    # A single-cue preview or a cancelled batch may have filled a formerly missing cue.
    return not any(c.id in missing and (Path(cache)/(raw_key(c,p)+'.mp3')).is_file() for c in p.cues)

class TTSCooldown:
    def __init__(self):self.lock=threading.Lock();self.until=0.;self.failures=0
    def fail(self):
        with self.lock:
            self.failures+=1;delay=min(60,5*2**min(4,self.failures-1))
            self.until=max(self.until,time.monotonic()+delay)
        return delay
    def success(self):
        with self.lock:self.failures=0
    def wait(self,cancel):
        while True:
            if cancel.is_set():raise InterruptedError('Đã hủy trong lúc chờ dịch vụ voice.')
            with self.lock:remaining=self.until-time.monotonic()
            if remaining<=0:return
            cancel.wait(min(.2,remaining))

_tts_context=threading.local()

async def fetch_voice(text,voice,rate,path,cancel):
    import edge_tts
    last=None;gate=getattr(_tts_context,"gate",None) or TTSCooldown()
    for attempt in range(3):
        gate.wait(cancel)
        if cancel.is_set(): raise InterruptedError('Đã hủy tạo giọng.')
        task=asyncio.create_task(edge_tts.Communicate(text,voice,rate=f'{rate:+d}%').save(str(path)))
        try:
            began=time.monotonic()
            while not task.done():
                if cancel.is_set(): raise InterruptedError('Đã hủy tạo giọng.')
                if time.monotonic()-began>90: raise TimeoutError('Edge TTS phản hồi quá lâu.')
                await asyncio.sleep(.15)
            await task
            gate.success();return
        except (Exception,asyncio.CancelledError) as e:
            task.cancel()
            try: await task
            except (Exception,asyncio.CancelledError): pass
            if isinstance(e,InterruptedError): raise
            last=e
            delay=gate.fail()
            report=getattr(_tts_context,'report',None)
            if report:report(f'Voice lỗi; nghỉ ít nhất {delay}s trước khi thử lại ({attempt+1}/3).')
    raise RuntimeError(f'Edge TTS không tạo được giọng sau 3 lần thử: {last}')

def fit_voice(raw,out,slot,cancel):
    duration=probe(raw)['duration'];factor=max(1,duration/slot)
    run([binary('ffmpeg'),'-y','-v','error','-i',raw,'-af',atempo(factor)+f',apad,atrim=duration={slot:.6f}',
        '-ar',str(RATE),'-ac','1','-c:a','pcm_s16le',out],cancel)
    return duration,factor

def mix_track(entries,duration,out,cancel,progress=lambda x:None):
    import numpy as np
    out=Path(out);tmp=out.with_suffix('.partial.wav'); total=round(duration*RATE)
    if total*2>4_200_000_000: raise ValueError('Voice vượt dung lượng WAV 4 GB. Hãy chia dự án thành các phần ngắn hơn.')
    events=sorted(entries,key=lambda e:e['start']);idx=0;active=[]
    try:
        with wave.open(str(tmp),'wb') as target:
            target.setparams((1,2,RATE,0,'NONE','not compressed'))
            for pos in range(0,total,RATE*10):
                if cancel.is_set(): raise InterruptedError('Đã hủy ghép voice.')
                end=min(total,pos+RATE*10); block=np.zeros(end-pos,dtype=np.int32)
                while idx<len(events) and round(events[idx]['start']*RATE)<end:
                    active.append(events[idx]);idx+=1
                active=[e for e in active if round(e['end']*RATE)>pos]
                for e in active:
                    start=round(e['start']*RATE)
                    with wave.open(str(e['path']),'rb') as src:
                        begin=max(pos,start);finish=min(end,start+src.getnframes())
                        if finish<=begin: continue
                        src.setpos(begin-start)
                        samples=np.frombuffer(src.readframes(finish-begin),dtype='<i2').astype(np.int32)
                        block[begin-pos:begin-pos+len(samples)]+=samples
                target.writeframes(np.clip(block,-32768,32767).astype('<i2').tobytes())
                progress(100*end/total)
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)

def mix_track_cached(entries,duration,out,cache,cancel,progress=lambda n:None):
    cache=Path(cache)/'mix-blocks';cache.mkdir(exist_ok=True)
    total=round(duration*RATE);block_frames=30*RATE
    if total*2>4_200_000_000:raise ValueError('Voice vượt giới hạn WAV 4 GB.')
    buckets={}
    for e in entries:
        lo=max(0,math.floor(e['start']*RATE/block_frames));hi=min(math.ceil(total/block_frames),math.ceil(e['end']*RATE/block_frames))
        for index in range(lo,hi):buckets.setdefault(index,[]).append(e)
    out=Path(out);temp=out.with_suffix('.partial.wav')
    try:
        with wave.open(str(temp),'wb') as target:
            target.setparams((1,2,RATE,0,'NONE','not compressed'))
            for index,pos in enumerate(range(0,total,block_frames)):
                if cancel.is_set():raise InterruptedError('Đã hủy ghép; các đoạn đã ghép được giữ.')
                count=min(block_frames,total-pos);rows=buckets.get(index,[])
                shifted=[dict(r,start=r['start']-pos/RATE,end=r['end']-pos/RATE) for r in rows]
                fingerprint=[count,[(r['path'],r['start'],r['end'],Path(r['path']).stat().st_mtime_ns,Path(r['path']).stat().st_size) for r in shifted]]
                key=hashlib.sha256(json.dumps(fingerprint).encode()).hexdigest()[:32];block=cache/(key+'.wav')
                if not block.is_file():mix_track(shifted,count/RATE,block,cancel)
                with wave.open(str(block),'rb') as src:
                    while True:
                        if cancel.is_set():raise InterruptedError('Đã hủy ghép voice.')
                        data=src.readframes(RATE)
                        if not data:break
                        target.writeframesraw(data)
                progress(100*(pos+count)/max(1,total))
        temp.replace(out)
    finally:temp.unlink(missing_ok=True)

def cached_voice_exists(p,cache):
    cache=Path(cache)
    return any((cache/(raw_key(c,p)+'.mp3')).is_file() for c in p.cues if plain(c.text))

def voice_complete(p,cache):
    m=load_manifest(cache)
    return voice_ready(p,cache) and m.get('complete',True)

def prepare_voice_row(c,p,cache,cancel,known_duration=None):
    cache=Path(cache);key=raw_key(c,p);raw=cache/(key+'.mp3')
    if not raw.is_file():return None
    dur=known_duration if known_duration is not None else probe(raw)['duration'];slot=(c.end-c.start)/p.work_speed
    required=max(1,dur/slot);applied=min(required,p.max_fit)
    # Overlong speech remains audible in review, including its spill past the subtitle.
    length=max(slot,dur/applied);ok=required<=p.max_fit+.0001
    fitkey=hashlib.sha256(f'partial-v2|{key}|{length:.9f}|{applied:.9f}'.encode()).hexdigest()[:24]
    fitted=cache/(fitkey+'.wav')
    oldfit=cache/(hashlib.sha256(f'{key}|{slot:.9f}'.encode()).hexdigest()[:24]+'.wav')
    if ok and oldfit.is_file() and oldfit.stat().st_mtime_ns>=raw.stat().st_mtime_ns:fitted=oldfit
    if fitted.is_file() and fitted.stat().st_mtime_ns<raw.stat().st_mtime_ns:
        fitted=cache/(hashlib.sha256((fitkey+str(raw.stat().st_mtime_ns)).encode()).hexdigest()[:24]+'.wav')
    if not fitted.is_file():
        temp=fitted.with_suffix('.partial.wav')
        try:
            run([binary('ffmpeg'),'-y','-v','error','-i',raw,'-af',atempo(applied)+f',apad,atrim=duration={length:.9f}',
                 '-ar',str(RATE),'-ac','1','-c:a','pcm_s16le',temp],cancel)
            temp.replace(fitted)
        finally:temp.unlink(missing_ok=True)
    return dict(id=c.id,start=c.start/p.work_speed,end=c.start/p.work_speed+length,
        cue_end=c.end/p.work_speed,raw=str(raw),path=str(fitted),duration=dur,factor=required,
        applied=applied,ok=ok,spill=max(0,length-slot))

def rebuild_voice_track(p,cache,cancel,report,segment=None,include_overlap=False):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    spoken=[c for c in p.cues if plain(c.text) and (segment is None or (c.start<segment[1] and (c.end>segment[0] if include_overlap else c.start>=segment[0])))];rows=[];missing=[];errors=[]
    old=load_manifest(cache)
    known={Path(r['raw']).name:r['duration'] for r in old.get('rows',[]) if r.get('duration',0)>0 and r.get('raw')}
    metadata_path=cache/'audio-metadata.json'
    try:metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):metadata={}
    for i,c in enumerate(spoken):
        if cancel.is_set():raise InterruptedError('Đã hủy ghép. MP3 đã tạo vẫn được giữ.')
        report(65*i/max(1,len(spoken)),f'Ghép voice đã có: {i+1}/{len(spoken)}')
        try:
            raw=cache/(raw_key(c,p)+'.mp3');duration=None
            if raw.exists():
                stat=raw.stat();item=metadata.get(raw.name,{})
                if item.get('size')==stat.st_size and item.get('mtime')==stat.st_mtime_ns:duration=item.get('duration')
                elif raw.name in known:duration=known[raw.name]
                if duration is None:duration=probe(raw)['duration']
                metadata[raw.name]=dict(size=stat.st_size,mtime=stat.st_mtime_ns,duration=duration)
            row=prepare_voice_row(c,p,cache,cancel,duration)
        except InterruptedError:raise
        except Exception as e:row=None;errors.append(dict(id=c.id,error=str(e)))
        if row:rows.append(row)
        else:missing.append(c.id)
    atomic_json(metadata_path,metadata)
    if not rows and segment is None:raise ValueError('Chưa có MP3 phù hợp với nội dung/giọng hiện tại. Chọn vùng rồi tạo voice trước.')
    start,end=segment if segment is not None else (0,p.duration)
    offset=start/p.work_speed
    total=max(end/p.work_speed,max((r['end'] for r in rows),default=0))-offset
    sig=batch_signature(p,segment) if segment is not None else signature(p)
    if include_overlap:sig=hashlib.sha256((sig+'review'+signature(p)).encode()).hexdigest()
    track=cache/(('batch-voice-' if segment is not None else 'voice-')+sig[:20]+'.wav')
    shifted=[dict(r,start=r['start']-offset,end=r['end']-offset) for r in rows]
    if segment is None:
        mix_track_cached(shifted,total,track,cache,cancel,lambda n:report(65+n*.35,'Cập nhật âm thanh timeline · dùng lại đoạn không đổi…'))
    else:mix_track(shifted,total,track,cancel,lambda n:report(65+n*.35,'Ghép voice vùng đang chọn…'))
    bad=sum(not r['ok'] for r in rows)
    manifest=dict(signature=sig,schema=2,track=str(track),rows=rows,missing=missing,errors=errors,
        complete=not missing and not bad,created=time.time(),duration=total,segment=segment,
        long_count=bad,missing_count=len(missing),tail=max(0,total-(end-start)/p.work_speed))
    if not include_overlap:atomic_json(batch_manifest_path(cache,segment) if segment is not None else cache/'voices.json',manifest)
    report(100,f'Nghe được {len(rows)}/{len(spoken)} câu · {bad} câu tràn mốc · {len(missing)} câu chưa có voice')
    return manifest

def voice_track_path(cache):
    m=load_manifest(cache)
    return Path(m.get('track') or Path(cache)/'voice.wav')

def generate_voices(p,cache,cancel,report,only_id=None,only_ids=None,segment=None,mix=True,parallel_segments=None):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    chosen=set(only_ids) if only_ids is not None else None
    spoken=[c for c in p.cues if plain(c.text) and (not only_id or c.id==only_id) and (chosen is None or c.id in chosen)]
    if only_ids is not None:
        order={id:i for i,id in enumerate(only_ids)};spoken.sort(key=lambda c:order[c.id])
    if not spoken:raise ValueError('Vùng chọn không có câu cần đọc.')
    from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
    gate=TTSCooldown()
    errors=[];unique={raw_key(c,p):c for c in spoken};pending=[];done=0;total=len(unique);began=time.monotonic()
    for key,c in unique.items():
        if (cache/(key+'.mp3')).is_file() and (cache/(key+'.mp3')).stat().st_size>0:done+=1
        else:pending.append((key,c))
    report(65*done/max(1,total),f'Dùng lại {done}/{total} MP3 · Tạo tối đa {min(24,p.tts_workers*len(parallel_segments)) if parallel_segments else p.tts_workers} câu cùng lúc')
    def fetch_one(pair):
        key,c=pair;raw=cache/(key+'.mp3');temp=raw.with_suffix('.partial.mp3')
        try:
            if cancel.is_set():raise InterruptedError('Đã hủy tạo giọng.')
            _tts_context.gate=gate;_tts_context.report=lambda msg:report(65*done/max(1,total),msg)
            gate.wait(cancel)
            asyncio.run(fetch_voice(plain(c.text),c.voice or p.voice,p.tts_rate+c.tts_rate,temp,cancel))
            probe(temp);temp.replace(raw)
            return c.id,None
        except InterruptedError:raise
        except Exception as e:return c.id,str(e)
        finally:temp.unlink(missing_ok=True)
    # Shared collector: workers never mutate manifests. Refill each freed slot immediately.
    from collections import deque
    segments=parallel_segments or [(float('-inf'),float('inf'))]
    queues=[deque() for _ in segments];active=[0]*len(segments)
    for pair in pending:
        group=next((i for i,(a,b) in enumerate(segments) if a<=pair[1].start<b),0)
        queues[group].append(pair)
    limit=max(1,min(6,p.tts_workers));capacity=min(24,limit*len(segments));cursor=0
    with ThreadPoolExecutor(max_workers=capacity) as pool:
        futures={}
        while any(queues) or futures:
            if cancel.is_set():
                for f in futures:f.cancel()
                raise InterruptedError('Đã hủy; voice đã tạo được giữ.')
            while len(futures)<capacity:
                group=next(((cursor+j)%len(queues) for j in range(len(queues)) if queues[(cursor+j)%len(queues)] and active[(cursor+j)%len(queues)]<limit),None)
                if group is None:break
                futures[pool.submit(fetch_one,queues[group].popleft())]=group;active[group]+=1;cursor=(group+1)%len(queues)
            finished,_=wait(futures,return_when=FIRST_COMPLETED)
            for future in finished:
                active[futures.pop(future)]-=1
                id,error=future.result();done+=1
                if error:
                    if only_id:raise RuntimeError(error)
                    errors.append(dict(id=id,error=error))
                elapsed=round(time.monotonic()-began)
                report(65*done/max(1,total),f'Voice {done}/{total} · {elapsed}s · {len(errors)} lỗi'+(' · '+error[:65] if error else ''))
    if only_id:
        row=prepare_voice_row(spoken[0],p,cache,cancel)
        if row:
            error_path=cache/'voice-errors.json'
            try:stored=json.loads(error_path.read_text(encoding='utf-8'))
            except (OSError,ValueError):stored={}
            stored.pop(only_id,None);atomic_json(error_path,stored)
        return dict(sample=row)
    if not mix:
        metadata_path=cache/'audio-metadata.json'
        try:metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):metadata={}
        rows=[]
        for i,c in enumerate(spoken):
            if cancel.is_set():raise InterruptedError('Đã hủy; MP3 đã tạo được giữ lại.')
            raw=cache/(raw_key(c,p)+'.mp3')
            if not raw.is_file() or not raw.stat().st_size:continue
            try:
                stat=raw.stat();item=metadata.get(raw.name,{})
                dur=item.get('duration') if item.get('size')==stat.st_size and item.get('mtime')==stat.st_mtime_ns else None
                row=prepare_voice_row(c,p,cache,cancel,dur)
                if row:
                    rows.append(row);metadata[raw.name]=dict(size=stat.st_size,mtime=stat.st_mtime_ns,duration=row['duration'])
            except InterruptedError:raise
            except Exception as e:errors.append(dict(id=c.id,error=str(e)))
            report(65+35*(i+1)/len(spoken),f'Chuẩn bị câu {i+1}/{len(spoken)}')
        atomic_json(metadata_path,metadata)
        error_path=cache/'voice-errors.json'
        try:stored=json.loads(error_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):stored={}
        for c in spoken:stored.pop(c.id,None)
        by_id={c.id:c for c in spoken}
        for item in errors:
            c=by_id.get(item['id'])
            if c:stored[c.id]=dict(key=raw_key(c,p),error=item['error'])
        atomic_json(error_path,stored)
        return dict(rows=rows,tts_errors=errors,generated_only=True,attempted_ids=[c.id for c in spoken],missing_count=len(spoken)-len(rows),long_count=sum(not r['ok'] for r in rows))
    result=rebuild_voice_track(p,cache,cancel,lambda n,msg:report(65+.35*n,msg),segment=segment)
    result['tts_errors']=errors
    atomic_json(batch_manifest_path(cache,segment) if segment is not None else cache/'voices.json',result)
    return result


def check_project(p):
    if not p.video or not Path(p.video).is_file(): raise ValueError('Hãy chọn video đang tồn tại.')
    if not p.cues and not p.screen_regions and not p.music_clean.get('enabled'): raise ValueError('Hãy nhập SRT hoặc thêm vùng chữ / làm mờ trước.')
    for r in p.screen_regions:validate_screen_region(r,p.duration)
    for c in p.cues:
        validate_cue(c)
        if c.end>p.duration+.1: raise ValueError(f'Phụ đề {stamp(c.end)} vượt thời lượng video. Kiểm tra đúng video và SRT.')

def export_video(p,cache,out,cancel,report,with_voice=True,preview=None,allow_partial=False,segment=None,review_voice=None):
    check_project(p)
    local_voice=(review_voice or batch_manifest(p,cache,segment)) if with_voice and segment is not None else {}
    if with_voice and not local_voice and not voice_ready(p,cache): raise ValueError('Voice cần ghép lại theo chỉnh sửa hiện tại. Bấm Ghép voice đã có.')
    if with_voice and not allow_partial and not (local_voice.get('complete') if local_voice else voice_complete(p,cache)):raise ValueError('Voice có câu tràn mốc hoặc còn thiếu; cần chọn xuất bản đang có hoặc sửa trước.')
    out=Path(out)
    if Path(p.video).resolve()==out.resolve(): raise ValueError('Không được ghi đè video nguồn.')
    if out.exists(): raise ValueError('Tên tệp đã tồn tại. Hãy chọn tên mới để giữ bản cũ.')
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    job=cache/('render-'+uuid.uuid4().hex[:10]);job.mkdir()
    write_ass(job/'subtitles.ass',p)
    partial=out.with_name(out.stem+'.partial'+out.suffix)
    graph=video_filter(p)
    args=[binary('ffmpeg'),'-y','-nostdin']
    duration=p.output_duration
    if segment is not None:
        a,b=segment
        if not 0<=a<b<=p.duration+.001:raise ValueError('Vùng xuất nằm ngoài video.')
        preview=a/p.speed
    if preview is not None:
        start=max(0,min(preview,duration-.1));duration=min((segment[1]-segment[0])/p.speed if segment else 10,duration-start)
        source_start=start*p.speed
        args+=['-ss',f'{source_start:.6f}']
        graph=f'[0:v]setpts=PTS+{source_start:.6f}/TB[vshift];'+graph.replace('[0:v]','[vshift]')
    args+=['-i',p.video]
    if with_voice:
        if preview is not None: args+=['-ss',f'{max(0,source_start-(segment[0] if local_voice else 0))/p.work_speed:.6f}']
        args+=['-i',str(local_voice['track'] if local_voice else voice_track_path(cache))]
    audios=[];source_audio='0:a'
    clean=clean_audio_path(p)
    if clean:
        if preview is not None:args+=['-ss',f'{source_start:.6f}']
        source_audio=f'{2 if with_voice else 1}:a';args+=['-i',str(clean)]
    if p.has_audio and p.original_volume>0:
        graph+=f';[{source_audio}]asetpts=PTS-STARTPTS,{atempo(p.speed)},volume={p.original_volume},apad,atrim=duration={duration:.6f}[original]';audios.append('[original]')
    if with_voice:
        graph+=f';[1:a]asetpts=PTS-STARTPTS,{atempo(p.final_speed)},volume={p.voice_volume},apad,atrim=duration={duration:.6f}[voice]';audios.append('[voice]')
    if audios: graph+=';'+''.join(audios)+f'amix=inputs={len(audios)}:duration=longest:normalize=0,alimiter=limit=0.97:level=false:latency=true[a]'
    (job/'filters.txt').write_text(graph,encoding='utf-8')
    args+=['-filter_complex_script','filters.txt','-map','[v]']
    if audios: args+=['-map','[a]','-c:a','aac','-b:a','192k']
    else: args+=['-an']
    args+=['-t',f'{duration:.6f}','-c:v','libx264','-preset','ultrafast' if preview is not None else p.export_preset,
        '-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-progress','pipe:1','-nostats',str(partial)]
    try:
        began=time.monotonic()
        def export_progress(percent):
            elapsed=time.monotonic()-began
            eta=elapsed*(100-percent)/percent if percent>0 else 0
            report(percent,f'Xuất {percent:.1f}% · Đã chạy {stamp(elapsed)} · Còn khoảng {stamp(eta)}')
        report(0,'Đang xuất video · '+p.export_preset)
        run(args,cancel,cwd=job,progress=export_progress,total=duration)
        if out.exists(): raise ValueError('Tệp đích vừa được tạo bởi tiến trình khác; không ghi đè.')
        partial.replace(out);report(100,'Đã xuất video.');return str(out)
    finally:
        partial.unlink(missing_ok=True);shutil.rmtree(job,ignore_errors=True)

def preview_follow_rate(base, error_ms):
    """Audio is the preview clock. Gently move video; never seek the speech stream."""
    if abs(error_ms)<=160:return base
    return base*(1+max(-.025,min(.025,error_ms/1000*.04)))

def plan_overflow(p,rows,only_ids=None,target_rate=1.25,max_extension=2.0,gap=.08):
    """Suggest end-time extensions into actual silence; starts/text remain unchanged."""
    by_id={r['id']:r for r in rows};spoken=sorted([c for c in p.cues if plain(c.text)],key=lambda c:c.start)
    chosen=set(only_ids) if only_ids is not None else None
    if not 1<=target_rate<=3 or not 0<=max_extension<=10 or not 0<=gap<=1:raise ValueError('Thông số nới mốc không hợp lệ.')
    target_rate=min(target_rate,p.max_fit)
    changes=[];long_count=0;missing=0;remaining=0
    for i,c in enumerate(spoken):
        if chosen is not None and c.id not in chosen:continue
        row=by_id.get(c.id)
        if not row or Path(row.get('raw','')).stem!=raw_key(c,p):missing+=1;continue
        dur=float(row['duration']);factor=dur/((c.end-c.start)/p.work_speed)
        if factor<=p.max_fit+.0001:continue
        long_count+=1
        boundary=min(p.duration,spoken[i+1].start-gap if i+1<len(spoken) else p.duration)
        wanted=math.ceil((c.start+dur/target_rate*p.work_speed)*1000)/1000
        limit=min(boundary,c.end+max_extension)
        new_end=max(c.end,min(wanted,math.floor(limit*1000)/1000))
        new_factor=dur/((new_end-c.start)/p.work_speed);solved=new_factor<=p.max_fit+.0001
        if not solved:remaining+=1
        if new_end>c.end+.0005:
            changes.append(dict(id=c.id,text=c.text,start=c.start,old_end=c.end,new_end=new_end,
                before=factor,after=new_factor,resolved=solved))
    return dict(changes=changes,long_count=long_count,remaining=remaining,solved=long_count-remaining,missing=missing)


def project_filename(video):
    stem=Path(video).stem if video else 'Du-an'
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem).strip(' .')[:120].rstrip(' .') or 'Du-an'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',stem):stem='Video-'+stem
    return stem+'.ha.json'

def software_decode_args(video_codec):
    args=['-hwaccel','none']
    if video_codec=='av1':
        decoders=run([binary('ffmpeg'),'-hide_banner','-decoders'],capture=True)
        decoder=next((name for name in ['libdav1d','libaom-av1'] if name in decoders),None)
        if not decoder:raise RuntimeError('FFmpeg trên máy chưa có bộ giải mã AV1 bằng CPU (libdav1d/libaom-av1). Cần bản FFmpeg có một trong hai bộ giải mã này để phát AV1 bằng CPU.')
        args+=['-c:v',decoder]
    return args


def keep_voice_batch(p,segment):
    """Preserve existing boundaries; add only uncovered parts of this completed range."""
    a,b=map(float,segment);a=max(0,a);b=min(p.duration,b)
    if a>=b:return False
    additions=[];cursor=a
    for lo,hi in p.voice_batch_kept:
        if hi<=cursor:continue
        if lo>=b:break
        if lo>cursor:additions.append([cursor,min(lo,b)])
        cursor=max(cursor,hi)
    if cursor<b:additions.append([cursor,b])
    if not additions:return False
    p.voice_batch_kept=sorted(p.voice_batch_kept+additions)
    return True


def recover_voice_batches(p,cache):
    """Recover completed old-version batches only when their current content matches."""
    changed=False
    for path in sorted(Path(cache).glob('batch-*-*.json'),key=lambda f:f.stat().st_mtime):
        try:
            data=json.loads(path.read_text(encoding='utf-8'));segment=data.get('segment')
            if not segment or len(segment)!=2 or data.get('missing_count',1):continue
            if batch_manifest(p,cache,segment):changed=keep_voice_batch(p,segment) or changed
        except (OSError,ValueError,TypeError,KeyError):continue
    return changed


def voice_batches(p, minutes=None):
    """Keep completed ranges and split each remaining gap from its own beginning."""
    import bisect
    size=max(1,min(120,int(p.voice_batch_minutes if minutes is None else minutes)))*60
    result=[];cursor=0.
    def gap(end):
        nonlocal cursor
        while cursor<end:
            nxt=min(end,cursor+size);result.append(dict(start=cursor,end=nxt,ids=[],kept=False));cursor=nxt
    for a,b in p.voice_batch_kept:
        a=max(0.,float(a));b=min(p.duration,float(b))
        if a>=p.duration:break
        gap(a)
        if b>cursor:result.append(dict(start=cursor,end=b,ids=[],kept=True));cursor=b
    gap(p.duration)
    starts=[r['start'] for r in result]
    for cue in p.cues:
        if plain(cue.text) and 0<=cue.start<p.duration:
            result[bisect.bisect_right(starts,cue.start)-1]['ids'].append(cue.id)
    return result


def batch_signature(p,segment):
    a,b=segment
    content=[p.video,a,b,p.work_speed,p.max_fit,[[c.id,c.start,c.end,raw_key(c,p)] for c in p.cues if a<=c.start<b and plain(c.text)]]
    return hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()

def batch_manifest_path(cache,segment):
    return Path(cache)/f'batch-{round(segment[0]*1000)}-{round(segment[1]*1000)}.json'

def batch_manifest(p,cache,segment):
    try:m=json.loads(batch_manifest_path(cache,segment).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
    if m.get('signature')!=batch_signature(p,segment) or not Path(m.get('track','')).is_file():return {}
    missing=set(m.get('missing',[]))
    if any(c.id in missing and (Path(cache)/(raw_key(c,p)+'.mp3')).is_file() for c in p.cues):return {}
    return m

def batch_preview_path(p,cache,start,end):
    stat=Path(p.video).stat()
    key=hashlib.sha256(json.dumps([p.video,stat.st_size,stat.st_mtime_ns,start,end,'360p24-v1']).encode()).hexdigest()[:24]
    return Path(cache)/('batch-preview-'+key+'.mp4')

def prepare_batch_preview(p,cache,start,end,cancel,report):
    target=batch_preview_path(p,cache,start,end)
    if target.is_file():report(100,'Dùng lại video xem nhẹ của lô');return str(target)
    tmp=target.with_suffix('.partial.mp4')
    try:
        args=[binary('ffmpeg'),'-hide_banner','-y','-nostdin','-filter_threads','1']+software_decode_args(p.video_codec)
        args+=['-threads','2','-ss',f'{start:.6f}','-i',p.video,'-t',f'{end-start:.6f}',
               '-map','0:v:0','-map','0:a:0?',
               '-vf',"fps=24,scale=w='min(640,iw)':h='min(360,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
               '-c:v','libx264','-threads','2','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p',
               '-c:a','aac','-b:a','96k','-movflags','+faststart','-progress','pipe:1','-nostats',tmp]
        run(args,cancel,progress=lambda n:report(n,'Tạo video xem nhẹ 360p cho lô — lần đầu cần chờ'),total=end-start)
        tmp.replace(target);return str(target)
    finally:tmp.unlink(missing_ok=True)


def timeline_move(snapshot, delta, duration):
    """Clamp one shared delta so a selected group's spacing cannot change."""
    if not snapshot:return {}
    low=min(a for a,b in snapshot.values());high=max(b for a,b in snapshot.values())
    if high-low>duration:return dict(snapshot)
    delta=max(-low,min(float(delta),max(0,duration)-high))
    return {key:(round(a+delta,3),round(b+delta,3)) for key,(a,b) in snapshot.items()}

def timeline_snap(value, targets, tolerance):
    nearest=min(targets,key=lambda t:abs(t-value),default=value)
    return nearest if abs(nearest-value)<=tolerance else value


def audit_missing_voice(p,cache,only_ids=None):
    """Read-only presence check for current text/voice/rate, ignoring empty SRT cues."""
    missing=[];spoken=0;scope=set(only_ids) if only_ids is not None else None
    try:errors=json.loads((Path(cache)/'voice-errors.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):errors={}
    for c in p.cues:
        if (scope is not None and c.id not in scope) or not plain(c.text):continue
        spoken+=1;path=Path(cache)/(raw_key(c,p)+'.mp3')
        try:present=path.is_file() and path.stat().st_size>0
        except OSError:present=False
        error=errors.get(c.id,{})
        reason=error.get('error') if error.get('key')==raw_key(c,p) else None
        if not present or reason:
            category='symbols' if not any(ch.isalnum() for ch in plain(c.text)) else ('error' if reason else 'missing')
            missing.append(dict(id=c.id,start=c.start,end=c.end,text=c.text,category=category,reason=reason or 'Chưa có MP3 phù hợp hoặc file rỗng'))
    return dict(spoken=spoken,available=spoken-len(missing),missing=missing)


def interleaved_voice_ids(p,segments):
    """One shared request pool, distributed fairly across the selected ranges."""
    from itertools import zip_longest
    groups=[[c.id for c in p.cues if a<=c.start<b and plain(c.text)] for a,b in segments]
    return list(dict.fromkeys(id for group in zip_longest(*groups) for id in group if id is not None))


def remove_cached_voice(p,cache,ids=None):
    """Remove active audio only; quarantine it so video/proxy/source files stay intact."""
    cache=Path(cache);all_voice=ids is None;chosen=set(ids or [])
    keys={raw_key(c,p) for c in p.cues if all_voice or c.id in chosen}
    affected=[c.id for c in p.cues if raw_key(c,p) in keys]
    paths=[]
    for path in cache.iterdir():
        name=path.name
        raw=bool(re.fullmatch(r'[a-f0-9]{24}\.mp3',name))
        audio=bool(re.fullmatch(r'(?:[a-f0-9]{24}|voice-[a-f0-9]+|batch-voice-[a-f0-9]+)\.wav',name)) or name=='voice.wav'
        manifest=name=='voices.json' or bool(re.fullmatch(r'batch-\d+-\d+\.json',name))
        if (raw and (all_voice or path.stem in keys)) or manifest or (all_voice and (audio or name in ('mix-blocks','audio-metadata.json','voice-errors.json'))):paths.append(path)
    if not paths:return dict(affected=affected,count=0,backup=None)
    backup=cache/'voice-trash'/uuid.uuid4().hex;backup.mkdir(parents=True)
    moved=[]
    try:
        for path in paths:
            path.rename(backup/path.name);moved.append(path)
    except Exception:
        for path in reversed(moved):(backup/path.name).rename(path)
        raise
    return dict(affected=affected,count=len(paths),backup=str(backup))


def merge_srt_cues(existing,incoming):
    """Preserve absolute timestamps and existing cue identity; skip exact repeated entries."""
    result=list(existing);seen={(c.start,c.end,c.text) for c in existing};added=0
    for cue in incoming:
        key=(cue.start,cue.end,cue.text)
        if key in seen:continue
        seen.add(key);result.append(cue);added+=1
    return sorted(result,key=lambda c:c.start),added,len(incoming)-added


def inspect_srt_import(existing,files):
    """Indexed duplicate lookup and dynamic interval queries; normalize each cue once."""
    import unicodedata
    from bisect import bisect_left
    from collections import defaultdict
    all_cues=list(existing)+[c for _,cues in files for c in cues]
    starts=sorted({c.start for c in all_cues});size=1
    while size<len(starts):size*=2
    maximum=[float('-inf')]*(2*size);at=defaultdict(list)
    exact=set();times=defaultdict(list);texts=defaultdict(list);labels={};order={}
    def key(c):return unicodedata.normalize('NFC',' '.join(plain(c.text).split()))
    def timing(c):return round(c.start*1000),round(c.end*1000)
    def add(c,text):
        exact.add((*timing(c),text));times[timing(c)].append(c)
        if text:texts[text].append(c)
        order[c.id]=len(order);labels[c.id]=stamp(c.start)+' → '+stamp(c.end)+' · '+c.text
        i=bisect_left(starts,c.start);at[i].append(c);node=size+i
        maximum[node]=max(maximum[node],c.end);node//=2
        while node:
            maximum[node]=max(maximum[node*2],maximum[node*2+1]);node//=2
    def overlaps(c):
        stop=bisect_left(starts,c.end);found={x.id:x for x in times.get(timing(c),())}
        stack=[(1,0,size)]
        while stack:
            node,left,right=stack.pop()
            if left>=stop or maximum[node]<=c.start:continue
            if right-left==1:
                for x in at[left]:
                    if min(x.end,c.end)>max(x.start,c.start):found[x.id]=x
            else:
                mid=(left+right)//2;stack.append((node*2,left,mid));stack.append((node*2+1,mid,right))
        return sorted(found.values(),key=lambda x:order[x.id])
    for c in existing:add(c,key(c))
    rows=[];summaries=[]
    for name,cues in files:
        counts=dict(duplicate=0,overlap=0,repeated=0,new=0)
        for cue in cues:
            text=key(cue);duplicate=(*timing(cue),text) in exact
            overlap=[] if duplicate else overlaps(cue)
            repeated=texts.get(text,()) if text else ()
            kind='duplicate' if duplicate else ('overlap' if overlap else ('repeated' if repeated else 'new'))
            matches=overlap or repeated
            # Repeated dialogue may occur thousands of times; bound display text, not detection.
            details='\n'.join(labels[c.id] for c in matches[:10]) if not duplicate else ''
            if not duplicate and len(matches)>10:details+=f'\n… và {len(matches)-10} câu khác.'
            rows.append(dict(cue=cue,file=name,kind=kind,targets=[c.id for c in overlap],old_text=details))
            counts[kind]+=1
            if not duplicate:add(cue,text)
        summaries.append(dict(file=name,total=len(cues),**counts))
    return dict(rows=rows,files=summaries)


def apply_srt_import(existing,report,choices=None):
    choices=choices or {};result=list(existing)
    for row in report['rows']:
        cue=row['cue'];kind=row['kind']
        action=choices.get(cue.id,'skip' if kind in ('duplicate','overlap') else 'keep')
        if kind=='duplicate' or action=='skip':continue
        if action=='replace':result=[c for c in result if c.id not in row['targets']]
        result.append(cue)
    return sorted(result,key=lambda c:c.start)


def region_pixels(p,r):
    x=max(0,min(p.width-2,round(r['x']*p.width/100)))//2*2
    y=max(0,min(p.height-2,round(r['y']*p.height/100)))//2*2
    w=max(2,min(p.width-x,round(r['w']*p.width/100)))//2*2
    h=max(2,min(p.height-y,round(r['h']*p.height/100)))//2*2
    return x,y,w,h


def validate_screen_region(r,duration):
    for key in ('start','end','x','y','w','h','size','strength'):
        if not isinstance(r.get(key),(int,float)) or not math.isfinite(r[key]):raise ValueError('Thông số vùng chữ không hợp lệ.')
    if not 0<=r['start']<r['end'] or (duration and r['end']>duration+.001):raise ValueError('Thời gian vùng chữ vượt video hoặc không hợp lệ.')
    if not (0<=r['x']<100 and 0<=r['y']<100 and 0<r['w']<=100-r['x']+.001 and 0<r['h']<=100-r['y']+.001):raise ValueError('Vùng chọn nằm ngoài video.')
    if not 8<=r['size']<=200 or not 1<=r['strength']<=40:raise ValueError('Cỡ chữ / độ mờ không hợp lệ.')
    if r.get('mode') not in ('blur','solid','none'):raise ValueError('Kiểu che không hợp lệ.')
    if not isinstance(r.get('text'),str) or not isinstance(r.get('id'),str):raise ValueError('Vùng chữ không hợp lệ.')
    ass_color(r['color'])


def recognize_screen_text(path):
    try:from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:raise RuntimeError('Chưa cài OCR. Đóng app, chạy CAI-OCR.cmd trong gói cập nhật rồi mở lại. Vẫn có thể nhập chữ Việt và làm mờ thủ công.') from e
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
    result,_=engine(str(path))
    return '\n'.join(str(row[1]) for row in (result or []))


MUSIC_MODEL='UVR-MDX-NET-Inst_HQ_3.onnx'
MUSIC_ENGINE_VERSION='audio-separator-0.47.0-mdx-v1'
MUSIC_WORKER=r'''
import os,sys,json,pathlib,shutil
out,models,model,ffmpeg_dir,threads=sys.argv[1:6]
backend=sys.argv[6] if len(sys.argv)>6 else 'cpu'
os.environ['OMP_NUM_THREADS']=threads;os.environ['MKL_NUM_THREADS']=threads;os.environ['CUDA_VISIBLE_DEVICES']=''
channel=sys.stdout;sys.stdout=sys.stderr
def emit(data):channel.write(json.dumps(data,ensure_ascii=True)+'\n');channel.flush()
os.environ['PATH']=ffmpeg_dir+os.pathsep+os.environ.get('PATH','')
import torch
torch.set_num_threads(int(threads));torch.set_num_interop_threads(1)
import onnxruntime as ort
def nvidia_adapter():
    import ctypes as c,uuid
    if os.name!='nt':raise RuntimeError('DirectML cần Windows 10/11.')
    class GUID(c.Structure):_fields_=[('a',c.c_uint32),('b',c.c_uint16),('d',c.c_uint16),('e',c.c_ubyte*8)]
    class LUID(c.Structure):_fields_=[('low',c.c_uint32),('high',c.c_int32)]
    class DESC(c.Structure):
        _fields_=[('name',c.c_wchar*128),('vendor',c.c_uint32),('device',c.c_uint32),('subsystem',c.c_uint32),('revision',c.c_uint32),('video',c.c_size_t),('system',c.c_size_t),('shared',c.c_size_t),('luid',LUID),('flags',c.c_uint32)]
    def method(ptr,index,restype,*args):
        address=c.cast(ptr,c.POINTER(c.POINTER(c.c_void_p))).contents[index]
        return c.WINFUNCTYPE(restype,c.c_void_p,*args)(address)
    iid=GUID.from_buffer_copy(uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    factory=c.c_void_p();dxgi=c.WinDLL('dxgi');create=dxgi.CreateDXGIFactory1
    create.argtypes=[c.POINTER(GUID),c.POINTER(c.c_void_p)];create.restype=c.c_int32
    if create(c.byref(iid),c.byref(factory))<0:raise RuntimeError('Không đọc được danh sách GPU DXGI.')
    try:
        for index in range(16):
            adapter=c.c_void_p();hr=method(factory,12,c.c_int32,c.c_uint32,c.POINTER(c.c_void_p))(factory,index,c.byref(adapter))
            if hr<0:break
            try:
                desc=DESC()
                if method(adapter,10,c.c_int32,c.POINTER(DESC))(adapter,c.byref(desc))>=0 and desc.vendor==0x10de and not desc.flags&2:
                    return index,desc.name
            finally:method(adapter,2,c.c_uint32)(adapter)
    finally:method(factory,2,c.c_uint32)(factory)
    raise RuntimeError('Không tìm thấy GPU NVIDIA. Chọn CPU để tiếp tục.')

original=ort.InferenceSession
sessions=[];gpu_checked=False;adapter_name='CPU';adapter_index=None
if backend=='dml':
    if 'DmlExecutionProvider' not in ort.get_available_providers():raise RuntimeError('Chưa có DirectML. Chạy CAI-GPU-GTX.cmd trong bản cập nhật.')
    adapter_index,adapter_name=nvidia_adapter()
def bounded(*args,**kwargs):
    opts=kwargs.get('sess_options') or ort.SessionOptions()
    opts.intra_op_num_threads=int(threads);opts.inter_op_num_threads=1
    if backend=='dml':
        opts.enable_mem_pattern=False;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        opts.enable_profiling=True;opts.profile_file_prefix=str(pathlib.Path(out)/'gpu-profile')
        kwargs['providers']=[('DmlExecutionProvider',{'device_id':adapter_index}),'CPUExecutionProvider']
    else:kwargs['providers']=['CPUExecutionProvider']
    kwargs['sess_options']=opts
    session=original(*args,**kwargs)
    if backend=='dml':
        if 'DmlExecutionProvider' not in session.get_providers():raise RuntimeError('Không khởi tạo được GPU DirectML. Đã dừng, không chạy ngầm bằng CPU.')
        session.disable_fallback()
    sessions.append(session);return session
ort.InferenceSession=bounded
from audio_separator.separator import Separator
# A cancelled download must never be mistaken for a complete model on resume.
class AtomicSeparator(Separator):
    def load_model_data_using_hash(self,path):
        data=super().load_model_data_using_hash(path)
        # Native ONNX input size avoids an unnecessary conversion to PyTorch.
        self.arch_specific_params['MDX']['segment_size']=2**int(data['mdx_dim_t_set'])
        return data
    def download_file_if_not_exists(self,url,output_path):
        target=pathlib.Path(output_path)
        if target.is_file():return
        temporary=target.with_name(target.name+'.download')
        temporary.unlink(missing_ok=True)
        try:
            super().download_file_if_not_exists(url,str(temporary))
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
sep=AtomicSeparator(model_file_dir=models,output_dir=out,output_format='WAV',output_single_stem='Vocals',normalization_threshold=1.0,amplification_threshold=0.0,use_soundfile=True,mdx_params={'hop_length':1024,'segment_size':128,'overlap':.25,'batch_size':1,'enable_denoise':False})
sep.load_model(model_filename=model)
if backend=='dml' and not sessions:raise RuntimeError('Mô hình không tạo phiên ONNX GPU. Đã dừng để tránh chạy nhầm CPU.')
emit({'event':'ready','device':adapter_name,'backend':backend})
for line in sys.stdin:
    request=json.loads(line)
    if request.get('stop'):break
    try:
        files=sep.separate(request['source'],custom_output_names={'Vocals':'speech'})
        if len(files)!=1:raise RuntimeError('Expected one speech output')
        p=pathlib.Path(files[0]);p=p if p.is_absolute() else pathlib.Path(out)/p
        gpu_nodes=0;cpu_nodes=0
        if backend=='dml' and not gpu_checked:
            for session in sessions:
                profile=pathlib.Path(session.end_profiling())
                events=json.loads(profile.read_text(encoding='utf-8'))
                gpu_nodes+=sum(e.get('args',{}).get('provider')=='DmlExecutionProvider' for e in events)
                cpu_nodes+=sum(e.get('args',{}).get('provider')=='CPUExecutionProvider' for e in events)
                profile.unlink(missing_ok=True)
            if not gpu_nodes:raise RuntimeError('Không xác nhận được phép tính chạy bằng DirectML. Chưa áp dụng kết quả; chọn CPU hoặc gửi Nhật ký.')
            gpu_checked=True
        shutil.copyfile(p,request['target']);p.unlink(missing_ok=True)
        emit({'event':'done','device':adapter_name,'gpu_verified':gpu_checked,'gpu_nodes':gpu_nodes,'cpu_nodes':cpu_nodes})
    except Exception as e:
        emit({'event':'error','message':str(e)});break
'''


def music_python(backend='cpu'):
    configured=os.environ.get('HUYENANH_MUSIC_GPU_PYTHON' if backend=='dml' else 'HUYENANH_MUSIC_PYTHON')
    path=Path(configured) if configured else ROOT/('.music-dml-venv' if backend=='dml' else '.music-venv')/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not path.is_file() and backend=='dml':raise RuntimeError('Chưa cài GPU. Đóng app và chạy CAI-GPU-GTX.cmd một lần.')
    if not path.is_file():raise RuntimeError('Chưa cài bộ giảm nhạc. Đóng app và chạy CAI-GIAM-NHAC.cmd trong gói cập nhật một lần, rồi mở lại app.')
    return path


def music_source_key(p):
    source=Path(p.video);stat=source.stat()
    return hashlib.sha256(json.dumps([str(source.resolve()),stat.st_size,stat.st_mtime_ns,MUSIC_MODEL,MUSIC_ENGINE_VERSION],ensure_ascii=False).encode()).hexdigest()[:24]


def clean_audio_path(p):
    state=p.music_clean
    if not state.get('enabled'):return None
    if state.get('source_key')!=music_source_key(p):raise ValueError('Bản giảm nhạc không khớp video nguồn. Mở Giảm nhạc để xử lý lại hoặc dùng âm gốc.')
    path=Path(state.get('track',''))
    if not path.is_file() or not path.stat().st_size:raise ValueError('Không tìm thấy âm thanh đã giảm nhạc. Mở Giảm nhạc để ghép lại phần đã xử lý.')
    return path


def music_chunk_valid(path,duration):
    try:
        with wave.open(str(path),'rb') as f:return f.getnchannels()==2 and f.getframerate()==44100 and f.getsampwidth()==2 and abs(f.getnframes()-round(duration*44100))<=2
    except (OSError,EOFError,wave.Error):return False


class MusicSession:
    """One model per task, bounded audio chunks, cancellable JSON pipe protocol."""
    def __init__(self,models,root,threads=2,python=None,worker_code=None,backend="cpu"):
        import tempfile,queue
        self.out=Path(tempfile.mkdtemp(prefix='ai-session-',dir=root))
        self.events=queue.Queue();self.errors=tempfile.TemporaryFile();self.proc=None;self.reader=None
        try:
            self.proc=subprocess.Popen([str(python or music_python(backend)),'-u','-c',worker_code or MUSIC_WORKER,str(self.out),str(models),MUSIC_MODEL,str(Path(binary('ffmpeg')).resolve().parent),str(threads),backend],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def read():
                try:
                    for line in self.proc.stdout:
                        try:self.events.put(json.loads(line))
                        except ValueError:continue
                finally:self.events.put({'event':'exit'})
            self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        except BaseException:self.close();raise
    def wait(self,event,cancel,heartbeat=None):
        import queue
        began=time.monotonic();last=-2
        while True:
            if cancel.is_set():raise InterruptedError('Đã hủy giảm nhạc; giữ lại các đoạn đã xong.')
            elapsed=time.monotonic()-began
            if heartbeat and elapsed-last>=2:heartbeat(elapsed);last=elapsed
            try:message=self.events.get(timeout=.1)
            except queue.Empty:continue
            if message.get('event')==event:return message
            if message.get('event')=='error':raise RuntimeError('AI giảm nhạc: '+message.get('message','Lỗi không xác định'))
            if message.get('event')=='exit':
                self.errors.seek(0,2);size=self.errors.tell();self.errors.seek(max(0,size-5000))
                raise RuntimeError('Bộ AI đã dừng: '+self.errors.read().decode('utf-8',errors='replace'))
    def separate(self,source,target,cancel,heartbeat=None):
        if cancel.is_set():raise InterruptedError('Đã hủy giảm nhạc.')
        try:self.proc.stdin.write(json.dumps({'source':str(source),'target':str(target)},ensure_ascii=True)+'\n');self.proc.stdin.flush()
        except (BrokenPipeError,OSError):raise RuntimeError('Bộ AI đã ngắt; bấm xử lý tiếp để dùng lại các đoạn đã xong.')
        result=self.wait('done',cancel,heartbeat)
        if not Path(target).is_file():raise RuntimeError('AI không trả về tệp âm thanh.')
        return result
    def close(self):
        if self.proc:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
            if self.reader:self.reader.join(timeout=2)
            for stream in (self.proc.stdin,self.proc.stdout):
                if stream:
                    try:stream.close()
                    except OSError:pass
        self.errors.close();shutil.rmtree(self.out,ignore_errors=True)


def separate_music_chunk(source,target,models,cancel,python=None):
    session=MusicSession(models,Path(target).parent,python=python)
    try:session.wait('ready',cancel);session.separate(source,target,cancel)
    finally:session.close()


def build_music_reduction(p,cache,cancel,report,retain=.12,segment=None,separator=None,fresh=False):
    """30s resumable blocks with 1s context; source/video/TTS files are never rewritten."""
    if not 0<=retain<=.5:raise ValueError('Mức giữ nền phải từ 0 đến 50%.')
    if not p.has_audio:raise ValueError('Video không có âm thanh gốc.')
    start,end=segment if segment is not None else (0.,p.duration)
    if not 0<=start<end<=p.duration+.001:raise ValueError('Khoảng xử lý giảm nhạc không hợp lệ.')
    key=music_source_key(p);root=Path(cache)/'music-clean'/key;root.mkdir(parents=True,exist_ok=True)
    models=Path(cache).parent.parent/'music-models';models.mkdir(parents=True,exist_ok=True)
    if fresh:
        root=root/('test-'+uuid.uuid4().hex);root.mkdir()
    plans=[];position=start
    while position<end-.000001:
        stop=min(end,position+30);name=f'chunk-{round(position*1000)}-{round(stop*1000)}.wav';plans.append((position,stop,root/name));position=stop
    missing=[(a,b,path) for a,b,path in plans if not music_chunk_valid(path,b-a)]
    if separator is None and missing:music_python(p.music_backend)
    session=None;remaining=sum(b-a for a,b,_ in missing);processed_seconds=0;processing_time=0;ratio=None
    try:
        for i,(a,b,path) in enumerate(plans):
            if cancel.is_set():raise InterruptedError('Đã dừng giảm nhạc; các đoạn xong được giữ để chạy tiếp.')
            if music_chunk_valid(path,b-a):report(80*(i+1)/len(plans),f'Dùng lại đoạn giảm nhạc {i+1}/{len(plans)}');continue
            chunk_began=time.monotonic()
            label=f'Giảm nhạc đoạn {i+1}/{len(plans)} · {stamp(a)}–{stamp(b)}'
            def heartbeat(elapsed):
                eta=f' · Còn khoảng {stamp(max(0,remaining*ratio-(time.monotonic()-chunk_began)))} + ghép âm' if ratio is not None else ' · Đang đo tốc độ'
                report(80*i/len(plans),label+f' · Đoạn này {stamp(time.monotonic()-chunk_began)}'+eta)
            heartbeat(0)
            pad_start=max(0,a-1);pad_end=min(p.duration,b+1);source=root/'input.partial.wav';estimated=root/'estimate.partial.wav';tmp=path.with_suffix('.partial.wav')
            try:
                run([binary('ffmpeg'),'-v','error','-y','-nostdin','-ss',f'{pad_start:.6f}','-i',p.video,'-t',f'{pad_end-pad_start:.6f}','-vn','-ac',2,'-ar',44100,'-c:a','pcm_s16le',source],cancel)
                if separator is None:
                    if session is None:
                        report(80*i/len(plans),'Khởi động AI một lần cho lượt chạy này…')
                        session=MusicSession(models,root,p.music_threads,backend=p.music_backend)
                        ready=session.wait('ready',cancel,lambda elapsed:report(80*i/len(plans),f'Khởi động / tải mô hình AI · {stamp(elapsed)} · Chưa tính thời gian xử lý'))
                        report(80*i/len(plans),'Bộ xử lý: '+str((ready or {}).get('device',p.music_backend)))
                        chunk_began=time.monotonic()
                    info=session.separate(source,estimated,cancel,heartbeat) or {}
                    if info.get('gpu_nodes'):report(80*i/len(plans),f"Đã xác nhận GPU: {info['device']} · {info['gpu_nodes']} lượt nút DirectML, {info['cpu_nodes']} CPU")
                else:separator(source,estimated,models,cancel)
                # Context is discarded, never concatenated twice. A tiny edge fade avoids clicks.
                length=b-a
                run([binary('ffmpeg'),'-v','error','-y','-nostdin','-i',estimated,'-af',f'atrim=start={a-pad_start:.6f},asetpts=PTS-STARTPTS,apad,atrim=duration={length:.6f},afade=t=in:d=0.003,afade=t=out:st={max(0,length-.003):.6f}:d=0.003','-ac',2,'-ar',44100,'-c:a','pcm_s16le',tmp],cancel)
                if not music_chunk_valid(tmp,length):raise RuntimeError('Đoạn giảm nhạc sai thời lượng. Đoạn chưa được lưu; có thể thử lại.')
                tmp.replace(path)
                measured=time.monotonic()-chunk_began
                processed_seconds+=b-a;processing_time+=measured;remaining-=b-a
                ratio=processing_time/processed_seconds
                report(80*(i+1)/len(plans),f'Xong đoạn {i+1}/{len(plans)} · {measured:.1f}s cho {b-a:.1f}s âm · Còn khoảng {stamp(remaining*ratio)} + ghép âm')
            finally:
                for file in (source,estimated,tmp):file.unlink(missing_ok=True)
    finally:
        if session is not None:session.close()
    tag=f'{round(start*1000)}-{round(end*1000)}';dry=root/('speech-'+tag+'.flac');listing=root/('concat-'+tag+'.txt')
    if not dry.is_file():
        listing.write_text(''.join("file '"+path.name+"'\n" for _,_,path in plans),encoding='utf-8');tmp=dry.with_suffix('.partial.flac')
        try:run([binary('ffmpeg'),'-v','error','-y','-nostdin','-f','concat','-safe','0','-i',listing,'-c:a','flac',tmp],cancel);tmp.replace(dry)
        finally:tmp.unlink(missing_ok=True)
    report(85,'Ghép âm thanh đã giảm nhạc…');track=root/(f'clean-{tag}-{round(retain*1000)}.flac');original=root/('original-'+tag+'.flac')
    if segment is not None and not original.is_file():
        temp=original.with_suffix('.partial.flac')
        try:run([binary('ffmpeg'),'-v','error','-y','-nostdin','-ss',str(start),'-i',p.video,'-t',str(end-start),'-vn','-ac',2,'-ar',44100,'-c:a','flac',temp],cancel);temp.replace(original)
        finally:temp.unlink(missing_ok=True)
    if not track.is_file():
        tmp=track.with_suffix('.partial.flac')
        graph=f'[0:a]volume={1-retain:.6f}[speech];[1:a]volume={retain:.6f}[original];[speech][original]amix=inputs=2:duration=longest:normalize=0,apad,atrim=duration={end-start:.6f},alimiter=limit=0.97:level=false:latency=true[out]'
        try:run([binary('ffmpeg'),'-v','error','-y','-nostdin','-i',dry,'-ss',str(start),'-i',p.video,'-filter_complex',graph,'-map','[out]','-t',str(end-start),'-ac',2,'-ar',44100,'-c:a','flac',tmp],cancel);tmp.replace(track)
        finally:tmp.unlink(missing_ok=True)
    if abs(probe(track)['duration']-(end-start))>.05:
        track.unlink(missing_ok=True);dry.unlink(missing_ok=True)
        raise RuntimeError('Âm đã xử lý lệch thời lượng; chưa áp dụng vào dự án. Bấm xử lý tiếp để ghép lại các đoạn đã xong.')
    report(100,'Đã xử lý xong khoảng âm thanh.')
    return dict(source_key=key,track=str(track),original=str(original) if segment is not None else '',retain=retain,start=start,end=end,backend=p.music_backend,processing_seconds=processing_time,processed_audio_seconds=processed_seconds)


def make_music_preview(p,result,base,cancel,report):
    """Remux cached video without encoding frames; keeps one player/one clock for original audio."""
    base=Path(base);fingerprint=hashlib.sha256((str(base.resolve())+str(base.stat().st_mtime_ns)).encode()).hexdigest()[:12]
    target=Path(result['track']).with_name(Path(result['track']).stem+'-'+fingerprint+'.mkv')
    if not target.is_file():
        tmp=target.with_suffix('.partial.mkv')
        try:
            report(0,'Gắn âm đã giảm nhạc vào bản xem — sao chép hình, không mã hóa lại…')
            run([binary('ffmpeg'),'-y','-nostdin','-i',base,'-i',result['track'],'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(p.duration),'-progress','pipe:1','-nostats',tmp],cancel,progress=lambda n:report(n,'Đang chuẩn bị bản xem giảm nhạc…'),total=p.duration)
            if abs(probe(tmp)['duration']-p.duration)>.2:raise RuntimeError('Bản xem giảm nhạc sai thời lượng.')
            tmp.replace(target)
        finally:tmp.unlink(missing_ok=True)
    return dict(result,preview=str(target),preview_codec=probe(target)['video_codec'],enabled=True)
