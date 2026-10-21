import asyncio
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import aiohttp
import edge_tts
from studio.core import Cue,Project,generate_voices,raw_key
from studio.tts import TTSCooldown,TTSServiceError,context,edge_client,failure_reason,fetch_voice


def http_error(status,**headers):
    return aiohttp.WSServerHandshakeError(None,(),status=status,message='Invalid response status',headers=headers)


class ImmediateCooldown(TTSCooldown):
    """Keep production admission/recovery behavior, skip wall-clock backoff in tests."""
    def __init__(self,capacity=6):super().__init__(capacity,spacing=0)
    def fail(self,*args,**kwargs):
        delay=super().fail(*args,**kwargs)
        with self.lock:self.until=0
        return delay


class TTSTests(unittest.TestCase):
    def tearDown(self):context.__dict__.clear()

    def test_old_client_requires_dependency_update(self):
        with patch.object(edge_tts,'__version__','7.2.8'):
            with self.assertRaisesRegex(TTSServiceError,'install.cmd'):edge_client()

    def test_one_failed_wave_has_one_delay_and_stale_success_cannot_reopen(self):
        gate=TTSCooldown(6,spacing=0);cancel=threading.Event()
        with patch('studio.tts.time.monotonic',return_value=100):
            first=gate.acquire(cancel);self.assertEqual(gate.active,1)
            gate.success(first);self.assertEqual(gate.limit,2)
            gate.limit=6
            wave=[gate.acquire(cancel) for _ in range(6)]
            self.assertEqual(gate.fail(wave[0],'HTTP 429'),5)
            deadline=gate.until
            for token in wave[1:5]:self.assertIsNone(gate.fail(token,'HTTP 429'))
            gate.success(wave[5])
            self.assertEqual((gate.failures,gate.limit,gate.active,gate.until),(1,1,0,deadline))
        with patch('studio.tts.time.monotonic',return_value=106):
            token=gate.acquire(cancel)
            self.assertEqual(gate.fail(token,'HTTP 429'),10)
        with patch('studio.tts.time.monotonic',return_value=117):
            token=gate.acquire(cancel)
            with self.assertRaisesRegex(TTSServiceError,'3 lần'):gate.fail(token,'HTTP 429')
        self.assertEqual(gate.active,0)

    def test_reason_has_status_and_retry_after_without_request_tokens(self):
        error=http_error(429,**{'Retry-After':'17'})
        self.assertEqual(failure_reason(error),('Edge TTS trả HTTP 429.',False,17))
        reason,fatal,_=failure_reason(http_error(403))
        self.assertTrue(fatal);self.assertIn('HTTP 403',reason);self.assertIn('install.cmd',reason)
        self.assertNotIn('wss://',reason)

    def test_repeated_outage_tries_three_times_and_does_not_sleep_after_last(self):
        reports=[];gate=ImmediateCooldown();context.gate=gate;context.report=reports.append
        calls=[]
        async def save(path):calls.append(path);raise http_error(503)
        with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)):
            with self.assertRaisesRegex(TTSServiceError,'HTTP 503'):
                asyncio.run(fetch_voice('Xin chào','vi-VN-NamMinhNeural',0,'unused.mp3',threading.Event()))
        self.assertEqual(len(calls),3);self.assertEqual(len(reports),2)
        self.assertIn('5s',reports[0]);self.assertIn('10s',reports[1]);self.assertEqual(gate.active,0)

    def test_cancellation_closes_active_request_and_interrupts_shared_wait(self):
        gate=TTSCooldown();context.gate=gate;cancel=threading.Event();closed=threading.Event()
        async def save(path):
            try:await asyncio.sleep(30)
            finally:closed.set()
        timer=threading.Timer(.1,cancel.set);timer.start();began=time.monotonic()
        try:
            with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)):
                with self.assertRaises(InterruptedError):asyncio.run(fetch_voice('Xin chào','vi-VN-NamMinhNeural',0,'unused.mp3',cancel))
        finally:timer.cancel()
        self.assertTrue(closed.is_set());self.assertLess(time.monotonic()-began,1);self.assertEqual(gate.active,0)
        cancel.clear();gate.until=time.monotonic()+60
        timer=threading.Timer(.1,cancel.set);timer.start();began=time.monotonic()
        try:
            with self.assertRaises(InterruptedError):gate.acquire(cancel)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-began,1)

    def test_invalid_parameter_does_not_retry_or_cool_down_other_cues(self):
        gate=ImmediateCooldown();context.gate=gate
        with patch.object(edge_tts,'Communicate',side_effect=ValueError('invalid voice')) as client:
            with self.assertRaisesRegex(ValueError,'invalid voice'):
                asyncio.run(fetch_voice('Xin chào','bad',0,'unused.mp3',threading.Event()))
        self.assertEqual(client.call_count,1);self.assertEqual((gate.active,gate.failures,gate.until),(0,0,0))

    def test_403_stops_large_queue_after_one_request_preserving_cached_audio(self):
        p=Project(duration=2000,tts_workers=6,cues=[Cue(i,i+.5,f'Câu {i}') for i in range(1615)])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cached=root/(raw_key(p.cues[0],p)+'.mp3');cached.write_bytes(b'existing audio')
            calls=[]
            async def save(path):
                calls.append(path);Path(path).write_bytes(b'partial');raise http_error(403)
            with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)):
                began=time.monotonic()
                with self.assertRaisesRegex(TTSServiceError,'HTTP 403'):
                    generate_voices(p,root,threading.Event(),lambda *a:None,mix=False,parallel_segments=[(i*300,(i+1)*300) for i in range(7)])
            self.assertEqual(len(calls),1);self.assertLess(time.monotonic()-began,2)
            self.assertEqual(cached.read_bytes(),b'existing audio');self.assertFalse(list(root.glob('*.partial.mp3')))

    def test_shared_limit_across_seven_batches_recovers_and_reuses_audio(self):
        p=Project(duration=70,tts_workers=3,cues=[Cue(i*2,i*2+1,f'Câu {i}') for i in range(35)])
        gate=ImmediateCooldown(3);lock=threading.Lock();active=0;peak=0;calls=0;reports=[]
        async def save(path):
            nonlocal active,peak,calls
            with lock:active+=1;peak=max(peak,active);calls+=1;number=calls
            try:
                await asyncio.sleep(.01)
                if number==1:raise http_error(429)
                Path(path).write_bytes(b'new audio')
            finally:
                with lock:active-=1
        def row(c,*args):return dict(id=c.id,duration=.2,ok=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cached=root/(raw_key(p.cues[0],p)+'.mp3');cached.write_bytes(b'existing audio')
            with patch('studio.core.TTSCooldown',return_value=gate),patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)),patch('studio.core.probe',return_value={'duration':.2}),patch('studio.core.prepare_voice_row',side_effect=row):
                result=generate_voices(p,root,threading.Event(),lambda n,msg:reports.append(msg),mix=False,parallel_segments=[(i*10,(i+1)*10) for i in range(7)])
            self.assertEqual(len(result['rows']),35);self.assertEqual(result['tts_errors'],[])
            self.assertEqual(calls,35)  # 34 missing + one recovered request
            self.assertGreater(peak,1);self.assertLessEqual(peak,3)
            self.assertEqual(len([s for s in reports if 'Chờ chung' in s]),1)
            self.assertEqual(cached.read_bytes(),b'existing audio');self.assertEqual(len(list(root.glob('*.mp3'))),35)
            self.assertFalse(list(root.glob('*.partial.mp3')))
            # All files exist: running again never contacts Edge TTS.
            with patch('studio.core.fetch_voice') as request,patch('studio.core.prepare_voice_row',side_effect=row):
                again=generate_voices(p,root,threading.Event(),lambda *a:None,mix=False)
                request.assert_not_called();self.assertEqual(len(again['rows']),35)


if __name__=='__main__':unittest.main()
