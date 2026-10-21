import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from studio.core import Project,Cue,export_video,write_ass,video_filter
from studio.composition import new_layer,prepare_layers,validate_composition
from studio.ui import Window,CPUFrames


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.source=cls.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
            'color=c=red:s=320x180:r=10:d=2,drawbox=x=160:y=0:w=160:h=180:c=blue:t=fill',
            '-c:v','libx264','-threads','1',str(cls.source)],check=True)
        logo=QImage(100,40,QImage.Format_RGB32);logo.fill(QColor('#00FF00'))
        for x in range(40,100):
            for y in range(40):logo.setPixelColor(x,y,QColor('#FF00FF'))
        cls.logo=cls.root/'logo tiếng Việt.png';logo.save(str(cls.logo))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def p(self):return Project(video=str(self.source),width=320,height=180,duration=2,video_codec='h264')
    def pixels(self,path,t=.5):
        data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
        return QImage(data,320,180,960,QImage.Format_RGB888).copy()
    def export(self,p,name,**kwargs):
        path=self.root/name
        with patch('studio.core.export_encoder',return_value=('CPU',['-c:v','libx264','-preset','ultrafast','-crf','20'])):
            export_video(p,self.root/'cache',path,threading.Event(),lambda *a:None,with_voice=False,**kwargs)
        return path
    def test_old_project_roundtrip_and_invalid_layer(self):
        p=Project.from_dict({'version':1});self.assertEqual(p.overlays,[])
        p=self.p();p.overlays=[new_layer(duration=2,preset='notice')];p.sidebar=dict(enabled=True)
        self.assertEqual(Project.from_dict(p.to_dict()).overlays,p.overlays)
        for key,value in [('x',float('nan')),('color','red;movie=x'),('end',3),('opacity',2)]:
            bad=copy.deepcopy(p);bad.overlays[0][key]=value
            with self.assertRaises(ValueError):validate_composition(bad)
    def test_mask_flips_but_logo_and_subtitles_do_not(self):
        p=self.p();p.video_effects=dict(enabled=True,flip=True)
        p.mask.update(enabled=True,mode='solid',color='#00FF00',x=10,y=70,w=20,h=20)
        v=new_layer('image',2);v.update(image=str(self.logo),x=4,y=5,w=25,h=20);p.overlays=[v]
        p.cues=[Cue(0,2,'Phụ đề Việt')]
        out=self.export(p,'mirror.mp4');image=self.pixels(out)
        self.assertGreater(image.pixelColor(256,140).green(),180)  # source mask moves right
        self.assertGreater(image.pixelColor(18,26).green(),180)  # asymmetric logo stays left
        self.assertGreater(image.pixelColor(75,26).red(),180)
        other=copy.deepcopy(p);other.video_effects['flip']=False
        ref=self.pixels(self.export(other,'no-mirror.mp4'))
        # The subtitle footprint is identical against two flat backgrounds.
        def whites(im):return {(x,y) for x in range(90,230) for y in range(145,165) if min(im.pixelColor(x,y).getRgb()[:3])>200}
        self.assertGreater(len(whites(image)),10)
        self.assertGreater(len(whites(image)&whites(ref))/len(whites(image)|whites(ref)),.90)
    def test_sidebar_keeps_size_and_timings_survive_seek(self):
        p=self.p();p.sidebar=dict(enabled=True,width=25,color='#111111',side='right')
        v=new_layer('icon',2);v.update(start=1,x=78,y=20,w=18,h=40,color='#00FF00');p.overlays=[v]
        out=self.export(p,'sidebar.mp4')
        early=self.pixels(out,.3);late=self.pixels(out,1.5)
        self.assertLess(early.pixelColor(280,70).green(),40);self.assertGreater(late.pixelColor(280,70).green(),100)
        self.assertGreater(early.pixelColor(30,80).red(),150)
        sample=self.export(p,'seek.mp4',preview=1.2)
        self.assertGreater(self.pixels(sample,.1).pixelColor(280,70).green(),100)
    def test_all_mask_modes_encode(self):
        for mode in ('blur','gblur','mosaic','solid'):
            p=self.p();p.mask.update(enabled=True,mode=mode)
            out=self.export(p,mode+'.mp4');self.assertGreater(out.stat().st_size,100)
    def test_notice_raster_preview_and_edit_dock(self):
        p=self.p();p.overlays=[new_layer(duration=2,preset='notice')]
        folder=self.root/'notice';folder.mkdir();assets=prepare_layers(folder,p)
        self.assertEqual(len(assets),1)
        img=QImage(str(folder/assets[0]['file']))
        self.assertTrue(any(img.pixelColor(x,y).red()>150 and img.pixelColor(x,y).alpha()>100 for x in range(img.width()) for y in range(img.height())))
        decoder=CPUFrames(p.video,'h264',320,180,.5,project=p)
        try:self.assertEqual(len(decoder.frames.get(timeout=10)[1]),320*180*3)
        finally:decoder.close();decoder.thread.join(3)
        w=Window();w.p=p;w.load_controls();w.show();w.open_layers()
        try:
            panel=w.layers_panel;self.assertEqual(w.stage_index,2)
            self.assertFalse(panel.isWindow())
            panel.add('icon');self.assertEqual(len(w.p.overlays),2)
            panel.controls['text'].setPlainText('Tên kênh');panel.controls['x'].setValue(20)
            self.assertEqual(w.p.overlays[1]['x'],20)
            panel.bar_on.setChecked(True);panel.place_in_sidebar();self.assertTrue(w.p.sidebar['enabled'])
            self.assertGreater(w.p.overlays[1]['x'],70)
            QTest.qWait(300);w.preview.update_layer_box()
            center=w.preview.mapFromScene(w.preview.layer_box.rect().center())
            old_y=w.p.overlays[1]['y']
            QTest.mousePress(w.preview.viewport(),Qt.LeftButton,pos=center)
            QTest.mouseMove(w.preview.viewport(),center+QPoint(0,20))
            QTest.mouseRelease(w.preview.viewport(),Qt.LeftButton,pos=center+QPoint(0,20))
            self.assertGreater(w.p.overlays[1]['y'],old_y)
            w.mask_edit.setChecked(True);w.toggle_mirror();self.assertFalse(w.mask_edit.isChecked())
        finally:w.close_cpu();w.dirty=False;w.close();w.deleteLater();QTest.qWait(100)

    def test_speech_only_reuses_stem_and_optional_filter(self):
        import shutil
        from studio import core
        source=self.root/'audio-source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(self.source),'-f','lavfi','-i',
                        'sine=frequency=440:duration=2','-c:v','copy','-c:a','aac','-shortest',str(source)],check=True)
        p=self.p();p.video=str(source);p.has_audio=True;calls=[]
        def separator(src,target,models,cancel):calls.append(1);shutil.copyfile(src,target)
        with patch('studio.core.run',wraps=core.run) as run:
            first=core.build_music_reduction(p,self.root/'audio-cache',threading.Event(),lambda *a:None,retain=0,separator=separator)
        self.assertEqual(len(calls),1)
        self.assertFalse(any('amix' in str(call.args[0]) for call in run.call_args_list))
        second=core.build_music_reduction(p,self.root/'audio-cache',threading.Event(),lambda *a:None,retain=0,separator=separator,polish=True)
        self.assertEqual(len(calls),1)
        self.assertNotEqual(first['track'],second['track'])
        self.assertAlmostEqual(core.probe(second['track'])['duration'],2,delta=.05)

    def test_top_subtitle_renders_after_mirror_inside_video_area(self):
        p=self.p();p.video_effects=dict(enabled=True,flip=True);p.sidebar=dict(enabled=True,side='left',width=25,color='#111111')
        p.cues=[Cue(0,2,'VỊ TRÍ PHỤ ĐỀ')];p.style.update(y=16)
        image=self.pixels(self.export(p,'top-subtitle.mp4'))
        top=[(x,y) for x in range(320) for y in range(60) if min(image.pixelColor(x,y).getRgb()[:3])>200]
        self.assertGreater(len(top),10);self.assertGreater(min(x for x,y in top),80)
        self.assertAlmostEqual(sum(x for x,y in top)/len(top),200,delta=12)
        self.assertFalse(any(min(image.pixelColor(x,y).getRgb()[:3])>200 for x in range(320) for y in range(120,180)))

    def test_slowing_before_voice_fitting_prevents_overlap(self):
        from studio import core
        import shutil
        cache=self.root/'fitting-cache';cache.mkdir()
        p=self.p();p.max_fit=1.2;c1=Cue(0,1,'Câu đầu');c2=Cue(1,2,'Câu tiếp')
        first=cache/(core.raw_key(c1,p)+'.mp3');second=cache/(core.raw_key(c2,p)+'.mp3')
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=1.6',str(first)],check=True)
        shutil.copyfile(first,second)
        fast=core.prepare_voice_row(c1,p,cache,threading.Event(),known_duration=1.6)
        self.assertFalse(fast['ok']);self.assertGreater(fast['end'],c2.start)
        p.work_speed=.5
        slow1=core.prepare_voice_row(c1,p,cache,threading.Event(),known_duration=1.6)
        slow2=core.prepare_voice_row(c2,p,cache,threading.Event(),known_duration=1.6)
        self.assertTrue(slow1['ok']);self.assertEqual(slow1['spill'],0)
        self.assertLessEqual(slow1['end'],slow2['start'])
