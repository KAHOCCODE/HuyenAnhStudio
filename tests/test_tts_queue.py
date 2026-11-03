import asyncio
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import aiohttp
import edge_tts
from edge_tts.exceptions import NoAudioReceived
from studio import core
from studio.core import Cue,Project,generate_voices,raw_key
from studio.tts import TTSCooldown,TTSServiceError,check_voice_service,context,fetch_voice


class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.audio_path=Path(cls.tmp.name)/'short.mp3'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.1',str(cls.audio_path)],check=True)
        cls.audio=cls.audio_path.read_bytes()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def tearDown(self):context.__dict__.clear()

    def test_new_cues_finish_before_retry_and_metadata_avoids_second_probe(self):
        p=Project(duration=5,tts_workers=1,cues=[Cue(i,i+.5,word) for i,word in enumerate(('Câu lỗi','Câu hai','Câu ba','Câu bốn'))])
        original=p.to_dict();calls=[]
        def client(text,voice,**kwargs):
            self.assertEqual(kwargs['receive_timeout'],30)
            async def save(path):
                calls.append(text)
                if text=='Câu lỗi' and calls.count(text)<3:raise NoAudioReceived('empty')
                Path(path).write_bytes(self.audio)
            return SimpleNamespace(save=save)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(edge_tts,'Communicate',side_effect=client),patch('studio.tts.retry_delay',return_value=0),patch('studio.core.probe',wraps=core.probe) as probe:
                result=generate_voices(p,folder,threading.Event(),lambda *a:None,mix=False)
            self.assertEqual(calls,['Câu lỗi','Câu hai','Câu ba','Câu bốn','Câu lỗi','Câu lỗi'])
            self.assertEqual(probe.call_count,4)
            self.assertEqual(result['missing_count'],0);self.assertEqual(result['tts_errors'],[])
            self.assertEqual(json.loads((Path(folder)/'voice-errors.json').read_text()),{})
            with patch('studio.core.fetch_voice') as request,patch('studio.core.probe',wraps=core.probe) as probe:
                again=generate_voices(p,folder,threading.Event(),lambda *a:None,mix=False)
            request.assert_not_called();probe.assert_not_called();self.assertEqual(len(again['rows']),4)
            self.assertEqual(p.to_dict(),original)

    def test_cancel_waiting_retry_does_not_hold_worker_or_leave_partial(self):
        p=Project(duration=2,tts_workers=1,cues=[Cue(0,1,'Xin chào')]);cancel=threading.Event()
        async def save(path):Path(path).write_bytes(b'partial');raise NoAudioReceived('empty')
        timer=threading.Timer(.2,cancel.set);timer.start();start=time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as folder:
                with patch.object(edge_tts,'Communicate',return_value=SimpleNamespace(save=save)),patch('studio.tts.retry_delay',return_value=60):
                    with self.assertRaises(InterruptedError):generate_voices(p,folder,cancel,lambda *a:None,mix=False)
                self.assertFalse(list(Path(folder).glob('*.partial.mp3')))
                self.assertIn(p.cues[0].id,json.loads((Path(folder)/'voice-errors.json').read_text()))
        finally:timer.cancel()
        self.assertLess(time.monotonic()-start,1)

    def test_empty_wave_reduces_concurrency_and_recovers_gradually(self):
        gate=TTSCooldown(6,spacing=0);cancel=threading.Event();gate.limit=6
        with patch('studio.tts.time.monotonic',return_value=100):
            tokens=[gate.acquire(cancel) for _ in range(6)]
            self.assertIsNone(gate.no_audio(tokens[0]));self.assertEqual(gate.limit,1)
            self.assertEqual(gate.no_audio(tokens[1]),10);self.assertEqual(gate.until,110)
            for token in tokens[2:]:gate.success(token)
            self.assertEqual(gate.limit,1);self.assertEqual(gate.active,0);self.assertEqual(gate.recovery_round,1)
        for i in range(4):
            with patch('studio.tts.time.monotonic',return_value=111+i):
                token=gate.acquire(cancel);gate.success(token);self.assertEqual(gate.limit,2 if i==3 else 1)
        self.assertEqual(gate.recovery_round,0)

    def test_tls_verification_failure_stops_without_retries(self):
        context.gate=TTSCooldown()
        error=aiohttp.ClientConnectorCertificateError(SimpleNamespace(host='example.invalid',port=443,is_ssl=True),ssl.CertificateError('invalid'))
        with patch.object(edge_tts,'Communicate',side_effect=error) as request:
            with self.assertRaisesRegex(TTSServiceError,'chứng chỉ'):
                asyncio.run(fetch_voice('Xin chào','vi-VN-NamMinhNeural',0,'unused.mp3',threading.Event()))
        self.assertEqual(request.call_count,1);self.assertEqual(context.gate.active,0)

    def test_diagnostic_compares_both_voices_without_switching_or_saving(self):
        paths=[];voices=[]
        def client(text,voice,**kwargs):
            voices.append(voice)
            async def save(path):
                paths.append(Path(path))
                if voice=='vi-VN-NamMinhNeural':raise NoAudioReceived('empty')
                Path(path).write_bytes(self.audio)
            return SimpleNamespace(save=save)
        with patch.object(edge_tts,'Communicate',side_effect=client):result=check_voice_service(threading.Event(),lambda *a:None)
        self.assertEqual(voices,['vi-VN-NamMinhNeural','vi-VN-HoaiMyNeural'])
        self.assertEqual([r['ok'] for r in result['voices']],[False,True])
        self.assertTrue(all(not p.exists() and not p.parent.exists() for p in paths))


if __name__=='__main__':unittest.main()
