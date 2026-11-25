import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QSpinBox
from studio import core
from studio.core import Cue,Project,generate_voices,raw_key,signature
from studio.local_tts import LocalTTSPool,LocalTTSSession
from studio.tts import TTSServiceError
from studio.ui import Window
from studio.voices import VIENEU_PREFIX


WORKER='''import json,math,os,struct,sys,time,wave
from pathlib import Path
log=Path(__file__).with_suffix('.log')
def record(event,text=''):
    with log.open('a',encoding='utf-8') as f:f.write(json.dumps([event,os.getpid(),time.monotonic(),text])+'\\n')
record('loaded')
print(json.dumps(dict(event='ready')),flush=True)
for line in sys.stdin:
    row=json.loads(line);text=row['text'];record('begin',text)
    if text=='wait':time.sleep(30)
    time.sleep(.25)
    if text=='fatal':
        print(json.dumps(dict(event='error',fatal=True,message='fatal fixture')),flush=True);continue
    if text=='fail':
        print(json.dumps(dict(event='error',message='bad cue')),flush=True);continue
    frequency=440 if text=='one' else 880
    with wave.open(row['target'],'wb') as out:
        out.setparams((1,2,24000,0,'NONE','not compressed'))
        out.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*frequency*i/24000))) for i in range(6000)))
    record('end',text)
    print(json.dumps(dict(event='done')),flush=True)
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class VieNeuParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.cache=self.root/'cache';self.cache.mkdir()
        self.worker=self.root/'worker.py';self.worker.write_text(WORKER)
        self.pool=LocalTTSPool(factory=lambda **kw:LocalTTSSession(python=sys.executable,worker=self.worker,**kw))
        self.cancel=threading.Event()

    def tearDown(self):self.pool.close();self.temp.cleanup()

    def project(self,count=8,limit=0):
        return Project(duration=count*2,voice=VIENEU_PREFIX+'Trúc Ly',vieneu_workers=2,tts_cue_limit=limit,
                       cues=[Cue(i*2,i*2+1,'one' if i==0 else f'word{i}',id=str(i)) for i in range(count)])

    def events(self):return [json.loads(line) for line in self.worker.with_suffix('.log').read_text().splitlines()]

    def generate(self,p,**kwargs):
        return generate_voices(p,self.cache,self.cancel,lambda *a:None,mix=False,local_session=self.pool,**kwargs)

    def peak(self):
        active=peak=0
        for event,_,_,_ in sorted(self.events(),key=lambda e:e[2]):
            if event=='begin':active+=1;peak=max(peak,active)
            if event=='end':active-=1
        return peak

    def test_two_real_processes_overlap_and_keep_independent_audio_targets(self):
        import numpy as np
        p=self.project(4);result=self.generate(p,parallel_segments=[(0,4),(4,8)])
        self.assertEqual(result['missing_count'],0);self.assertEqual(self.peak(),2)
        self.assertEqual(len([e for e in self.events() if e[0]=='loaded']),2)

        for cue in p.cues[:2]:
            raw=self.cache/(raw_key(cue,p)+'.mp3')
            data=subprocess.check_output(['ffmpeg','-v','error','-i',str(raw),'-f','f32le','-ar','24000','-ac','1','-'])
            samples=np.frombuffer(data,dtype='<f4')[800:5000]
            tone=np.fft.rfftfreq(len(samples),1/24000)[np.argmax(np.abs(np.fft.rfft(samples)))]
            self.assertAlmostEqual(tone,440 if cue.text=='one' else 880,delta=8)
        processes=[s.proc for s in self.pool.sessions]
        self.generate(p)
        self.assertEqual([s.proc for s in self.pool.sessions],processes)
        self.assertEqual(len([e for e in self.events() if e[0]=='loaded']),2)

    def test_four_workers_respect_requested_global_capacity(self):
        p=self.project(8);p.vieneu_workers=4
        result=self.generate(p,parallel_segments=[(i,i+2) for i in range(0,16,2)])
        self.assertEqual(result['missing_count'],0)
        self.assertEqual(self.peak(),4)
        self.assertEqual(len([e for e in self.events() if e[0]=='loaded']),4)

    def test_limit_counts_only_new_unique_mp3s_and_resumes_next_cues(self):
        p=self.project(8,3);segments=[(0,4),(4,8),(8,12),(12,16)]
        for expected_new,expected_deferred,expected_rows in [(3,5,3),(3,2,6),(2,0,8),(0,0,8)]:
            result=self.generate(p,parallel_segments=segments)
            self.assertEqual(result['new_count'],expected_new)
            self.assertEqual(result['deferred_count'],expected_deferred)
            self.assertEqual(len(result['rows']),expected_rows)
            self.assertEqual(result['missing_count'],0);self.assertFalse(result['tts_errors'])
        self.assertEqual(len([e for e in self.events() if e[0]=='begin']),8)
        self.assertEqual(len([e for e in self.events() if e[0]=='loaded']),2)

    def test_duplicates_share_quota_and_unattempted_cues_are_not_errors(self):
        p=self.project(4,1);p.cues[1].text='one'
        result=self.generate(p)
        self.assertEqual(result['new_count'],1);self.assertEqual(len(result['rows']),2)
        self.assertEqual(result['deferred_ids'],['2','3'])
        self.assertFalse(result['tts_errors']);self.assertEqual(result['missing_count'],0)

    def test_cancel_terminates_all_workers_and_cleans_partial_audio(self):
        p=self.project(2);p.cues[0].text=p.cues[1].text='wait';p.cues[1].voice=VIENEU_PREFIX+'Hải Đăng'
        timer=threading.Timer(.4,self.cancel.set);timer.start();began=time.monotonic()
        try:
            with self.assertRaises(InterruptedError):self.generate(p)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-began,3)
        self.assertFalse(self.pool.ready);self.assertFalse(self.pool.sessions)
        self.assertFalse(list(self.cache.glob('*.partial.*')))

    def test_fatal_worker_aborts_another_waiting_request(self):
        p=self.project(2);p.cues[0].text='fatal';p.cues[1].text='wait';began=time.monotonic()
        with self.assertRaises(TTSServiceError):self.generate(p)
        self.assertLess(time.monotonic()-began,3);self.assertFalse(self.pool.ready)
        self.assertFalse(list(self.cache.glob('*.partial.*')))

    def test_project_defaults_validation_and_voice_cache_identity(self):
        p=Project.from_dict(dict(version=1));self.assertEqual((p.vieneu_workers,p.tts_cue_limit),(1,0))
        p=self.project(1);before=signature(p);key=raw_key(p.cues[0],p)
        p.vieneu_workers=4;p.tts_cue_limit=50
        self.assertEqual(signature(p),before);self.assertEqual(raw_key(p.cues[0],p),key)
        self.assertEqual(Project.from_dict(p.to_dict()).vieneu_workers,4)
        for name,values in [('vieneu_workers',[0,5,True,1.5]),('tts_cue_limit',[-1,True,'50'])]:
            for value in values:
                with self.assertRaises(ValueError):Project.from_dict(dict(version=1,**{name:value}))

    def test_ui_keeps_edge_and_local_concurrency_separate(self):
        w=Window()
        try:
            w.p=Project(voice=VIENEU_PREFIX+'Trúc Ly',tts_workers=6,tts_retry_mode='per_cue',vieneu_workers=2,tts_cue_limit=50)
            w.load_controls();self.assertTrue(w.workers.isEnabled());self.assertEqual(w.workers.maximum(),4)
            self.assertEqual(w.workers.value(),2);self.assertEqual(w.cue_limit.value(),50)
            w.workers.setValue(3);self.assertEqual(w.p.vieneu_workers,3);self.assertEqual(w.p.tts_workers,6)
            w.voice.setCurrentIndex(w.voice.findData('vi-VN-NamMinhNeural'))
            self.assertEqual(w.workers.value(),6);self.assertTrue(w.tts_mode.isEnabled())
            w.voice.setCurrentIndex(w.voice.findData(VIENEU_PREFIX+'Trúc Ly'))
            self.assertEqual(w.workers.value(),3);self.assertFalse(w.tts_mode.isEnabled())
        finally:w.dirty=False;w.close();w.deleteLater()

    def test_sequential_batches_share_one_click_quota(self):
        w=Window();results=[]
        try:
            w.p=self.project(4,3);w.p.video='fixture.mp4';w.cache=self.cache
            w.local_tts_session=self.pool
            def start(fn,done,label):results.append(fn(self.cancel,lambda *a:None))
            with patch.object(w,'save',return_value=True),patch('studio.ui.check_project'),patch.object(w,'start_job',side_effect=start):
                w.run_voice_queue([(0,4),(4,8)],parallel=False)
            result=results[0];self.assertEqual(result['new_count'],3)
            self.assertEqual(result['deferred_count'],1);self.assertEqual(result['deferred_ids'],['3'])
            self.assertEqual(result['queue_completed'],1)
            self.assertEqual(len(list(self.cache.glob('*.mp3'))),3)
        finally:w.dirty=False;w.close();w.deleteLater()

    def test_batch_dialog_exposes_local_workers_and_limit(self):
        w=Window();errors=[]
        try:
            w.p=self.project(4,3);w.p.video='fixture.mp4';w.load_controls()
            def inspect():
                dialog=self.app.activeModalWidget()
                try:
                    workers=dialog.findChild(QSpinBox,'batchVoiceWorkers');quota=dialog.findChild(QSpinBox,'batchVoiceCueLimit')
                    self.assertTrue(workers.isEnabled());self.assertEqual(workers.maximum(),4)
                    self.assertEqual(workers.value(),2);self.assertEqual(quota.value(),3)
                    workers.setValue(4);quota.setValue(5)
                    next(b for b in dialog.findChildren(QPushButton) if b.text()=='Chạy các lượt đã chọn').click()
                except BaseException as e:errors.append(e);dialog.reject()
            QTimer.singleShot(0,inspect)
            with patch.object(w,'run_voice_queue') as run:w.show_batches();run.assert_called_once()
            if errors:raise errors[0]
            self.assertEqual(w.p.vieneu_workers,4);self.assertEqual(w.p.tts_cue_limit,5)
        finally:w.dirty=False;w.close();w.deleteLater()


if __name__=='__main__':unittest.main()
