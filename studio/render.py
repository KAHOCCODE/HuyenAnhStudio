"""Bounded-size render graphs for locally stretched video and original audio."""
import copy
import math
import shutil
import uuid
from pathlib import Path


def export_retimed_video(p,cache,out,cancel,report,manifest,preview=None,segment=None):
    from .core import (voice_timing,map_time,write_ass,video_filter,binary,run,
                       clean_audio_path,atempo,stamp,retimed_cues,voice_volume_filter,
                       export_encoder)
    from .video_effects import output_size,settings
    from .composition import prepare_layers
    timing=manifest.get('timing') or voice_timing(p,manifest['rows'])
    a,b=segment or (0.,p.duration)
    if not 0<=a<b<=p.duration+.001:raise ValueError('Vùng xuất nằm ngoài video.')
    if preview is not None and segment is None:
        a=max(0.,min(preview*p.speed,p.duration-.001));b=min(p.duration,a+10*p.speed)
    begin=map_time(timing,a);finish=map_time(timing,b)
    duration=(finish-begin)/p.final_speed
    job=Path(cache)/('retime-'+uuid.uuid4().hex[:10]);job.mkdir(parents=True)
    partial=Path(out).with_name(Path(out).stem+'.partial'+Path(out).suffix)
    keep_original=p.has_audio and p.original_gain>0 and not p.mute_original_when_dubbed
    try:
        # Caption coordinates refer to the output frame; timing refers to the new clock.
        captions=copy.deepcopy(p);captions.cues=[]
        for c in retimed_cues(p,timing):
            start,end=c.start,c.end
            if end<=begin or start>=finish:continue
            c.start=max(0.,(start-begin)/p.final_speed);c.end=min(duration,(end-begin)/p.final_speed)
            captions.cues.append(c)
        for r in captions.screen_regions:
            r['start']=(map_time(timing,r['start'])-begin)/p.final_speed
            r['end']=(map_time(timing,r['end'])-begin)/p.final_speed
        write_ass(job/'subtitles.ass',captions,regions=False,canvas=output_size(p))
        effects=settings(p.video_effects)
        write_ass(job/'regions.ass',p,cues=False,mirror_regions=bool(effects['enabled'] and effects['flip']))
        assets=prepare_layers(job,p) if p.overlays else []
        encoder,options=export_encoder(p,p.export_preset,cancel,report)
        # Put chunk boundaries on the output frame grid to prevent cumulative drift.
        cuts=[begin]
        relevant=[s for s in timing['spans'] if s['end']>a and s['start']<b]
        for index in range(32,len(relevant),32):
            t=begin+math.ceil((relevant[index]['out_start']-begin)/p.final_speed*30)/30*p.final_speed
            if cuts[-1]+1e-6<t<finish-1e-6:cuts.append(t)
        cuts.append(finish);parts=[]
        for index,(left,right) in enumerate(zip(cuts,cuts[1:])):
            if cancel.is_set():raise InterruptedError('Đã hủy xuất video.')
            src_a=map_time(timing,left,True);src_b=map_time(timing,right,True)
            length=(right-left)/p.final_speed
            spans=[s for s in timing['spans'] if s['end']>src_a+1e-9 and s['start']<src_b-1e-9]
            terms=[]
            for s in spans:
                lo=max(src_a,s['start']);hi=min(src_b,s['end'])
                ratio=(s['out_end']-s['out_start'])/(s['end']-s['start'])/p.final_speed
                terms.append(f'min(max(T-{lo:.9f},0),{hi-lo:.9f})*{ratio:.12f}')
            graph=f'[0:v]setpts=PTS-STARTPTS+{src_a:.9f}/TB[src];'
            graph+=video_filter(p,assets=assets,finish=False).replace('[0:v]','[src]').replace('[v]','[framed]')
            graph+=";[framed]setpts='("+'+'.join(terms)+f")/TB',fps=30,tpad=stop_mode=clone:stop_duration={length:.9f},trim=duration={length:.9f},setpts=PTS+{(left-begin)/p.final_speed:.9f}/TB,subtitles=filename='subtitles.ass',setpts=PTS-STARTPTS,format=yuv420p[v]"
            args=[binary('ffmpeg'),'-y','-v','error','-nostdin','-ss',f'{src_a:.9f}','-t',f'{src_b-src_a:.9f}','-i',p.video]
            if keep_original:
                clean=clean_audio_path(p)
                audio='0:a'
                if clean:
                    args+=['-ss',f'{src_a:.9f}','-t',f'{src_b-src_a:.9f}','-i',str(clean)];audio='1:a'
                graph+=f';[{audio}]asetpts=PTS-STARTPTS,asplit={len(spans)}'+''.join(f'[in{i}]' for i in range(len(spans)))
                for i,s in enumerate(spans):
                    lo=max(src_a,s['start']);hi=min(src_b,s['end'])
                    speed=(s['end']-s['start'])/(s['out_end']-s['out_start'])*p.final_speed
                    length=(hi-lo)/speed
                    graph+=f';[in{i}]atrim=start={lo-src_a:.9f}:end={hi-src_a:.9f},asetpts=PTS-STARTPTS,{atempo(speed)},apad,atrim=duration={length:.9f}[a{i}]'
                graph+=';'+''.join(f'[a{i}]' for i in range(len(spans)))+f'concat=n={len(spans)}:v=0:a=1[a]'
            script=job/'chunk-filters.txt';script.write_text(graph,encoding='utf-8')
            name=f'part-{index:05d}.mkv';parts.append(name)
            args+=['-filter_complex_threads','1','-filter_complex_script',script.name,'-map','[v]']
            if keep_original:args+=['-map','[a]','-c:a','pcm_s16le','-ar','48000','-ac','2']
            else:args+=['-an']
            args+=['-t',f'{length:.9f}']
            tail=['-threads','2','-progress','pipe:1','-nostats',name]
            def progress(percent):
                overall=90*((left-begin)+(right-left)*percent/100)/(finish-begin)
                report(overall,f'Làm chậm video cục bộ · đoạn {index+1}/{len(cuts)-1} · {overall:.1f}%')
            try:run(args+options+tail,cancel,cwd=job,progress=progress,total=length)
            except RuntimeError:
                if options[1]=='libx264' or cancel.is_set():raise
                encoder='CPU · libx264';options=['-c:v','libx264','-preset',p.export_preset,'-crf','20']
                report(0,'GPU không dùng được với bộ lọc này · chuyển sang CPU')
                run(args+options+tail,cancel,cwd=job,progress=progress,total=length)
        (job/'parts.txt').write_text(''.join(f"file '{name}'\n" for name in parts),encoding='utf-8')
        # Captions are already burned. Concatenate and mux without re-encoding video.
        run([binary('ffmpeg'),'-y','-v','error','-f','concat','-safe','0','-i','parts.txt','-c','copy','joined.mkv'],cancel,cwd=job)
        voice_offset=max(0.,begin-map_time(timing,segment[0] if segment else 0.))
        graph=f'[1:a]asetpts=PTS-STARTPTS,{atempo(p.final_speed)},{voice_volume_filter(p.voice_volume)},apad,atrim=duration={duration:.9f}[voice]'
        if keep_original:
            graph+=f';[0:a]volume={p.original_gain},apad,atrim=duration={duration:.9f}[original];[original][voice]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.97:level=false:latency=true[a]'
        else:graph+=';[voice]alimiter=limit=0.97:level=false:latency=true[a]'
        (job/'finish.txt').write_text(graph,encoding='utf-8')
        args=[binary('ffmpeg'),'-y','-v','error','-nostdin','-i','joined.mkv','-ss',f'{voice_offset:.9f}','-i',manifest['track'],
              '-filter_complex_threads','1','-filter_complex_script','finish.txt','-map','0:v','-map','[a]','-t',f'{duration:.9f}',
              '-c:v','copy','-c:a','aac','-b:a','192k',
              '-movflags','+faststart','-progress','pipe:1','-nostats',str(partial)]
        run(args,cancel,cwd=job,total=duration,progress=lambda n:report(90+.1*n,f'Ghép âm thanh · {90+.1*n:.1f}%'))
        if Path(out).exists():raise ValueError('Tệp đích vừa được tạo; không ghi đè.')
        partial.replace(out);report(100,f'Đã xuất video · {stamp(duration)} · giữ tốc độ đọc tự nhiên.');return str(out)
    finally:
        partial.unlink(missing_ok=True);shutil.rmtree(job,ignore_errors=True)
