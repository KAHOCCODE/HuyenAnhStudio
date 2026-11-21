import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import aiohttp
import edge_tts
from edge_tts.exceptions import NoAudioReceived
from studio.core import Cue,Project,generate_voices,raw_key,signature
from studio.tts import TTSCooldown,TTSServiceError,TTSRequestError,context,fetch_voice


class ModeTests(unittest.TestCase):
    def tearDown(self):context.__dict__.clear()

    def test_strategy_roundtrip_does_not_invalidate_audio_cache(self):
        p=Project(duration=2,cues=[Cue(0,1,'Xin chào')]);before=signature(p);key=raw_key(p.cues[0],p)
        p.tts_retry_mode='per_cue';p.tts_workers=6
        self.assertEqual(signature(p),before);self.assertEqual(raw_key(p.cues[0],p),key)
        self.assertEqual(Project.from_dict(p.to_dict()).tts_retry_mode,'per_cue')
        self.assertEqual(Project.from_dict({'version':1}).tts_retry_mode,'adaptive')
        with self.assertRaises(ValueError):Project.from_dict({'version':1,'tts_retry_mode':'unknown'})

    def test_per_cue_gate_does_not_turn_empty_responses_into_global_outage(self):
        gate=TTSCooldown(6,spacing=0,mode='per_cue');cancel=threading.Event()
        token=gate.acquire(cancel);gate.success(token)
        self.assertEqual(gate.limit,6);self.assertEqual(gate.max_attempts,9)
        for _ in range(20):
            token=gate.acquire(cancel);self.assertIsNone(gate.no_audio(token));gate.empty_cue_failed()
        self.assertIsNone(gate.error);self.assertEqual((gate.limit,gate.until,gate.active),(6,0,0))

    def test_ninth_attempt_can_recover_and_exhaustion_never_sleeps_after_last(self):
        gate=TTSCooldown(1,spacing=0,mode='per_cue');context.gate=gate;calls=[]
        async def no_wait(*args):pass
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'sample.mp3'
            async def save(path):
                calls.append(path)
                if len(calls)<9:raise NoAudioReceived('empty')
                Path(path).write_bytes(b'audio')
            with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)),patch('studio.tts.wait_retry',side_effect=no_wait) as wait:
                asyncio.run(fetch_voice('Xin chào','vi-VN-NamMinhNeural',0,target,threading.Event()))
            self.assertEqual(len(calls),9);self.assertEqual(wait.call_count,8);self.assertEqual(target.read_bytes(),b'audio')
            async def fail(path):raise NoAudioReceived('empty')
            with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=fail)) as request,patch('studio.tts.wait_retry',side_effect=no_wait) as wait:
                with self.assertRaisesRegex(TTSRequestError,'9 lần'):
                    asyncio.run(fetch_voice('Xin chào','vi-VN-NamMinhNeural',0,target,threading.Event()))
            self.assertEqual(request.call_count,9);self.assertEqual(wait.call_count,8);self.assertFalse(target.exists())
        self.assertIsNone(gate.error);self.assertEqual(gate.active,0)

    def test_six_connections_shared_across_batches_and_failed_cues_do_not_stop_others(self):
        p=Project(duration=13,tts_workers=6,tts_retry_mode='per_cue',cues=[Cue(i,i+.5,f'Câu {i}') for i in range(12)])
        calls=Counter();voices=set();lock=threading.Lock();state=dict(active=0,peak=0,warm=0,first_good=False);all_warm=threading.Event()
        gate=TTSCooldown(6,spacing=0,mode='per_cue')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);audio_file=root/'tone.mp3'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.1',str(audio_file)],check=True)
            audio=audio_file.read_bytes();cache=root/'cache'
            def client(text,voice,**kwargs):
                async def save(path):
                    with lock:
                        calls[text]+=1;voices.add(voice);state['active']+=1;state['peak']=max(state['peak'],state['active'])
                        first_good=text not in ('Câu 0','Câu 1') and not state['first_good']
                        if first_good:state['first_good']=True
                    try:
                        if text in ('Câu 0','Câu 1'):raise NoAudioReceived('empty')
                        if not first_good:
                            with lock:
                                state['warm']+=1
                                if state['warm']>=6:all_warm.set()
                            deadline=time.monotonic()+3
                            while not all_warm.is_set():
                                if time.monotonic()>deadline:raise AssertionError('Six request slots were not shared correctly')
                                await asyncio.sleep(.005)
                        Path(path).write_bytes(audio)
                    finally:
                        with lock:state['active']-=1
                return SimpleNamespace(save=save)
            with patch.object(edge_tts,'Communicate',side_effect=client),patch('studio.core.TTSCooldown',return_value=gate),patch('studio.tts.retry_delay',return_value=0):
                result=generate_voices(p,cache,threading.Event(),lambda *a:None,mix=False,parallel_segments=[(0,4),(4,8),(8,13)])
            self.assertEqual(state['peak'],6);self.assertEqual(state['active'],0);self.assertIsNone(gate.error)
            self.assertEqual(calls['Câu 0'],9);self.assertEqual(calls['Câu 1'],9)
            self.assertTrue(all(calls[f'Câu {i}']==1 for i in range(2,12)))
            self.assertEqual(result['missing_count'],2);self.assertEqual(len(result['rows']),10)
            self.assertEqual(voices,{p.voice});self.assertEqual(len(json.loads((cache/'voice-errors.json').read_text())),2)
            self.assertFalse(list(cache.glob('*.partial.mp3')))

    def test_auth_failure_still_stops_before_sending_many_requests(self):
        p=Project(duration=20,tts_workers=6,tts_retry_mode='per_cue',cues=[Cue(i,i+.5,f'Câu {i}') for i in range(20)])
        async def save(path):raise aiohttp.WSServerHandshakeError(None,(),status=403,message='forbidden')
        with tempfile.TemporaryDirectory() as folder,patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)) as request:
            with self.assertRaisesRegex(TTSServiceError,'HTTP 403'):generate_voices(p,folder,threading.Event(),lambda *a:None,mix=False)
        self.assertEqual(request.call_count,1)

    def test_mode_controls_save_and_undo_with_old_project(self):
        from PySide6.QtWidgets import QApplication
        from studio.ui import Window
        app=QApplication.instance() or QApplication([]);w=Window()
        try:
            w.p=Project(tts_workers=6,tts_retry_mode='per_cue');w.load_controls()
            self.assertEqual(w.workers.maximum(),6);self.assertEqual(w.workers.value(),6)
            w.tts_mode.setCurrentIndex(w.tts_mode.findData('adaptive'))
            self.assertEqual(w.p.tts_retry_mode,'adaptive');self.assertEqual(w.p.tts_workers,2)
            w.undo_action();self.assertEqual(w.p.tts_retry_mode,'per_cue');self.assertEqual(w.workers.value(),6)
        finally:w.dirty=False;w.close_cpu();w.close();w.deleteLater()


if __name__=='__main__':unittest.main()
