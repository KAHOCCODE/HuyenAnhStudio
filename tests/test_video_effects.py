import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from studio.core import Project, Cue, export_video, write_ass, video_filter
from studio.video_effects import settings, output_size


class EffectSettingsTests(unittest.TestCase):
    def test_old_projects_and_roundtrip(self):
        p = Project.from_dict({'version': 1})
        self.assertFalse(settings(p.video_effects)['enabled'])
        p.video_effects = dict(enabled=True, size='portrait', zoom=1.15, flip=True)
        self.assertEqual(Project.from_dict(p.to_dict()).video_effects, p.video_effects)
        self.assertEqual(output_size(p), (1080, 1920))

    def test_reject_invalid_values(self):
        for value in [[], {'zoom': float('nan')}, {'opacity': .8},
                      {'width': 101}, {'height': 100.5}, {'flip': 'yes'},
                      {'background': "red;movie=x"}, {'size': 'wrong'}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings(value)

    def test_final_subtitles_and_source_replacements(self):
        p = Project(width=640, height=360, cues=[Cue(0, 1, 'Hello')])
        p.video_effects = dict(enabled=True, size='portrait', flip=True)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'subtitles.ass'
            write_ass(path, p, regions=False, canvas=output_size(p))
            text = path.read_text(encoding='utf-8-sig')
            self.assertIn('PlayResX: 1080', text)
            self.assertIn('PlayResY: 1920', text)
            graph = video_filter(p)
            self.assertLess(graph.index('hflip'), graph.index('regions.ass'))
            self.assertLess(graph.index('regions.ass'), graph.index('subtitles.ass'))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class RenderTests(unittest.TestCase):
    def test_full_export_is_not_limited_to_ten_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'long.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                'testsrc2=size=160x90:rate=10:duration=14','-f','lavfi','-i',
                'sine=frequency=440:duration=14','-c:v','libx264','-threads','1',
                '-c:a','aac',str(src)],check=True)
            p=Project(video=str(src),width=160,height=90,duration=14,has_audio=True)
            p.video_effects=dict(enabled=True,size='custom',width=90,height=160,
                                 zoom=1.15,layout='blur',effect='dust')
            out=root/'complete.mp4'
            export_video(p,root/'cache',out,threading.Event(),lambda *a:None,
                         with_voice=False,preview=None,segment=None)
            info=json.loads(subprocess.check_output(['ffprobe','-v','error',
                '-show_streams','-show_format','-of','json',str(out)]))
            self.assertAlmostEqual(float(info['format']['duration']),14,delta=.2)
            video=next(x for x in info['streams'] if x['codec_type']=='video')
            self.assertEqual((video['width'],video['height']),(90,160))
            self.assertTrue(any(x['codec_type']=='audio' for x in info['streams']))

    def test_export_layouts_effects_audio_and_preview(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=320x180:rate=12:duration=1.5', '-f', 'lavfi',
                            '-i', 'sine=frequency=440:duration=1.5', '-c:v', 'libx264',
                            '-threads', '1', '-c:a', 'aac', str(src)], check=True)
            for i, (layout, effect) in enumerate([
                ('crop', 'none'), ('fit', 'haze'), ('blur', 'dust'), ('frame', 'light')]):
                with self.subTest(layout=layout):
                    p = Project(video=str(src), width=320, height=180, duration=1.5,
                                has_audio=True, work_speed=1.25)
                    p.video_effects = dict(enabled=True, size='custom', width=144, height=256,
                                          layout=layout, zoom=1.15, flip=True, effect=effect,
                                          temperature=.2, x=20, y=80)
                    out = root / f'out{i}.mp4'
                    export_video(p, root/'cache', out, threading.Event(), lambda *a: None,
                                 with_voice=False, preview=.2)
                    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                        '-show_streams', '-show_format', '-of', 'json', str(out)]))
                    v = next(x for x in data['streams'] if x['codec_type'] == 'video')
                    self.assertEqual((v['width'], v['height']), (144, 256))
                    self.assertEqual(v['sample_aspect_ratio'], '1:1')
                    self.assertTrue(any(x['codec_type'] == 'audio' for x in data['streams']))
                    self.assertAlmostEqual(float(data['format']['duration']), 1, delta=.15)
            self.assertFalse(list((root/'cache').glob('render-*')))


if __name__ == '__main__':
    unittest.main()
