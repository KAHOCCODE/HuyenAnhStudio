from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import numpy as np

from studio import core, audio_mix
from studio.core import Cue, Project, RATE, raw_key


def pcm(path, seconds=.25, tone=440):
    samples=(np.sin(np.arange(round(seconds*RATE))*2*np.pi*tone/RATE)*4000).astype('<i2')
    with wave.open(str(path),'wb') as target:
        target.setparams((1,2,RATE,0,'NONE','not compressed'))
        target.writeframes(samples.tobytes())


class IncrementalMixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cancel=threading.Event();self.source=self.root/'tone.wav';pcm(self.source)
        self.entries=[dict(start=62.,end=62.25,path=str(self.source))]
        self.cache=self.root/'cache';self.out=self.root/'review.wav'

    def tearDown(self):self.tmp.cleanup()

    def update(self,entries=None,duration=150,progress=lambda n:None,previous=None):
        return audio_mix.update_mix(self.entries if entries is None else entries,duration,self.out,
                                    self.cache,self.cancel,core.mix_track,progress,previous)

    def fresh(self,entries,duration,actual):
        expected=self.root/'expected.wav'
        core.mix_track(entries,duration,expected,self.cancel)
        self.assertEqual(Path(actual).read_bytes(),expected.read_bytes())

    def test_small_edit_and_no_change_preserve_unaffected_pcm(self):
        first=self.update();before=self.out.read_bytes();stat=self.out.stat()
        with patch('studio.core.mix_track',side_effect=AssertionError('Unchanged audio must not be rendered')):
            again=self.update()
        self.assertEqual(again['written_frames'],0);self.assertEqual(again['changed_blocks'],0)
        self.assertEqual(self.out.stat().st_mtime_ns,stat.st_mtime_ns)
        other=self.root/'other.wav';pcm(other,tone=880)
        entries=[dict(self.entries[0],path=str(other))]
        edited=self.update(entries)
        self.assertEqual(edited['changed_blocks'],1);self.assertEqual(edited['rendered_blocks'],1)
        self.assertEqual(edited['written_frames'],30*RATE)
        after=self.out.read_bytes()
        self.assertEqual(before[:44+60*RATE*2],after[:44+60*RATE*2])
        self.assertEqual(before[44+90*RATE*2:],after[44+90*RATE*2:])
        self.fresh(entries,150,edited['track'])

    def test_cancel_during_patch_restores_previous_bytes_and_revision(self):
        first=self.update();before=self.out.read_bytes()
        other=self.root/'other.wav';pcm(other,tone=880)
        def progress(value):
            if value>60:self.cancel.set()
        with self.assertRaises(InterruptedError):
            self.update([dict(self.entries[0],path=str(other))],progress=progress)
        self.assertEqual(before,self.out.read_bytes())
        self.assertTrue(audio_mix.ready(self.cache,self.out,first['token']))
        self.assertFalse((self.cache/'mix-transaction').exists())

    def test_cancel_full_rebuild_preserves_previous_track(self):
        first=self.update();before=self.out.read_bytes()
        other=self.root/'other.wav';pcm(other,tone=880)
        entries=[dict(start=float(i+2),end=i+2.25,path=str(other)) for i in range(0,150,30)]
        def progress(value):
            if value>60:self.cancel.set()
        with self.assertRaises(InterruptedError):self.update(entries,progress=progress)
        self.assertEqual(before,self.out.read_bytes())
        self.assertTrue(audio_mix.ready(self.cache,self.out,first['token']))

    def test_modified_review_track_is_rebuilt_instead_of_trusted_as_legacy(self):
        first=self.update();before=self.out.read_bytes()
        with self.out.open('r+b') as target:target.seek(44+62*RATE*2);target.write(b'\xff\x7f'*100)
        self.assertFalse(audio_mix.ready(self.cache,self.out,first['token']))
        result=self.update(previous=dict(track=str(self.out),duration=150,rows=self.entries))
        self.assertEqual(self.out.read_bytes(),before)
        self.assertTrue(audio_mix.ready(self.cache,self.out,result['token']))

    def test_interrupted_process_is_refused_then_recovered(self):
        first=self.update();before=self.out.read_bytes()
        other=self.root/'other.wav';pcm(other,tone=880)
        code='''import os,sys,threading
from studio import core,audio_mix
source,cache,out=sys.argv[1:]
def progress(n):
    if n>60:os._exit(73)
audio_mix.update_mix([dict(start=62.,end=62.25,path=source)],150,out,cache,threading.Event(),core.mix_track,progress)
'''
        result=subprocess.run([sys.executable,'-c',code,str(other),str(self.cache),str(self.out)],
                              cwd=Path(__file__).resolve().parent.parent,check=False,timeout=15)
        self.assertEqual(result.returncode,73)
        self.assertFalse(audio_mix.ready(self.cache,self.out,first['token']))
        audio_mix.recover(self.cache)
        self.assertEqual(before,self.out.read_bytes())
        self.assertTrue(audio_mix.ready(self.cache,self.out,first['token']))

    def test_growing_shrinking_and_removing_audio_match_full_mix(self):
        self.update()
        for duration,entries in [(154,self.entries),(150,self.entries),(120,self.entries),(120,[])]:
            with self.subTest(duration=duration,entries=len(entries)):
                result=self.update(entries,duration)
                self.fresh(entries,duration,result['track'])
                with wave.open(result['track'],'rb') as source:self.assertEqual(source.getnframes(),round(duration*RATE))

    def test_migrate_six_hour_track_writes_only_thirty_seconds(self):
        frames=21600*RATE
        with self.out.open('wb') as target:
            target.write(audio_mix.header(frames));target.truncate(44+frames*2)
        result=self.update(duration=21600,previous=dict(track=str(self.out),duration=21600,rows=[]))
        self.assertEqual(result['total_blocks'],720)
        self.assertEqual(result['reused_blocks'],719)
        self.assertEqual(result['changed_blocks'],1)
        self.assertEqual(result['written_frames'],30*RATE)
        self.assertEqual(self.out.stat().st_size,44+frames*2)
        with wave.open(str(self.out),'rb') as source:
            source.setpos(62*RATE)
            self.assertGreater(np.abs(np.frombuffer(source.readframes(RATE//4),dtype='<i2')).sum(),0)
        self.assertTrue(audio_mix.ready(self.cache,self.out,result['token']))

    def test_block_boundary_rounding_overlaps_and_clipping(self):
        entries=[dict(start=29.9,end=30.1,path=str(self.source)),
                 dict(start=30.00001,end=30.25,path=str(self.source)),
                 dict(start=-.1,end=.15,path=str(self.source))]
        result=self.update(entries,duration=91.2345)
        self.fresh(entries,91.2345,result['track'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class PreparedVoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cancel=threading.Event()
        self.p=Project(duration=150,cues=[Cue(i,i+1,text,id=text) for i,text in [(2,'one'),(62,'two'),(122,'three')]])
        self.tone=self.root/'source.wav';pcm(self.tone)
        self.mp3=self.root/'source.mp3'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(self.tone),str(self.mp3)],check=True)
        for cue in self.p.cues:shutil.copyfile(self.mp3,self.root/(raw_key(cue,self.p)+'.mp3'))

    def tearDown(self):self.tmp.cleanup()

    def rebuild(self):return core.rebuild_voice_track(self.p,self.root,self.cancel,lambda *a:None)

    def test_restart_reuses_all_rows_and_does_not_touch_mixed_audio(self):
        first=self.rebuild();before=Path(first['track']).stat()
        with patch('studio.core.prepare_voice_row',side_effect=AssertionError('Must reuse prepared rows')),\
                patch('studio.core.probe',side_effect=AssertionError('Must reuse durations')),\
                patch('studio.core.mix_track',side_effect=AssertionError('Must reuse mixed audio')):
            again=self.rebuild()
        self.assertEqual(again['prepared_reused'],3)
        self.assertEqual(again['mix_stats']['written_frames'],0)
        self.assertEqual(Path(again['track']).stat().st_mtime_ns,before.st_mtime_ns)
        self.assertTrue(core.voice_ready(self.p,self.root))

    def test_one_changed_cue_prepares_once_and_patches_one_block(self):
        first=self.rebuild();old=Path(first['track']).read_bytes()
        cue=self.p.cues[1];cue.text='changed'
        shutil.copyfile(self.mp3,self.root/(raw_key(cue,self.p)+'.mp3'))
        self.assertFalse(core.voice_ready(self.p,self.root))
        with patch('studio.core.prepare_voice_row',wraps=core.prepare_voice_row) as prepare:
            result=self.rebuild()
        self.assertEqual(prepare.call_count,1);self.assertEqual(result['prepared_reused'],2)
        self.assertEqual(result['mix_stats']['changed_blocks'],1)
        self.assertEqual(result['mix_stats']['written_frames'],30*RATE)
        self.assertEqual(Path(result['track']).read_bytes(),old)  # Same tone, changed cache identity.
        self.assertTrue(core.voice_ready(self.p,self.root))

    def test_duration_change_retimes_following_cues_without_repreparing_them(self):
        first=self.rebuild();cue=self.p.cues[1];raw=self.root/(raw_key(cue,self.p)+'.mp3')
        pcm(self.tone,seconds=2.2,tone=880)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(self.tone),str(raw)],check=True)
        self.assertFalse(core.voice_ready(self.p,self.root))
        with patch('studio.core.prepare_voice_row',wraps=core.prepare_voice_row) as prepare:
            result=self.rebuild()
        self.assertEqual(prepare.call_count,1)
        self.assertGreater(result['rows'][-1]['start'],first['rows'][-1]['start'])
        self.assertTrue(all(row['applied']==1 for row in result['rows']))
        expected=self.root/'expected.wav';core.mix_track(result['rows'],result['duration'],expected,self.cancel)
        self.assertEqual(Path(result['track']).read_bytes(),expected.read_bytes())
        self.assertTrue(core.voice_ready(self.p,self.root))

    def test_missing_raw_or_fitted_audio_and_unrelated_edits(self):
        first=self.rebuild();self.p.original_volume=.33;self.p.voice_volume=1.4;self.p.style['color']='#FF0000'
        self.assertTrue(core.voice_ready(self.p,self.root))
        Path(first['rows'][0]['path']).unlink()
        with patch('studio.core.prepare_voice_row',wraps=core.prepare_voice_row) as prepare:rebuilt=self.rebuild()
        self.assertEqual(prepare.call_count,1)
        (self.root/(raw_key(self.p.cues[1],self.p)+'.mp3')).unlink()
        self.assertFalse(core.voice_ready(self.p,self.root));partial=self.rebuild()
        self.assertEqual(partial['missing_count'],1);self.assertFalse(partial['complete'])

    def test_generation_then_review_uses_the_same_prepared_rows(self):
        result=core.generate_voices(self.p,self.root,self.cancel,lambda *a:None,mix=False)
        self.assertEqual(result['prepared_updated'],3)
        with patch('studio.core.prepare_voice_row',side_effect=AssertionError('No second preparation')):
            reviewed=self.rebuild()
            again=core.generate_voices(self.p,self.root,self.cancel,lambda *a:None,mix=False)
        self.assertEqual(reviewed['prepared_reused'],3);self.assertEqual(again['prepared_reused'],3)

    def test_natural_voice_timing_edits_reuse_pcm_and_refresh_row_measurements(self):
        self.rebuild();self.p.work_speed=.75;self.p.cues[1].end+=.7
        with patch('studio.core.prepare_voice_row',side_effect=AssertionError('Timing edits keep natural PCM')):
            result=self.rebuild()
        self.assertEqual(result['prepared_reused'],3)
        self.assertEqual(result['prepared_updated'],0)
        self.assertTrue(all(r['applied']==1 for r in result['rows']))
        expected=self.root/'expected.wav';core.mix_track(result['rows'],result['duration'],expected,self.cancel)
        self.assertEqual(Path(result['track']).read_bytes(),expected.read_bytes())

    def test_10000_cues_reuse_cache_without_per_cue_progress_or_ffmpeg(self):
        self.p.cues=[Cue(i*2,i*2+1,'shared',id=str(i)) for i in range(10000)]
        self.p.duration=21600
        raw=self.root/(raw_key(self.p.cues[0],self.p)+'.mp3');shutil.copyfile(self.mp3,raw)
        core.collect_voice_rows(self.p,self.p.cues,self.root,self.cancel,lambda *a:None)
        messages=[]
        with patch('studio.core.prepare_voice_row',side_effect=AssertionError('Reuse all rows')),\
                patch('studio.core.probe',side_effect=AssertionError('Reuse all durations')):
            result=core.collect_voice_rows(self.p,self.p.cues,self.root,self.cancel,lambda *a:messages.append(a))
        self.assertEqual(result['prepared_reused'],10000);self.assertEqual(result['prepared_updated'],0)
        self.assertLess(len(messages),100)


if __name__=='__main__':unittest.main()
