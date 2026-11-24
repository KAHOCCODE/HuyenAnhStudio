import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import numpy as np
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QComboBox,QDialog,QCheckBox,QPushButton
from studio import core
from studio.core import (Project,Cue,MusicSession,MUSIC_WORKER,music_source_key,
                         build_music_reduction,clean_audio_path,make_music_preview,
                         rebuild_voice_track,raw_key,export_video,run,binary,probe)
from studio.ui import Window


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class DialogueRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.video=self.root/'source.mp4';self.cache=self.root/'cache'
        self.cancel=threading.Event()
        run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=blue:s=160x90:r=10:d=2',
             '-f','lavfi','-i','aevalsrc=0.08*sin(2*PI*220*t)+0.08*sin(2*PI*880*t):s=44100:d=2',
             '-c:v','libx264','-threads','1','-c:a','aac',self.video])
        self.p=Project(video=str(self.video),duration=2,width=160,height=90,
                       has_audio=True,export_preset='ultrafast',original_volume=.5)

    def tearDown(self):self.temp.cleanup()

    def levels(self,path):
        pcm=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(path),
                                     '-vn','-ar','24000','-ac','1','-f','f32le','-'])
        samples=np.frombuffer(pcm,dtype='<f4')[9600:14400]
        spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples))))
        frequencies=np.fft.rfftfreq(len(samples),1/24000)
        return [float(np.sqrt(np.sum(spectrum[np.abs(frequencies-tone)<20]**2))/len(samples))
                for tone in (220,880,1320)]

    def separated(self,frequency):
        def separate(source,target,models,cancel):
            run([binary('ffmpeg'),'-v','error','-y','-i',source,'-af',
                 f'bandpass=f={frequency}:t=h:w=60','-c:a','pcm_s16le',target],cancel)
        return separate

    def test_background_cache_isolated_from_legacy_speech_and_reused(self):
        source=self.video.stat()
        identity=[str(self.video.resolve()),source.st_size,source.st_mtime_ns,
                  core.MUSIC_MODEL,core.MUSIC_ENGINE_VERSION]
        legacy=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:24]
        self.assertEqual(music_source_key(self.p),legacy)
        speech=build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,
                                     retain=0,separator=self.separated(220))
        speech.pop('mode')
        self.p.music_clean=dict(speech,enabled=True)
        self.assertEqual(str(clean_audio_path(self.p)),speech['track'])
        background=build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,
                                         mode='background',separator=self.separated(880))
        self.assertNotEqual(background['source_key'],speech['source_key'])
        self.assertNotEqual(background['track'],speech['track'])
        self.assertEqual(background['retain'],0)
        self.assertFalse(background['polish'])
        before=copy.deepcopy(self.p.to_dict())
        again=build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,mode='background',
                                    separator=lambda *a:self.fail('Completed background chunks must be reused'))
        self.assertEqual(again['track'],background['track'])
        self.assertEqual(self.p.to_dict(),before)
        self.p.music_clean=dict(background,enabled=True)
        self.assertEqual(str(clean_audio_path(self.p)),background['track'])
        self.assertEqual(Project.from_dict(self.p.to_dict()).music_clean,self.p.music_clean)
        self.p.music_clean['source_key']=legacy
        with self.assertRaises(ValueError):clean_audio_path(self.p)
        for kwargs in ({'mode':'bad'},{'mode':'background','retain':.12},
                       {'mode':'background','polish':True}):
            with self.assertRaises(ValueError):
                build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,**kwargs)

    def test_filtered_background_reaches_playback_full_export_and_slow_video(self):
        result=build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,
                                     mode='background',separator=self.separated(880))
        self.p.music_clean=make_music_preview(self.p,result,self.video,self.cancel,lambda *a:None)
        voice,background,_=self.levels(self.p.music_clean['preview'])
        self.assertGreater(background,.01)
        self.assertLess(voice,background*.1)
        self.p.cues=[Cue(.25,.75,'Voice Việt')]
        run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i',
             'sine=frequency=1320:sample_rate=24000:duration=0.8',
             self.cache/(raw_key(self.p.cues[0],self.p)+'.mp3')])
        for slow in (True,False):
            self.p.slow_video_for_voice=slow
            rebuild_voice_track(self.p,self.cache,self.cancel,lambda *a:None)
            for preview in (None,.1):
                with self.subTest(slow=slow,preview=preview):
                    out=self.root/f'dubbed-{slow}-{preview}.mp4'
                    export_video(self.p,self.cache,out,self.cancel,lambda *a:None,
                                 preview=preview,allow_partial=True)
                    voice,background,dubbed=self.levels(out)
                    self.assertGreater(background,.004)
                    self.assertGreater(dubbed,.015)
                    self.assertLess(voice,background*.1)

    def test_cancel_and_resume_keep_completed_background_chunks(self):
        audio=self.root/'long.wav'
        run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i',
             'sine=frequency=880:duration=61','-ar','44100','-ac','2',audio])
        project=Project(video=str(audio),duration=61,has_audio=True)
        calls=[]
        def interrupted(source,target,models,cancel):
            calls.append(source)
            if len(calls)==2:
                cancel.set();raise InterruptedError('Test cancellation')
            shutil.copyfile(source,target)
        with self.assertRaises(InterruptedError):
            build_music_reduction(project,self.cache,self.cancel,lambda *a:None,
                                  mode='background',separator=interrupted)
        root=self.cache/'music-clean'/music_source_key(project,'background')
        self.assertEqual(len(list(root.glob('chunk-*.wav'))),1)
        self.assertFalse(list(root.glob('*.partial*')))
        self.cancel.clear();resumed=[]
        def separate(source,target,models,cancel):
            resumed.append(source);shutil.copyfile(source,target)
        result=build_music_reduction(project,self.cache,self.cancel,lambda *a:None,
                                     mode='background',separator=separate)
        self.assertEqual(len(resumed),2)
        self.assertAlmostEqual(probe(result['track'])['duration'],61,delta=.01)

    def test_actual_worker_protocol_requests_instrumental_stem(self):
        # Exercise the production JSON worker and separator arguments with a tiny model double.
        prelude=r'''
import sys,types,pathlib,json,shutil
torch=types.ModuleType('torch')
torch.set_num_threads=lambda n:None;torch.set_num_interop_threads=lambda n:None
sys.modules['torch']=torch
ort=types.ModuleType('onnxruntime');ort.InferenceSession=lambda *a,**k:None
ort.disable_telemetry_events=lambda:None
sys.modules['onnxruntime']=ort
class Model:
    def __init__(self,**kwargs):
        self.settings=kwargs
        pathlib.Path(kwargs['output_dir'],'request.json').write_text(json.dumps(kwargs))
    def load_model(self,**kwargs):pass
    def separate(self,source,custom_output_names):
        stem=self.settings['output_single_stem']
        path=pathlib.Path(self.settings['output_dir'])/(custom_output_names[stem]+'.wav')
        shutil.copyfile(source,path)
        return [str(path)]
package=types.ModuleType('audio_separator');module=types.ModuleType('audio_separator.separator')
module.Separator=Model;sys.modules['audio_separator']=package;sys.modules['audio_separator.separator']=module
'''
        self.cache.mkdir(exist_ok=True)
        session=MusicSession(self.root,self.cache,python=sys.executable,
                             worker_code=prelude+MUSIC_WORKER,mode='background')
        try:
            ready=session.wait('ready',self.cancel)
            self.assertEqual(ready['stem'],'Instrumental')
            recorded=json.loads((session.out/'request.json').read_text())
            self.assertEqual(recorded['output_single_stem'],'Instrumental')
            target=self.root/'output.wav'
            session.separate(self.video,target,self.cancel)
            self.assertTrue(target.is_file())
            self.assertFalse((session.out/'background.wav').exists())
        finally:session.close()

    def test_normal_ui_entry_applies_background_and_can_restore_original(self):
        result=build_music_reduction(self.p,self.cache,self.cancel,lambda *a:None,
                                     mode='background',separator=self.separated(880))
        window=Window();window.p=self.p;window.cache=self.cache
        window.p.original_muted=True;window.p.original_volume=0
        window.p.music_clean={'polish':True}
        window.load_controls();window.show();window.go_stage(3);window.subtitle_tabs.setCurrentIndex(1)
        self.assertTrue(window.remove_dialogue_btn.isVisible())
        def inspect(dialog):
            self.assertEqual(dialog.findChild(QComboBox,'separation_mode').currentData(),'background')
            self.assertTrue(dialog.findChild(QCheckBox,'separation_polish').isHidden())
            button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Xử lý / tiếp tục toàn video')
            button.click()
        def start(work,done,label):done(work(self.cancel,lambda *a:None))
        try:
            with patch.object(QDialog,'exec',inspect),patch.object(window,'start_job',side_effect=start),\
                 patch.object(window,'save',return_value=True),patch.object(window,'load_preview_source'),\
                 patch('studio.ui.build_music_reduction',return_value=result) as build,\
                 patch('studio.ui.make_music_preview',return_value=dict(result,enabled=True,preview=str(self.video))):
                window.remove_dialogue_btn.click()
                self.assertEqual(build.call_args.kwargs['mode'],'background')
                self.assertFalse(build.call_args.kwargs['polish'])
                self.assertEqual(build.call_args.args[4],0)
                self.assertTrue(window.p.music_clean['enabled'])
                self.assertFalse(window.p.original_muted)
                self.assertEqual(window.p.original_volume,.12)
                self.assertFalse(window.mute_original.isChecked())
                self.assertIn('đã tách giọng gốc',window.export_summary.text())
            def restore(dialog):
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Dùng lại âm gốc').click()
            with patch.object(QDialog,'exec',restore),patch.object(window,'save',return_value=True),\
                 patch.object(window,'load_preview_source'):
                window.remove_dialogue_btn.click()
                self.assertFalse(window.p.music_clean['enabled'])
        finally:
            window.close_cpu();window.dirty=False;window.close();window.deleteLater();QTest.qWait(30)


if __name__=='__main__':unittest.main()
