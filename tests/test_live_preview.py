import os
import json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import queue
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from studio.core import Project, export_video
from studio.ui import CPUFrames, Window


class LivePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.tmp=tempfile.TemporaryDirectory()
        cls.path=Path(cls.tmp.name)/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'testsrc2=size=320x180:rate=30:duration=2',
                        '-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','aac',
                        '-c:v','libx264','-threads','1',str(cls.path)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def project(self):return Project(video=str(self.path),video_codec='h264',width=320,height=180,duration=2,has_audio=True)

    def frame(self,p):
        decoder=CPUFrames(p.video,'h264',320,180,.5,project=p)
        try:
            timestamp,pixels=decoder.frames.get(timeout=10)
            self.assertAlmostEqual(timestamp,.5)
            self.assertEqual(len(pixels),decoder.width*decoder.height*3)
            self.assertFalse(decoder.error)
            return pixels,decoder.width,decoder.height
        finally:decoder.close();decoder.thread.join(timeout=3)

    def test_filter_changes_pixels_and_output_aspect(self):
        p=self.project();p.video_effects=dict(enabled=True)
        first=self.frame(p)
        p.video_effects.update(zoom=1.5)
        second=self.frame(p)
        self.assertNotEqual(first[0],second[0])
        p.video_effects.update(size='portrait',layout='blur',effect='dust')
        third=self.frame(p)
        self.assertAlmostEqual(third[1]/third[2],9/16,delta=.005)
        p.video_effects.update(size='custom',width=64,height=7680,layout='crop',effect='none')
        narrow=self.frame(p)
        self.assertLess(narrow[1],64)
        self.assertEqual(p.video_effects['width'],64)

    def test_docked_controls_change_main_preview_while_paused(self):
        w=Window();w.p=self.project();w.show();w.video_effects_dialog()
        try:
            self.assertFalse(w.effects_dock.isFloating())
            self.assertFalse(w.effects_panel.isWindow())
            w.effects_panel.controls['zoom'].setValue(1.5)
            for _ in range(60):
                QTest.qWait(50)
                if w.cpu_decoder and w.cpu_decoder.project and not w.preview.overlay.isVisible():break
            self.assertTrue(w.cpu_decoder and w.cpu_decoder.project)
            self.assertFalse(w.preview.overlay.isVisible())
            self.assertFalse(w.preview.video.pixmap().isNull())
            for preset in ('ultrafast','veryfast','medium'):
                w.effects_speed.setCurrentIndex(w.effects_speed.findData(preset))
                self.assertEqual(w.p.export_preset,preset)
            w.mask_edit.setChecked(True)
            QTest.qWait(500)
            self.assertIsNone(w.cpu_decoder.project)
        finally:
            w.close_cpu();w.dirty=False;w.close();w.deleteLater();QTest.qWait(100)

    def test_three_export_presets_reach_ffmpeg(self):
        from studio import core
        p=self.project();p.video_effects=dict(enabled=True,zoom=1.15)
        for preset in ('ultrafast','veryfast','medium'):
            p.export_preset=preset
            with patch('studio.core.run',wraps=core.run) as run:
                export_video(p,Path(self.tmp.name)/'cache',Path(self.tmp.name)/(preset+'.mp4'),
                             threading.Event(),lambda *a:None,with_voice=False)
            command=next(c.args[0] for c in run.call_args_list if '-preset' in c.args[0])
            self.assertEqual(command[command.index('-preset')+1],preset)

    def test_mute_preview_restore_and_project_save(self):
        w=Window();w.p=self.project();w.load_controls()
        try:
            w.vol.setValue(37)
            w.mute_original.setChecked(True)
            self.assertEqual(w.audio.volume(),0)
            self.assertFalse(w.vol.isEnabled())
            saved=Project.from_dict(w.p.to_dict())
            self.assertTrue(saved.original_muted)
            self.assertAlmostEqual(saved.original_volume,.37)
            self.assertEqual(w.voice_audio.volume(),1)
            w.mute_original.setChecked(False)
            self.assertAlmostEqual(w.audio.volume(),.37,places=5)
            self.assertTrue(w.vol.isEnabled())
            self.assertFalse(Project.from_dict({'version':1}).original_muted)
        finally:
            w.close_cpu();w.dirty=False;w.close();w.deleteLater();QTest.qWait(100)

    def test_mute_export_removes_original_but_keeps_voice(self):
        p=self.project();p.original_muted=True
        p.music_clean={'enabled':True}  # Missing processed audio must not block a muted export.
        for voice in (False,True):
            out=Path(self.tmp.name)/('muted-voice.mp4' if voice else 'muted.mp4')
            export_video(p,Path(self.tmp.name)/'cache',out,threading.Event(),lambda *a:None,
                         with_voice=voice,segment=(0,2) if voice else None,
                         review_voice={'track':str(self.path),'complete':True} if voice else None)
            streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams',
                                                        '-of','json',str(out)]))['streams']
            self.assertEqual(any(s['codec_type']=='audio' for s in streams),voice)
