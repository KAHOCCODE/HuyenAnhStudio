import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtWidgets import QApplication
from studio import core
from studio.core import Cue, Project, generate_voices, raw_key, synthesis_key, signature, probe, remove_cached_voice
from studio.local_tts import LocalTTSSession
from studio.tts import TTSServiceError
from studio.voices import VOICES, VIENEU_PREFIX, LOCAL_PRESETS
from studio.ui import Window


# A real cancellable pipe process and PCM output, without model downloads/network.
WORKER = '''import json, math, struct, sys, time, wave
from pathlib import Path
log=Path(__file__).with_suffix('.log')
with log.open('a') as f:f.write('loaded\\n')
print(json.dumps({'event':'ready'}),flush=True)
for line in sys.stdin:
    row=json.loads(line)
    with log.open('a') as f:f.write(row['voice']+'|'+row['text']+'\\n')
    if row['text']=='wait':time.sleep(20)
    if row['text']=='fail':
        print(json.dumps({'event':'error','message':'invalid audio'}),flush=True);continue
    with wave.open(row['target'],'wb') as w:
        w.setparams((1,2,24000,0,'NONE','not compressed'))
        w.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*i/24000))) for i in range(24000)))
    print(json.dumps({'event':'done'}),flush=True)
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class LocalTTSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.worker = self.root / 'worker.py'
        self.worker.write_text(WORKER, encoding='utf-8')
        self.cancel = threading.Event()
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            session.close()
        self.temp.cleanup()

    def session(self):
        session = LocalTTSSession(python=sys.executable, worker=self.worker)
        self.sessions.append(session)
        return session

    def tone(self, path):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=24000:duration=2', '-c:a', 'libmp3lame', str(path)], check=True)

    def samples(self, path):
        pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'f32le', '-ar', '24000', '-ac', '1', '-'])
        return np.frombuffer(pcm, dtype=np.float32)

    def test_old_cache_identity_and_project_roundtrip(self):
        c = Cue(0, 1, 'Xin chào')
        p = Project(cues=[c])
        old = hashlib.sha256(json.dumps(['Xin chào', p.voice, 0], ensure_ascii=False).encode()).hexdigest()[:24]
        self.assertEqual(raw_key(c, p), old)
        self.assertEqual(len(LOCAL_PRESETS), 25)
        self.assertEqual(len(VOICES), 27)
        p.voice = VIENEU_PREFIX + 'Trúc Ly'
        c.voice = VIENEU_PREFIX + 'Hải Đăng'
        natural = raw_key(c, p)
        p.tts_pitch = 2.5
        self.assertNotEqual(raw_key(c, p), natural)
        self.assertEqual(synthesis_key(c, p), natural)
        restored = Project.from_dict(p.to_dict())
        self.assertEqual((restored.voice, restored.cues[0].voice, restored.tts_pitch), (p.voice, c.voice, 2.5))
        self.assertEqual(Project.from_dict({'version': 1}).tts_pitch, 0)
        for bad in [float('nan'), float('inf'), True, 7, '2']:
            with self.assertRaises(ValueError):Project.from_dict({'version': 1, 'tts_pitch': bad})
        with self.assertRaises(ValueError):Project.from_dict({'version': 1, 'voice': VIENEU_PREFIX + 'unknown'})

    def test_one_model_across_interleaved_batches_and_cached_resume(self):
        p = Project(duration=6, voice=VIENEU_PREFIX + 'Trúc Ly', tts_workers=6, tts_retry_mode='per_cue',
                    cues=[Cue(0, .5, 'Một'), Cue(2, 2.5, 'Hai', voice=VIENEU_PREFIX + 'Hải Đăng'), Cue(4, 4.5, 'Một')])
        with patch('studio.core.LocalTTSSession', side_effect=self.session), patch('studio.core.edge_client', side_effect=AssertionError('Network provider touched')):
            result = generate_voices(p, self.cache, self.cancel, lambda *a: None, mix=False, parallel_segments=[(0, 3), (3, 6)])
        self.assertEqual(result['missing_count'], 0)
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(len(self.sessions), 1)
        self.assertIsNone(self.sessions[0].proc)
        self.assertFalse(self.sessions[0].ready)
        log = self.worker.with_suffix('.log').read_text().splitlines()
        self.assertEqual(log[0], 'loaded')
        self.assertCountEqual(log[1:], ['Trúc Ly|Một', 'Hải Đăng|Hai'])
        self.assertTrue(all(row['duration'] > .9 for row in result['rows']))
        with patch('studio.local_tts.local_python', side_effect=AssertionError('No install required for cached audio')), patch('studio.core.edge_client', side_effect=AssertionError('No Edge required')):
            again = generate_voices(p, self.cache, self.cancel, lambda *a: None, mix=False)
        self.assertEqual(again['missing_count'], 0)
        self.assertEqual(self.worker.with_suffix('.log').read_text().splitlines(), log)
        self.assertFalse(list(self.cache.glob('*.partial.*')))

    def test_pitch_changes_frequency_preserves_duration_and_reuses_natural_audio(self):
        cue = Cue(0, 3, 'Xin chào')
        p = Project(duration=4, cues=[cue])
        natural = self.cache / (raw_key(cue, p) + '.mp3')
        self.tone(natural)
        original = natural.read_bytes()
        before = signature(p)
        for pitch in (2.5, -2):
            p.tts_pitch = pitch
            with patch('studio.core.edge_client', side_effect=AssertionError('Should reuse natural MP3')), patch('studio.core.fetch_voice', side_effect=AssertionError('No extra TTS')):
                result = generate_voices(p, self.cache, self.cancel, lambda *a: None, mix=False)
            target = self.cache / (raw_key(cue, p) + '.mp3')
            samples = self.samples(target)[5000:-5000]
            peak = np.fft.rfftfreq(len(samples), 1 / 24000)[np.argmax(np.abs(np.fft.rfft(samples)))]
            self.assertAlmostEqual(peak, 440 * 2 ** (pitch / 12), delta=3)
            self.assertAlmostEqual(probe(target)['duration'], probe(natural)['duration'], delta=.1)
            self.assertEqual(result['missing_count'], 0)
            self.assertNotEqual(signature(p), before)
            self.assertEqual(natural.read_bytes(), original)
        removed = remove_cached_voice(p, self.cache, [cue.id])
        self.assertGreaterEqual(removed['count'], 2)
        self.assertFalse(natural.exists())

    def test_cancel_stops_worker_keeps_finished_cues_and_cleans_partial_files(self):
        p = Project(duration=4, voice=VIENEU_PREFIX + 'Trúc Ly',
                    cues=[Cue(0, .5, 'xong'), Cue(2, 2.5, 'wait')])
        def report(n, text):
            if 'Voice 1/2' in text:
                timer = threading.Timer(.15, self.cancel.set)
                timer.start()
        began = time.monotonic()
        with patch('studio.core.LocalTTSSession', side_effect=self.session):
            with self.assertRaises(InterruptedError):
                generate_voices(p, self.cache, self.cancel, report, mix=False)
        self.assertLess(time.monotonic() - began, 3)
        self.assertTrue((self.cache / (raw_key(p.cues[0], p) + '.mp3')).is_file())
        self.assertFalse((self.cache / (raw_key(p.cues[1], p) + '.mp3')).is_file())
        self.assertFalse(list(self.cache.glob('*.partial.*')))
        self.assertIsNone(self.sessions[0].proc)
        self.assertFalse(self.sessions[0].ready)

    def test_local_cue_error_does_not_drop_following_cues(self):
        p = Project(duration=4, voice=VIENEU_PREFIX + 'Trúc Ly',
                    cues=[Cue(0, .5, 'fail'), Cue(2, 2.5, 'tốt')])
        with patch('studio.core.LocalTTSSession', side_effect=self.session):
            result = generate_voices(p, self.cache, self.cancel, lambda *a: None, mix=False)
        self.assertEqual(result['missing_count'], 1)
        self.assertEqual([r['id'] for r in result['rows']], [p.cues[1].id])
        self.assertEqual(result['tts_errors'][0]['id'], p.cues[0].id)
        errors = json.loads((self.cache / 'voice-errors.json').read_text())
        self.assertEqual(set(errors), {p.cues[0].id})

    def test_mixed_provider_rate_pitch_and_retimed_video_export(self):
        video = self.root / 'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=blue:s=160x90:r=10:d=4',
                        '-f','lavfi','-i','sine=frequency=220:duration=4','-c:v','libx264','-threads','1',
                        '-c:a','aac',str(video)],check=True)
        p = Project(video=str(video), duration=4, width=160, height=90, has_audio=True,
                    voice=VIENEU_PREFIX+'Trúc Ly', tts_rate=20, tts_pitch=2.5,
                    cues=[Cue(.2,.6,'local'),Cue(2.2,2.6,'edge',voice='vi-VN-NamMinhNeural')])
        reference = self.root / 'edge.mp3'
        self.tone(reference)
        calls = []
        async def edge(text, voice, rate, target, cancel):
            calls.append((text,voice,rate))
            Path(target).write_bytes(reference.read_bytes())
        with patch('studio.core.LocalTTSSession', side_effect=self.session), patch('studio.core.fetch_voice', side_effect=edge):
            result = generate_voices(p,self.cache,self.cancel,lambda *a: None)
        self.assertEqual(calls,[('edge','vi-VN-NamMinhNeural',20)])
        self.assertEqual(result['missing_count'],0)
        self.assertTrue(result['complete'])
        self.assertTrue(.7 < result['rows'][0]['duration'] < 1)
        self.assertLessEqual(result['rows'][0]['end'],result['rows'][1]['start'])
        out = self.root / 'dubbed.mp4'
        core.export_video(p,self.cache,out,self.cancel,lambda *a: None)
        self.assertAlmostEqual(probe(out)['duration'],result['duration'],delta=.12)
        self.assertTrue(probe(out)['has_audio'])
        self.assertGreater(float(np.abs(self.samples(out)[:3000]).mean()),.001)

    def test_missing_runtime_stops_after_first_cue_and_keeps_prior_audio(self):
        p = Project(duration=6, voice=VIENEU_PREFIX + 'Trúc Ly', cues=[Cue(i, i+.5, str(i)) for i in (0, 2, 4)])
        cached = self.cache / (raw_key(p.cues[0], p) + '.mp3')
        self.tone(cached)
        with patch('studio.local_tts.local_python', side_effect=TTSServiceError('CAI-GIONG-MIEN-PHI.cmd')) as check:
            with self.assertRaisesRegex(TTSServiceError, 'CAI-GIONG'):
                generate_voices(p, self.cache, self.cancel, lambda *a: None, mix=False)
        self.assertEqual(check.call_count, 1)
        self.assertTrue(cached.exists())

    def test_ui_restores_voices_and_tone_and_disables_edge_limits(self):
        window = Window()
        try:
            window.p = Project(voice=VIENEU_PREFIX + 'Trúc Ly', tts_pitch=2.5, tts_workers=6, tts_retry_mode='per_cue')
            window.load_controls()
            self.assertEqual(window.voice.count(), 27)
            self.assertEqual(window.cue_voice.count(), 28)
            self.assertEqual(window.voice.currentData(), window.p.voice)
            self.assertEqual(window.tone.currentData(), 2.5)
            self.assertTrue(window.workers.isEnabled())
            self.assertEqual(window.workers.maximum(),4)
            self.assertEqual(window.workers.value(),1)
            self.assertFalse(window.tts_mode.isEnabled())
            window.tone.setCurrentIndex(window.tone.findData(-2.0))
            self.assertEqual(window.p.tts_pitch, -2)
            window.voice.setCurrentIndex(0)
            self.assertTrue(window.workers.isEnabled())
            self.assertEqual(window.p.tts_workers, 6)
            self.assertEqual(window.p.voice, 'vi-VN-NamMinhNeural')
        finally:
            window.dirty = False
            window.close()
            window.deleteLater()

    def test_worker_uses_cpu_fp32_and_reports_invalid_waveform(self):
        worker = Path(core.ROOT) / 'tools' / 'vieneu_worker.py'
        spec = importlib.util.spec_from_file_location('vieneu_worker_test', worker)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        requests = io.StringIO(json.dumps({'text': 'Xin chào', 'voice': 'Trúc Ly', 'target': str(self.root / 'voice.wav')}) + '\n')
        engine = SimpleNamespace(infer=lambda *a, **k: np.zeros(10, np.float32), close=lambda: None, sample_rate=48000)
        ort = SimpleNamespace(disable_telemetry_events=lambda: None)
        with patch.dict(sys.modules, {'onnxruntime': ort, 'vieneu': SimpleNamespace(Vieneu=lambda **kwargs: self.assert_cpu(kwargs, engine)), 'soundfile': SimpleNamespace()}), patch.object(module.importlib.metadata, 'version', return_value='3.8.5'), patch.object(module.sys, 'stdin', requests), patch.object(module.sys, 'stdout', output):
            self.assertEqual(module.main(), 0)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        outcomes=[e for e in events if e['event'] in ('ready','error')]
        self.assertEqual(outcomes[0]['event'], 'ready')
        self.assertEqual(outcomes[1]['event'], 'error')
        self.assertIn('âm thanh', outcomes[1]['message'])

    def assert_cpu(self, kwargs, engine):
        self.assertEqual({k: kwargs[k] for k in ('mode','backend','device','precision')},
                         dict(mode='v3turbo', backend='onnx', device='cpu', precision='fp32'))
        self.assertTrue(1 <= kwargs['threads'] <= 4)
        return engine


if __name__ == '__main__':
    unittest.main()
