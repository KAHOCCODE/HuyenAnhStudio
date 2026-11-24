import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio import core
from studio.core import Cue, Project, generate_voices, preview_voice
from studio.local_tts import LocalTTSSession
from studio.tts import TTSServiceError
from studio.voices import VIENEU_PREFIX
from studio.ui import Window
from studio.voice_preview_ui import VoicePreviewDialog


WORKER = '''import json,math,struct,sys,time,wave
from pathlib import Path
log=Path(__file__).with_suffix('.log')
with log.open('a') as f:f.write('loaded\\n')
for event in [dict(event='phase',message='Đang kiểm tra tệp mô hình: model.onnx'),dict(event='download',filename='model.onnx',downloaded=1048576,total=2097152),dict(event='phase',message='Đang nạp mô hình CPU'),dict(event='ready')]:
    print(json.dumps(event),flush=True)
for line in sys.stdin:
    row=json.loads(line)
    with log.open('a',encoding='utf-8') as f:f.write(row['voice']+'|'+row['text']+'\\n')
    if row['text']=='wait':time.sleep(30)
    with wave.open(row['target'],'wb') as out:
        out.setparams((1,2,24000,0,'NONE','not compressed'))
        out.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*440*i/24000))) for i in range(12000)))
    print(json.dumps(dict(event='done')),flush=True)
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class VoicePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.worker=self.root/'worker.py'
        self.worker.write_text(WORKER,encoding='utf-8')
        self.session=LocalTTSSession(python=sys.executable,worker=self.worker)
        self.cancel=threading.Event()

    def tearDown(self):
        self.session.close()
        self.temp.cleanup()

    def logs(self):
        return self.worker.with_suffix('.log').read_text(encoding='utf-8').splitlines()

    def wait_ui(self, predicate, timeout=5):
        end=time.monotonic()+timeout
        while not predicate():
            if time.monotonic()>end:self.fail('UI job did not finish')
            self.app.processEvents()
            QTest.qWait(10)

    def test_same_process_serves_preview_voice_changes_and_generation(self):
        messages=[]
        report=lambda _, message:messages.append(message)
        first=preview_voice('Một câu tùy ý',VIENEU_PREFIX+'Trúc Ly',0,0,self.root/'samples',self.cancel,report,local_session=self.session)
        proc=self.session.proc
        self.assertTrue(self.session.ready)
        self.assertIsNone(proc.poll())
        second=preview_voice('Một câu tùy ý',VIENEU_PREFIX+'Hải Đăng',0,2.5,self.root/'samples',self.cancel,report,local_session=self.session)
        self.assertIs(self.session.proc,proc)
        p=Project(duration=3,voice=VIENEU_PREFIX+'Trúc Ly',cues=[Cue(0,1,'Lồng tiếng phim')])
        result=generate_voices(p,self.root/'film',self.cancel,report,mix=False,local_session=self.session)
        self.assertEqual(result['missing_count'],0)
        self.assertEqual(self.logs().count('loaded'),1)
        self.assertEqual(len(self.logs()),4)
        self.assertTrue(Path(first['path']).is_file())
        self.assertTrue(Path(second['path']).is_file())
        self.assertTrue(any('1.0/2.0 MB' in m and '50%' in m for m in messages))
        self.assertTrue(any('nạp mô hình CPU' in m for m in messages))
        again=preview_voice('Một câu tùy ý',VIENEU_PREFIX+'Hải Đăng',0,2.5,self.root/'samples',self.cancel,report,local_session=self.session)
        self.assertEqual(again['path'],second['path'])
        self.assertEqual(len(self.logs()),4)
        self.session.close()
        self.assertIsNotNone(proc.poll())
        self.assertFalse(self.session.ready)
        self.assertTrue(Path(first['path']).is_file())

    def test_cancel_discards_inflight_response_and_can_restart_shared_session(self):
        preview_voice('Giữ câu đã xong',VIENEU_PREFIX+'Trúc Ly',0,0,self.root/'samples',self.cancel,lambda *a:None,local_session=self.session)
        proc=self.session.proc
        timer=threading.Timer(.15,self.cancel.set)
        timer.start()
        try:
            with self.assertRaises(InterruptedError):
                preview_voice('wait',VIENEU_PREFIX+'Hải Đăng',0,0,self.root/'samples',self.cancel,lambda *a:None,local_session=self.session)
        finally:timer.cancel()
        self.assertIsNotNone(proc.poll())
        self.assertFalse(self.session.ready)
        self.assertFalse(list((self.root/'samples').glob('*.partial.*')))
        self.cancel.clear()
        preview_voice('Câu mới',VIENEU_PREFIX+'Hải Đăng',0,0,self.root/'samples',self.cancel,lambda *a:None,local_session=self.session)
        self.assertTrue(self.session.ready)
        self.assertIsNot(self.session.proc,proc)
        self.assertEqual(self.logs().count('loaded'),2)

    def test_audition_bounds_prevent_accidental_bulk_generation(self):
        for text,rate,pitch in [('',0,0),('A'*501,0,0),('Câu đọc',101,0),('Câu đọc',0,7)]:
            with self.assertRaises((ValueError,RuntimeError)):
                preview_voice(text,VIENEU_PREFIX+'Trúc Ly',rate,pitch,self.root/'samples',self.cancel,lambda *a:None,local_session=self.session)
        self.assertIsNone(self.session.proc)

    def window(self):
        window=Window()
        window.cache_root=self.root/'app-cache'
        window.local_tts_session=self.session
        return window

    def test_dialog_listens_without_video_or_srt_and_does_not_modify_project(self):
        window=self.window()
        before=window.p.to_dict()
        dialog=VoicePreviewDialog(window,voice=VIENEU_PREFIX+'Trúc Ly',text='Câu nghe thử riêng')
        try:
            with patch.object(window,'save',side_effect=AssertionError('Preview must not save project')),patch.object(dialog.player,'play') as play:
                dialog.listen()
                self.wait_ui(lambda:not window.busy)
                self.assertEqual(play.call_count,1)
                self.assertTrue(Path(dialog.player.source().toLocalFile()).is_file())
                self.assertEqual(dialog.player.playbackRate(),1)
                dialog.voice.setCurrentIndex(dialog.voice.findData(VIENEU_PREFIX+'Hải Đăng'))
                dialog.listen()
                self.wait_ui(lambda:not window.busy)
                self.assertEqual(play.call_count,2)
            self.assertEqual(window.p.to_dict(),before)
            self.assertFalse(window.dirty)
            self.assertEqual(window.undo,[])
            self.assertEqual(self.logs().count('loaded'),1)
            dialog.reject()
            self.assertTrue(self.session.ready)
            proc=self.session.proc
            window.release_local_tts()
            self.assertIsNotNone(proc.poll())
        finally:
            dialog.deleteLater()
            window.dirty=False;window.close();window.deleteLater()

    def test_dialog_reports_failure_inline_and_reenables_controls(self):
        window=self.window()
        dialog=VoicePreviewDialog(window,text='Xin chào')
        try:
            with patch('studio.voice_preview_ui.preview_voice',side_effect=TTSServiceError('Thiếu bộ giọng')),patch.object(window,'error') as error:
                dialog.listen()
                self.wait_ui(lambda:not window.busy)
                error.assert_not_called()
            self.assertIn('Thiếu bộ giọng',dialog.status.text())
            self.assertTrue(dialog.play.isEnabled())
            self.assertFalse(dialog.running)
        finally:
            dialog.reject();dialog.deleteLater();window.dirty=False;window.close();window.deleteLater()

    def test_close_while_loading_cancels_before_dialog_is_destroyed(self):
        window=self.window()
        dialog=VoicePreviewDialog(window,voice=VIENEU_PREFIX+'Trúc Ly',text='wait')
        try:
            dialog.show();dialog.listen()
            self.wait_ui(lambda:self.session.ready)
            proc=self.session.proc
            dialog.close()
            self.assertTrue(dialog.close_after_job)
            self.wait_ui(lambda:not window.busy)
            self.assertFalse(dialog.isVisible())
            self.assertIsNotNone(proc.poll())
        finally:
            if window.busy:
                window.cancel_job();self.wait_ui(lambda:not window.busy)
            dialog.deleteLater();window.dirty=False;window.close();window.deleteLater()

    def test_only_explicit_apply_changes_project_and_close_releases_model(self):
        window=self.window()
        dialog=VoicePreviewDialog(window)
        try:
            dialog.voice.setCurrentIndex(dialog.voice.findData(VIENEU_PREFIX+'Hải Đăng'))
            dialog.pitch.setValue(2.5);dialog.rate.setValue(-10)
            self.assertEqual(window.p.voice,'vi-VN-NamMinhNeural')
            dialog.apply_to_project()
            self.assertEqual((window.p.voice,window.p.tts_pitch,window.p.tts_rate),(VIENEU_PREFIX+'Hải Đăng',2.5,-10))
            self.assertEqual(len(window.undo),1)
            self.session.speak('Xin chào',VIENEU_PREFIX+'Hải Đăng',self.root/'sample.wav',self.cancel)
            proc=self.session.proc
            window.dirty=False;window.close()
            self.assertIsNotNone(proc.poll())
        finally:
            dialog.deleteLater();window.dirty=False;window.close();window.deleteLater()

    def test_download_progress_preserves_downloader_arguments_and_result(self):
        path=core.ROOT/'tools'/'vieneu_worker.py'
        spec=importlib.util.spec_from_file_location('audition_worker_test',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calls=[];events=[]
        def download(*args,**kwargs):
            calls.append((args,kwargs))
            with kwargs['tqdm_class'](total=4*1048576,initial=1048576,desc='model') as progress:
                progress.update(3*1048576)
            return 'cached-model-path'
        hub=SimpleNamespace(hf_hub_download=download)
        with patch.dict(sys.modules,{'huggingface_hub':hub}):
            module.install_download_progress(events.append)
            result=hub.hf_hub_download('author/model','sub/model.onnx',subfolder='fp32',token='test-secret')
        self.assertEqual(result,'cached-model-path')
        self.assertEqual(calls[0][0],('author/model','sub/model.onnx'))
        self.assertEqual(calls[0][1]['token'],'test-secret')
        self.assertEqual(calls[0][1]['subfolder'],'fp32')
        transfers=[e for e in events if e['event']=='download']
        self.assertEqual(transfers[0]['downloaded'],1048576)
        self.assertEqual(transfers[-1]['downloaded'],4*1048576)
        self.assertEqual(transfers[-1]['total'],4*1048576)
        self.assertNotIn('test-secret',json.dumps(events))
        self.assertEqual(events[-1]['event'],'phase')


if __name__=='__main__':unittest.main()
