from pathlib import Path
import asyncio
import json
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import edge_tts
from edge_tts.exceptions import NoAudioReceived
from studio.core import Cue,Project,generate_voices,raw_key
from studio.tts import TTSCooldown,TTSServiceError


class RecoveryTests(unittest.TestCase):
    def test_rate_limit_resets_warmup_before_increasing_connections(self):
        gate=TTSCooldown(2,spacing=0);cancel=threading.Event()
        with patch('studio.tts.time.monotonic',return_value=100):
            for _ in range(3):
                token=gate.acquire(cancel);gate.success(token)
            token=gate.acquire(cancel);self.assertEqual(gate.fail(token,'HTTP 429'),5)
        with patch('studio.tts.time.monotonic',return_value=106):
            token=gate.acquire(cancel);gate.success(token)
            self.assertEqual(gate.limit,1);self.assertEqual(gate.healthy,1)

    def test_inflight_empty_wave_gets_one_pause_not_multiple_recovery_failures(self):
        gate=TTSCooldown(6,spacing=0);gate.limit=6;cancel=threading.Event()
        with patch('studio.tts.time.monotonic',return_value=100):
            wave=[gate.acquire(cancel) for _ in range(6)]
            self.assertIsNone(gate.no_audio(wave[0]))
            self.assertEqual(gate.no_audio(wave[1]),10)
            for token in wave[2:]:self.assertIsNone(gate.no_audio(token))
            self.assertEqual((gate.recovery_round,gate.until,gate.active,gate.limit),(1,110,0,1))
            self.assertIsNone(gate.error)
        with patch('studio.tts.time.monotonic',return_value=111):
            token=gate.acquire(cancel);self.assertEqual(gate.no_audio(token),20)
            self.assertEqual(gate.until,131)
        with patch('studio.tts.time.monotonic',return_value=132):
            token=gate.acquire(cancel);self.assertEqual(gate.no_audio(token),40)
            self.assertEqual(gate.until,172)
        with patch('studio.tts.time.monotonic',return_value=173):
            token=gate.acquire(cancel)
            with self.assertRaisesRegex(TTSServiceError,'3 đợt nghỉ'):gate.no_audio(token)
        self.assertEqual(gate.active,0)

    def test_transient_burst_after_six_successes_recovers_and_keeps_cached_audio(self):
        # The service recovers after 30 virtual seconds. No real 10/20s sleeps.
        state=dict(clock=0.,calls=0,active=0,peak=0,warm_started=0);lock=threading.Lock();delays=[];both_warm=threading.Event()
        class VirtualRecovery(TTSCooldown):
            def __init__(self,capacity):super().__init__(capacity,spacing=0)
            def no_audio(self,generation):
                delay=super().no_audio(generation)
                if delay is not None:
                    delays.append(delay)
                    with lock:state['clock']+=delay
                with self.lock:self.until=0;self.spacing=0
                return 0 if delay is not None else None
        p=Project(duration=14,tts_workers=6,cues=[Cue(i,i+.5,f'Câu {i}') for i in range(13)])
        original=p.to_dict()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);audio_file=root/'tone.mp3'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.1',str(audio_file)],check=True)
            audio=audio_file.read_bytes();cache=root/'cache';cache.mkdir()
            cached=cache/(raw_key(p.cues[0],p)+'.mp3');cached.write_bytes(audio)
            def client(text,voice,**kwargs):
                async def save(path):
                    with lock:
                        state['calls']+=1;number=state['calls'];clock=state['clock']
                        state['active']+=1;state['peak']=max(state['peak'],state['active'])
                    try:
                        # Synchronize the two healthy requests after warmup instead
                        # of relying on OS scheduling / FFprobe startup timings.
                        if number in (5,6):
                            with lock:
                                state['warm_started']+=1
                                if state['warm_started']==2:both_warm.set()
                            deadline=time.monotonic()+2
                            while not both_warm.is_set():
                                if time.monotonic()>deadline:raise AssertionError('Second healthy connection was not admitted')
                                await asyncio.sleep(.005)
                        await asyncio.sleep(.01)
                        if number>6 and clock<30:raise NoAudioReceived('temporary burst')
                        Path(path).write_bytes(audio)
                    finally:
                        with lock:state['active']-=1
                return SimpleNamespace(save=save)
            gate=VirtualRecovery(2)
            with patch.object(edge_tts,'Communicate',side_effect=client),patch('studio.core.TTSCooldown',return_value=gate) as factory,patch('studio.tts.retry_delay',return_value=0):
                result=generate_voices(p,cache,threading.Event(),lambda *a:None,mix=False,parallel_segments=[(0,5),(5,10),(10,14)])
            factory.assert_called_once_with(2)
            self.assertEqual(delays,[10,20]);self.assertIsNone(gate.error)
            self.assertGreater(state['peak'],1);self.assertLessEqual(state['peak'],2)
            self.assertEqual(result['missing_count'],0);self.assertEqual(len(result['rows']),13)
            self.assertEqual(cached.read_bytes(),audio);self.assertEqual(p.to_dict(),original)
            self.assertEqual(json.loads((cache/'voice-errors.json').read_text()),{})
            self.assertFalse(list(cache.glob('*.partial.mp3')))

    def test_cancel_during_shared_pause_is_prompt(self):
        class FastAdmission(TTSCooldown):
            def no_audio(self,generation):
                delay=super().no_audio(generation)
                with self.lock:self.spacing=0;self.next_start=0
                return delay
        gate=FastAdmission(1,spacing=0);cancel=threading.Event();timers=[];calls=[];messages=[]
        p=Project(duration=3,tts_workers=1,cues=[Cue(i,i+.5,f'Câu {i}') for i in range(3)])
        async def save(path):calls.append(path);raise NoAudioReceived('empty')
        def report(n,message):
            messages.append(message)
            if 'nghỉ chung 10s' in message:
                timer=threading.Timer(.1,cancel.set);timers.append(timer);timer.start()
        started=time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as folder,patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)),patch('studio.core.TTSCooldown',return_value=gate):
                with self.assertRaises(InterruptedError):generate_voices(p,folder,cancel,report,mix=False)
                self.assertFalse(list(Path(folder).glob('*.partial.mp3')))
        finally:
            for timer in timers:timer.cancel()
        self.assertTrue(any('nghỉ chung 10s' in message for message in messages))
        self.assertEqual(len(calls),2);self.assertLess(time.monotonic()-started,1)


if __name__=='__main__':unittest.main()
