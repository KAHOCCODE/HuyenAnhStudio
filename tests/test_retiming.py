import copy
import tempfile
import threading
import unittest
import shutil
from pathlib import Path

from studio.core import (Cue,Project,voice_timing,map_time,source_rate,retimed_cues,
                         framing_pixels,raw_key,run,binary,probe,rebuild_voice_track,
                         export_video,write_srt,parse_srt,prepare_voice_row,voice_ready)


class TimingTests(unittest.TestCase):
    def test_requested_example_and_following_cue(self):
        p=Project(duration=12,cues=[Cue(2.433,3.233,'Đừng động đậy.',id='a'),Cue(4,5,'Câu sau',id='b')])
        timing=voice_timing(p,[dict(id='a',duration=2.567),dict(id='b',duration=1.)])
        self.assertAlmostEqual(map_time(timing,3.233),5.)
        self.assertAlmostEqual(timing['rows']['b']['start'],5.767)
        self.assertAlmostEqual(timing['duration'],13.767)
        self.assertAlmostEqual(source_rate(timing,3),.8/2.567)
        self.assertEqual(p.cues[0].end,3.233)
        for t in [0,2.433,2.9,3.233,4,5,12]:self.assertAlmostEqual(map_time(timing,map_time(timing,t),True),t)

    def test_overlapping_and_simultaneous_source_cues_are_serialized(self):
        p=Project(duration=8,cues=[Cue(1,5,'a',id='a'),Cue(1,2,'b',id='b'),Cue(2,3,'c',id='c')])
        timing=voice_timing(p,[dict(id=c.id,duration=2) for c in p.cues])
        rows=sorted(timing['rows'].values(),key=lambda r:r['start'])
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(rows,rows[1:])))
        captions=retimed_cues(p,timing)
        self.assertTrue(all(a.end<=b.start for a,b in zip(captions,captions[1:])))

    def test_missing_voice_and_work_speed(self):
        p=Project(duration=10,work_speed=.5,cues=[Cue(1,2,'a',id='a'),Cue(3,4,'b',id='b')])
        timing=voice_timing(p,[dict(id='b',duration=3)])
        self.assertAlmostEqual(timing['duration'],21.)
        self.assertAlmostEqual(timing['rows']['b']['start'],6.)
        self.assertEqual(len(retimed_cues(p,timing)),2)

    def test_project_backwards_compatibility_and_framing(self):
        old=Project().to_dict()
        for key in ('slow_video_for_voice','mute_original_when_dubbed','framing'):old.pop(key)
        p=Project.from_dict(old)
        self.assertTrue(p.slow_video_for_voice)
        p.framing=dict(zoom=2.,x=100.,y=0.,flip=True)
        self.assertEqual(framing_pixels(p),(960,0,960,540))
        self.assertEqual(Project.from_dict(p.to_dict()).framing,p.framing)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cache=self.root/'cache';self.cache.mkdir();self.cancel=threading.Event()
        self.video=self.root/'source.mp4'
        run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=4',
             '-f','lavfi','-i','sine=frequency=220:duration=4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac',self.video])
        self.p=Project(video=str(self.video),duration=4,width=160,height=90,has_audio=True,
                       cues=[Cue(.5,1.,'Đừng động đậy.',id='a'),Cue(1.,1.5,'Câu hai',id='b')],export_preset='ultrafast')
        for cue,duration in zip(self.p.cues,[1.4,.8]):
            run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i',f'sine=frequency=880:sample_rate=24000:duration={duration}',
                 '-ac','1',self.cache/(raw_key(cue,self.p)+'.mp3')])

    def tearDown(self):self.temp.cleanup()
    def report(self,*args):pass

    def test_natural_voice_export_subtitles_and_muted_original(self):
        m=rebuild_voice_track(self.p,self.cache,self.cancel,self.report)
        rows=m['rows'];self.assertLessEqual(rows[0]['end'],rows[1]['start'])
        self.assertTrue(all(r['applied']==1 for r in rows));self.assertTrue(m['complete'])
        self.p.framing=dict(zoom=2.,x=100.,y=0.,flip=True)
        out=self.root/'out.mp4';export_video(self.p,self.cache,out,self.cancel,self.report)
        info=probe(out);self.assertEqual((info['width'],info['height']),(160,90))
        self.assertAlmostEqual(info['duration'],m['duration'],delta=.08)
        # With original muted, the pre-dialogue section contains no original 220 Hz tone.
        audio=self.root/'head.wav'
        run([binary('ffmpeg'),'-v','error','-y','-i',out,'-t','0.35','-ar','24000','-ac','1',audio])
        import wave,numpy as np
        with wave.open(str(audio),'rb') as f:samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
        self.assertLess(float(np.abs(samples.astype(float)).mean()),10.)
        # Check the actual source picture at its mapped output time, with right-half
        # crop + mirror. Ignore the lower half where the new subtitle is burned.
        reference=self.root/'reference.rgb';rendered=self.root/'rendered.rgb'
        for path,source,t,filters in [(reference,self.video,1.2,'crop=80:44:80:0,scale=160:90,hflip'),
                                     (rendered,out,map_time(m['timing'],1.2),'null')]:
            run([binary('ffmpeg'),'-v','error','-y','-ss',str(t),'-i',source,'-vf',filters,
                 '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo',path])
        expected=np.frombuffer(reference.read_bytes(),dtype=np.uint8).reshape(90,160,3)[:40].astype(float)
        actual=np.frombuffer(rendered.read_bytes(),dtype=np.uint8).reshape(90,160,3)[:40].astype(float)
        self.assertLess(float(np.abs(expected-actual).mean()),15.)
        srt=self.root/'retimed.srt';write_srt(srt,retimed_cues(self.p,m['timing']))
        cues=parse_srt(srt.read_text(encoding='utf-8-sig'));self.assertLessEqual(cues[0].end,cues[1].start)

    def test_segment_final_speed_and_keep_original(self):
        self.p.final_speed=1.25;self.p.work_speed=.8;self.p.mute_original_when_dubbed=False
        bounds=(.75,2.5)
        m=rebuild_voice_track(self.p,self.cache,self.cancel,self.report,segment=bounds,include_overlap=True)
        out=self.root/'region.mp4'
        export_video(self.p,self.cache,out,self.cancel,self.report,segment=bounds,review_voice=m,allow_partial=True)
        self.assertAlmostEqual(probe(out)['duration'],m['duration']/1.25,delta=.1)

    def test_mode_switch_invalidates_track_without_regenerating_raw(self):
        rebuild_voice_track(self.p,self.cache,self.cancel,self.report)
        self.assertTrue(voice_ready(self.p,self.cache));keys=[raw_key(c,self.p) for c in self.p.cues]
        self.p.slow_video_for_voice=False;self.assertFalse(voice_ready(self.p,self.cache))
        row=prepare_voice_row(self.p.cues[0],self.p,self.cache,self.cancel)
        self.assertGreater(row['applied'],1.)
        self.p.slow_video_for_voice=True
        row=prepare_voice_row(self.p.cues[0],self.p,self.cache,self.cancel)
        self.assertEqual(row['applied'],1.)
        self.assertEqual(keys,[raw_key(c,self.p) for c in self.p.cues])

    def test_multiple_chunks_do_not_accumulate_time_drift(self):
        self.p.cues=[Cue(i*.1,i*.1+.08,'Cùng một câu',id=str(i)) for i in range(40)]
        run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','sine=frequency=880:sample_rate=24000:duration=0.14',
             self.cache/(raw_key(self.p.cues[0],self.p)+'.mp3')])
        m=rebuild_voice_track(self.p,self.cache,self.cancel,self.report)
        out=self.root/'chunks.mp4';export_video(self.p,self.cache,out,self.cancel,self.report)
        self.assertAlmostEqual(probe(out)['duration'],m['duration'],delta=.08)

    def test_last_overlong_cue_keeps_video_until_voice_finishes(self):
        self.p.cues=[Cue(3.9,4.,self.p.cues[0].text,id='a')]
        m=rebuild_voice_track(self.p,self.cache,self.cancel,self.report)
        out=self.root/'tail.mp4';export_video(self.p,self.cache,out,self.cancel,self.report)
        video_duration=float(run([binary('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=duration','-of','csv=p=0',out],capture=True))
        self.assertAlmostEqual(video_duration,m['duration'],delta=.08)


if __name__=='__main__':unittest.main()
