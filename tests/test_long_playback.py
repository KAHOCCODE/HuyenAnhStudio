import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from studio.core import Cue,Project,raw_key,load_manifest,atomic_json,retimed_cues,batch_manifest,batch_manifest_path,batch_signature
from studio.playback_index import IntervalIndex,indexed_snap
from studio.retiming import TimingMap,prepare_timing,voice_timing,map_time,source_rate
from studio.ui import Window,CPUFrames


class TrackedCues(list):
    forbid_scan=False
    def __iter__(self):
        if self.forbid_scan:raise AssertionError('Playback must not rescan the whole SRT')
        return super().__iter__()


class LongPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.window=Window();self.window.cache=self.root

    def tearDown(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater();self.tmp.cleanup()

    def long_project(self):
        cues=TrackedCues(Cue(i*.9,i*.9+.7,f'Câu {i}') for i in range(24000))
        self.window.p=Project(duration=21600,cues=cues)
        self.window.refresh_voice_state()
        return cues

    def test_interval_queries_preserve_overlaps_and_boundary_semantics(self):
        rng=random.Random(17)
        cues=[Cue(0,21600,'Câu dài'),Cue(10,20,'Cùng mốc 1'),Cue(10,15,'Cùng mốc 2')]
        cues += [Cue(start,start+rng.uniform(.1,30),'Câu') for start in [rng.uniform(0,21600) for _ in range(500)]]
        cues.sort(key=lambda c:c.start);index=IntervalIndex(cues)
        for lo,hi in [(0,0),(10,10),(15,15),(20,20),(21599,21600)]+[(t,t+5) for t in [rng.uniform(0,21590) for _ in range(100)]]:
            self.assertEqual(index.intersect(lo,hi),[c for c in cues if c.start<=hi and c.end>=lo])
            self.assertEqual(index.active(lo),[c for c in cues if c.start<=lo<c.end])
        self.assertEqual(indexed_snap(9.99,[0,10,20],.1),10)
        self.assertEqual(indexed_snap(15,[0,10,20],.1),15)

    def test_playback_and_zoomed_timeline_do_not_scan_all_24000_cues(self):
        cues=self.long_project();w=self.window
        w.timeline.resize(1000,132);w.timeline.zoom=70;w.timeline.offset=18000
        cues.forbid_scan=True
        for ms in (18000000,18000300,18000900,18001200):w.on_position(ms)
        self.assertEqual(w.preview.overlay.text,'Câu 20001')
        blocks=w.timeline.blocks()
        self.assertLess(len(blocks),30)
        self.assertEqual(w.timeline.hit(18000.2,70).id,cues[20000].id)
        cues.forbid_scan=False

    def test_overview_coalesces_dense_blocks_and_cursor_reuses_geometry(self):
        self.long_project();w=self.window;w.timeline.resize(1000,132);w.timeline.zoom=892/21600
        blocks=w.timeline.blocks()
        self.assertLessEqual(len(blocks),1000)
        with patch.object(w,'row_status',side_effect=AssertionError('Cursor must reuse prepared blocks')):
            w.on_position(10800000)
            self.assertIs(w.timeline.blocks(),blocks)
            w.on_position(10800000)
        self.assertEqual(w.timeline.hit(21599.3,70).id,w.p.cues[-1].id)

    def test_render_status_cache_invalidates_after_text_change_and_audio_deletion(self):
        w=self.window;c=Cue(0,1,'Xin chào');w.p=Project(duration=2,cues=[c]);w.model.refresh()
        path=self.root/(raw_key(c,w.p)+'.mp3');path.write_bytes(b'completed-audio')
        w.refresh_voice_state()
        self.assertEqual(w.row_status(c)[0],'cached')
        with patch.object(Path,'stat',side_effect=AssertionError('No filesystem queries while painting')):
            self.assertEqual(w.row_status(c)[0],'cached')
            self.assertEqual(w.model.data(w.model.index(0,2),Qt.DisplayRole),'Có MP3')
            w.timeline.resize(800,132);w.timeline.blocks()
        c.text='Câu khác';w.refresh_voice_state()
        self.assertEqual(w.row_status(c)[0],'none')
        c.text='Xin chào';w.refresh_voice_state();self.assertEqual(w.row_status(c)[0],'cached')
        path.unlink();w.refresh_voice_state();self.assertEqual(w.row_status(c)[0],'none')

    def test_dragged_cue_is_visible_before_index_is_rebuilt(self):
        cues=self.long_project();w=self.window;c=cues[0]
        w.timeline.resize(1000,132);w.timeline.zoom=70;w.timeline.offset=10000
        w.timeline.drag=dict(snapshot={c.id:(c.start,c.end)})
        c.start=10000;c.end=10001
        self.assertIn(c,w.timeline.visible_cues(10000,10010))
        self.assertEqual(w.timeline.hit(10000.3,70).id,c.id)
        w.timeline.drag=None;w.p.cues.sort(key=lambda c:c.start);w.refresh_voice_state()
        w.on_position(10000300)
        self.assertIn('Câu 0',w.preview.overlay.text)

    def test_timing_index_roundtrip_preserves_existing_json_and_inverse_mapping(self):
        p=Project(duration=21600,cues=[Cue(i*3.6,i*3.6+2,f'Câu {i}') for i in range(6000)])
        timing=voice_timing(p,[dict(id=c.id,duration=3) for c in p.cues[::2]])
        plain=json.loads(json.dumps(timing));indexed=prepare_timing(plain)
        self.assertEqual(json.loads(json.dumps(indexed)),plain)
        self.assertEqual(set(indexed),{'spans','rows','duration'})
        for t in [0,.5,2,3.6,10800,18000,21599,21600]:
            self.assertAlmostEqual(map_time(indexed,t),map_time(plain,t))
            self.assertAlmostEqual(source_rate(indexed,t),source_rate(plain,t))
            self.assertAlmostEqual(map_time(indexed,map_time(indexed,t),True),t)
        atomic_json(self.root/'voices.json',dict(timing=plain))
        loaded=load_manifest(self.root)['timing'];self.assertIsInstance(loaded,TimingMap)
        # Repeated mapping uses the same lookup arrays; nothing is added to project JSON.
        starts=loaded.source_starts
        result=retimed_cues(p,loaded)
        for cue in result:
            map_time(loaded,cue.start,True);map_time(loaded,cue.end,True)
        self.assertIs(loaded.source_starts,starts)
        self.assertEqual(len(result),6000)
        atomic_json(self.root/'voices.json',dict(timing={}))
        self.assertEqual(load_manifest(self.root)['timing'],{})
        track=self.root/'track.wav';track.write_bytes(b'completed')
        segment=(0,60)
        atomic_json(batch_manifest_path(self.root,segment),dict(signature=batch_signature(p,segment),track=str(track),timing=plain))
        self.assertIsInstance(batch_manifest(p,self.root,segment)['timing'],TimingMap)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_cpu_decoder_can_seek_near_end_of_six_hour_source_with_subtitles(self):
        video=self.root/'six-hours.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=blue:s=96x54:r=1:d=21600',
                        '-an','-c:v','libx264','-preset','ultrafast','-threads','1',str(video)],check=True)
        p=Project(video=str(video),duration=21600,width=96,height=54,
                  cues=[Cue(i*3.6,i*3.6+2,'Lời thoại') for i in range(6000)])
        decoder=CPUFrames(str(video),'h264',96,54,21590,project=p)
        try:
            timestamp,pixels=decoder.frames.get(timeout=15)
            self.assertAlmostEqual(timestamp,21590)
            self.assertEqual(len(pixels),decoder.width*decoder.height*3)
            self.assertFalse(decoder.error)
        finally:decoder.close();decoder.thread.join(timeout=3)


if __name__=='__main__':unittest.main()
