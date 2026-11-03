import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

import numpy as np
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio import core
from studio.core import (Project,Cue,RATE,atomic_json,signature,voice_ready,voice_playback_path,
                         prepare_voice_playback,write_voice_audio,export_video,raw_key)
from studio.ui import Window


class VoiceVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.video=cls.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=10:d=2',
                        '-c:v','libx264','-threads','1',str(cls.video)],check=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=self.root);self.path=Path(self.folder.name)
        self.voice=self.path/'voice.wav';self.make_audio(self.voice,.025)
        self.cache=self.path/'cache';self.cache.mkdir();self.cancel=threading.Event()
        self.p=Project(video=str(self.video),video_codec='h264',duration=2,width=320,height=180,
                       original_muted=True,cues=[Cue(0,2,'Giọng Việt')])
        atomic_json(self.cache/'voices.json',dict(signature=signature(self.p),track=str(self.voice),complete=True,rows=[],missing=[]))

    def tearDown(self):self.folder.cleanup()

    def make_audio(self,path,amplitude):
        samples=np.round(np.sin(np.arange(RATE*2)*2*np.pi*440/RATE)*amplitude*32767).astype('<i2')
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,RATE,0,'NONE','not compressed'));out.writeframes(samples.tobytes())

    def samples(self,path):
        data=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vn','-ar',str(RATE),'-ac','1','-f','f32le','-'])
        return np.frombuffer(data,dtype='<f4')

    def rms(self,samples):return np.sqrt(np.mean(samples[2400:36000]**2))

    def window(self):
        w=Window();w.p=self.p;w.cache=self.cache;w.load_controls();w.changed(dirty=False)
        self.addCleanup(self.close_window,w)
        return w

    def close_window(self,w):
        w.voice_gain_timer.stop()
        if w.worker:w.worker.cancel.set()
        for _ in range(100):
            if not w.busy:break
            QTest.qWait(20)
        w.close_cpu();w.dirty=False;w.close();w.deleteLater();QTest.qWait(30)

    def wait_for(self,predicate):
        for _ in range(250):
            QTest.qWait(20)
            if predicate():return
        self.fail('Audio preparation did not finish')

    def test_project_accepts_boost_preserves_old_defaults_and_rejects_invalid_gain(self):
        self.assertEqual(Project.from_dict({'version':1}).voice_volume,1)
        for gain in (0,.5,1,3,6):
            self.p.voice_volume=gain
            self.assertEqual(Project.from_dict(self.p.to_dict()).voice_volume,gain)
        for gain in (-1,6.01,float('nan'),float('inf'),True,'3'):
            with self.assertRaisesRegex(ValueError,'600%'):Project.from_dict(dict(version=1,voice_volume=gain))

    def test_real_pcm_gain_cache_and_tts_signature_stay_independent(self):
        original=self.voice.read_bytes();base=self.samples(self.voice);before=signature(self.p);key=raw_key(self.p.cues[0],self.p)
        self.assertEqual(voice_playback_path(self.voice,1,self.cache),self.voice)
        for gain in (3,6):
            self.p.voice_volume=gain
            output=prepare_voice_playback(self.voice,gain,self.cache,self.cancel,lambda *a:None)
            samples=self.samples(output)
            self.assertAlmostEqual(self.rms(samples)/self.rms(base),gain,delta=.015)
            self.assertEqual(len(samples),len(base))
            with patch('studio.core.run',side_effect=AssertionError('Cached gain should not rerender')):
                self.assertEqual(prepare_voice_playback(self.voice,gain,self.cache,self.cancel,lambda *a:None),output)
            self.assertEqual(signature(self.p),before);self.assertEqual(raw_key(self.p.cues[0],self.p),key)
            self.assertTrue(voice_ready(self.p,self.cache))
        self.assertEqual(self.voice.read_bytes(),original)

    def test_peak_limiter_and_duration_on_strong_voice(self):
        self.make_audio(self.voice,.65);before=self.voice.read_bytes()
        output=prepare_voice_playback(self.voice,6,self.cache,self.cancel,lambda *a:None)
        samples=self.samples(output)
        self.assertLessEqual(float(np.max(np.abs(samples))),.9701)
        self.assertEqual(len(samples),RATE*2);self.assertGreater(self.rms(samples),.5)
        self.assertEqual(self.voice.read_bytes(),before)

    def test_preview_wav_and_full_video_use_same_gain(self):
        self.p.voice_volume=4
        preview=prepare_voice_playback(self.voice,4,self.cache,self.cancel,lambda *a:None)
        wav=self.path/'saved.wav';write_voice_audio(self.voice,wav,4,self.cancel,lambda *a:None)
        np.testing.assert_array_equal(self.samples(preview),self.samples(wav))
        out=self.path/'export.mp4'
        with patch('studio.core.export_encoder',return_value=('CPU',['-c:v','libx264','-preset','ultrafast'])):
            export_video(self.p,self.cache,out,self.cancel,lambda *a:None,with_voice=True)
        exported=self.samples(out);expected=self.samples(preview)
        self.assertAlmostEqual(self.rms(exported)/self.rms(expected),1,delta=.025)
        self.assertAlmostEqual(core.probe(out)['duration'],2,delta=.05)
        quieter=self.path/'half.wav';write_voice_audio(self.voice,quieter,.5,self.cancel,lambda *a:None)
        self.assertAlmostEqual(self.rms(self.samples(quieter))/self.rms(self.samples(self.voice)),.5,delta=.002)

    def test_gain_copy_refreshes_for_new_audio_and_keeps_two_recent_levels(self):
        paths=[Path(prepare_voice_playback(self.voice,g,self.cache,self.cancel,lambda *a:None)) for g in (2,3,4)]
        self.assertFalse(paths[0].exists());self.assertTrue(all(p.exists() for p in paths[1:]))
        self.make_audio(self.voice,.04)
        self.assertNotEqual(voice_playback_path(self.voice,4,self.cache),paths[-1])

    def test_cancel_preserves_source_and_saved_file_and_cleans_partial(self):
        out=self.path/'saved.wav';out.write_bytes(b'old saved file');before=self.voice.read_bytes()
        def cancelled(args,*a,**kw):
            Path(args[-1]).write_bytes(b'partial audio');raise InterruptedError('Cancelled')
        with patch('studio.core.probe',return_value={'duration':2}),patch('studio.core.run',side_effect=cancelled):
            with self.assertRaises(InterruptedError):write_voice_audio(self.voice,out,6,self.cancel,lambda *a:None)
        self.assertEqual(out.read_bytes(),b'old saved file');self.assertEqual(self.voice.read_bytes(),before)
        self.assertFalse(list(self.path.glob('*.partial.wav')))

    def test_ui_prepares_real_boost_and_returns_to_original_without_new_tts(self):
        w=self.window();w.go_stage(3);w.subtitle_tabs.setCurrentIndex(1)
        self.assertEqual(w.vvol.maximum(),600);before=signature(w.p)
        with patch('studio.ui.generate_voices',side_effect=AssertionError('Volume must not call TTS')):
            w.vvol.setValue(300)
            target=voice_playback_path(self.voice,3,self.cache)
            self.wait_for(lambda:target.is_file() and not w.busy and w.voice_player.source().toLocalFile()==str(target))
            self.assertEqual(w.p.voice_volume,3);self.assertTrue(w._voice_gain_ready)
            self.assertEqual(w.voice_audio.volume(),1)
            self.assertAlmostEqual(self.rms(self.samples(target))/self.rms(self.samples(self.voice)),3,delta=.015)
            w.vvol.setValue(50)
            self.assertEqual(w.voice_player.source().toLocalFile(),str(self.voice))
            self.assertAlmostEqual(w.voice_audio.volume(),.5)
            self.assertEqual(signature(w.p),before)
        self.assertEqual(Project.from_dict(w.p.to_dict()).voice_volume,.5)

    def test_save_wav_uses_selected_volume(self):
        w=self.window();w.p.voice_volume=3;w.load_controls()
        output=self.path/'voice-louder.wav'
        with patch('studio.ui.QFileDialog.getSaveFileName',return_value=(str(output),'')),patch('studio.ui.generate_voices',side_effect=AssertionError('Volume must not call TTS')):
            w.save_voice();self.wait_for(lambda:output.is_file() and not w.busy)
        self.assertAlmostEqual(self.rms(self.samples(output))/self.rms(self.samples(self.voice)),3,delta=.015)

    def test_single_cue_preview_uses_boosted_audio_and_selected_gain(self):
        w=self.window();w.p.voice_volume=3;w.load_controls();w.select_id(w.p.cues[0].id)
        result=dict(sample=dict(id=w.selected,path=str(self.voice),factor=1.,ok=True))
        # Decode and gain are exercised with real files; no audio device in offscreen Qt.
        with patch('studio.ui.generate_voices',return_value=result),patch.object(w.sample_player,'play') as play:
            w.sample()
            target=voice_playback_path(self.voice,3,self.cache)
            self.wait_for(lambda:not w.busy and w.sample_player.source().toLocalFile()==str(target))
            play.assert_called_once()
        self.assertTrue(w._sample_voice);self.assertEqual(w.sample_audio.volume(),1)
        self.assertAlmostEqual(self.rms(self.samples(target))/self.rms(self.samples(self.voice)),3,delta=.015)


if __name__=='__main__':unittest.main()
