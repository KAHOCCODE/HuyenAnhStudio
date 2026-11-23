import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio.core import Project,export_video
from studio.composition import (TEXT_PRESETS,TEXT_EFFECT_DEFAULTS,new_layer,
                                draw_layer,validate_layer)
from studio.layers_ui import LayersPanel
from studio.ui import Window,CPUFrames


class TextStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def image(self,layer):
        image=QImage(960,540,QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter=QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        try:draw_layer(painter,layer,960,540)
        finally:painter.end()
        return image

    def test_old_layers_render_unchanged_and_all_presets_roundtrip(self):
        layer=new_layer(duration=2)
        old={key:value for key,value in layer.items() if key not in TEXT_EFFECT_DEFAULTS}
        self.assertEqual(self.image(layer),self.image(old))
        project=Project(duration=2,overlays=[old])
        self.assertEqual(Project.from_dict(project.to_dict()).overlays,[old])
        images=[]
        for key in TEXT_PRESETS:
            layer=new_layer(duration=2,preset=key)
            layer.update(text='Huyễn Ảnh\nĐừng động đậy!',w=80.,h=50.)
            validate_layer(layer,2)
            project.overlays=[layer]
            self.assertEqual(Project.from_dict(project.to_dict()).overlays,[layer])
            image=self.image(layer)
            self.assertFalse(image.isNull())
            images.append(bytes(image.constBits()))
        self.assertEqual(len(set(images)),len(TEXT_PRESETS))

    def test_effect_settings_reject_invalid_values(self):
        for key,value in [('glow',37),('depth',float('nan')),('tracking',True),
                          ('outer_outline',-1),('glow_color','red;movie=x'),
                          ('gradient_color','#12'),('fill_mode','unknown'),('italic',1)]:
            with self.subTest(key=key):
                layer=new_layer(duration=2)
                layer[key]=value
                with self.assertRaises(ValueError):validate_layer(layer,2)

    def test_gallery_editing_and_switching_reset_effects_without_moving_text(self):
        layer=new_layer(duration=2)
        layer={key:value for key,value in layer.items() if key not in TEXT_EFFECT_DEFAULTS}
        layer.update(text='Tập 01 · Huyễn Ảnh',x=11.,y=24.,w=70.,h=35.,start=.2,end=1.8)
        panel=LayersPanel(Project(duration=2,overlays=[layer]))
        panel.resize(340,900)
        panel.show()
        self.app.processEvents()
        try:
            panel.preset_gallery.setCurrentRow(panel.gallery_keys.index('neon'))
            self.assertGreater(panel.selected['glow'],0)
            self.assertEqual(panel.text_preset.currentData(),'neon')
            for key in ('id','text','x','y','w','h','start','end'):
                self.assertEqual(panel.selected[key],layer[key])
            first=panel.preset_gallery.visualItemRect(panel.preset_gallery.item(0))
            second=panel.preset_gallery.visualItemRect(panel.preset_gallery.item(1))
            self.assertEqual(first.y(),second.y())
            self.assertGreater(second.x(),first.x())
            panel.text_preset.setCurrentIndex(panel.text_preset.findData('cinema'))
            panel.controls['text'].setPlainText('Nội dung mới vẫn giữ mẫu chữ')
            self.assertEqual(panel.selected['font'],'Georgia')
            self.assertEqual(panel.text_preset.currentData(),'cinema')
            panel.controls['glow'].setValue(12)
            self.assertEqual(panel.text_preset.currentData(),'')
            panel.apply_preset('clean')
            for key,value in TEXT_EFFECT_DEFAULTS.items():
                self.assertEqual(panel.selected[key],value)
        finally:
            panel.close()
            panel.deleteLater()
            QTest.qWait(20)

    def test_presets_support_window_undo_redo_and_hide_for_icons(self):
        window=Window()
        window.p=Project(video='/tmp/style-test.mp4',duration=2,
                         overlays=[new_layer(duration=2)])
        with patch.object(window,'refresh_effect_preview'):
            window.load_controls()
            window.show()
            window.go_stage(2)
            try:
                before=copy.deepcopy(window.p.overlays)
                panel=window.layers_panel
                panel.preset_gallery.setCurrentRow(panel.gallery_keys.index('gold'))
                self.assertEqual(window.p.overlays[0]['fill_mode'],'metal')
                window.undo_action()
                self.assertEqual(window.p.overlays,before)
                window.redo_action()
                self.assertEqual(window.p.overlays[0]['fill_mode'],'metal')
                self.assertEqual(Project.from_dict(window.p.to_dict()).overlays,window.p.overlays)
                panel.add('icon')
                icon=copy.deepcopy(panel.selected)
                panel.apply_preset('neon')
                self.assertEqual(panel.selected,icon)
                self.assertFalse(panel.preset_gallery.isVisible())
                self.assertFalse(panel.controls['glow'].isVisible())
            finally:
                window.close_cpu()
                window.dirty=False
                window.close()
                window.deleteLater()
                QTest.qWait(30)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class TextStyleExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        cls.source=cls.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'color=c=0x142036:s=480x270:r=10:d=2',
                        '-c:v','libx264','-threads','1',str(cls.source)],check=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def pixels(self,path,t=.6):
        data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),
                                      '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
        return np.frombuffer(data,dtype=np.uint8).reshape(270,480,3).copy()

    def project(self,key):
        layer=new_layer(duration=2,preset=key)
        layer.update(text='Huyễn Ảnh\nTập 01',size=100.,x=8.,y=15.,w=84.,h=65.,
                     start=.3,end=1.5,opacity=.85,align='center')
        return Project(video=str(self.source),width=480,height=270,duration=2,
                       video_codec='h264',overlays=[layer],export_preset='ultrafast')

    def test_real_exports_match_vector_artwork_and_keep_layer_timings(self):
        source=self.pixels(self.source)
        for key in ('gold','neon','cinema','comic','ice','rose'):
            with self.subTest(style=key):
                project=self.project(key)
                out=self.root/(key+'.mp4')
                export_video(project,self.root/'cache',out,threading.Event(),lambda *a:None,with_voice=False)
                expected=QImage(source.tobytes(),480,270,1440,QImage.Format_RGB888).copy()
                painter=QPainter(expected)
                painter.setRenderHint(QPainter.Antialiasing)
                draw_layer(painter,project.overlays[0],480,270)
                painter.end()
                expected=expected.convertToFormat(QImage.Format_RGB888)
                pixels=np.frombuffer(expected.constBits(),dtype=np.uint8).reshape(270,480,3)
                foreground=np.max(np.abs(pixels.astype(float)-source),axis=2)>30
                self.assertGreater(int(foreground.sum()),500)
                actual=self.pixels(out)
                self.assertLess(float(np.abs(actual.astype(float)-pixels)[foreground].mean()),18)
                self.assertLess(float(np.abs(self.pixels(out,.1).astype(float)-source).mean()),3)
                self.assertLess(float(np.abs(self.pixels(out,1.8).astype(float)-source).mean()),3)

    def test_cpu_preview_renders_the_same_styled_artwork(self):
        project=self.project('neon')
        decoder=CPUFrames(project.video,'h264',480,270,.6,project=project)
        try:
            _,frame=decoder.frames.get(timeout=10)
            preview=np.frombuffer(frame,dtype=np.uint8).reshape(270,480,3)
            self.assertGreater(int(np.count_nonzero(preview[:,:,1]>140)),200)
            self.assertFalse(decoder.error)
        finally:
            decoder.close()
            decoder.thread.join(3)


if __name__=='__main__':unittest.main()
