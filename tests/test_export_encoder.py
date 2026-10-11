import threading
import unittest
from unittest.mock import patch
from studio.core import Project, export_encoder, run


class EncoderTests(unittest.TestCase):
    def test_gpu_is_probed_at_output_size(self):
        p=Project(video_effects=dict(enabled=True,size='portrait'))
        with patch('studio.core.run') as probe:
            name,args=export_encoder(p,'ultrafast',threading.Event(),lambda *a:None)
        self.assertEqual(args[1],'h264_nvenc')
        self.assertIn('size=1080x1920',probe.call_args.args[0][7])
        self.assertEqual(probe.call_args.kwargs['timeout'],12)

    def test_missing_gpu_tries_others_then_cpu(self):
        with patch('studio.core.run',side_effect=RuntimeError('GPU unavailable')) as probe:
            name,args=export_encoder(Project(),'ultrafast',threading.Event(),lambda *a:None)
        self.assertEqual(probe.call_count,3)
        self.assertEqual(args[1],'libx264')
        self.assertIn('ultrafast',args)

    def test_next_gpu_after_timeout(self):
        with patch('studio.core.run',side_effect=[TimeoutError(),None]):
            name,args=export_encoder(Project(),'ultrafast',threading.Event(),lambda *a:None)
        self.assertEqual(args[1],'h264_qsv')

    def test_cancel_never_falls_back(self):
        with patch('studio.core.run',side_effect=InterruptedError()) as probe:
            with self.assertRaises(InterruptedError):
                export_encoder(Project(),'ultrafast',threading.Event(),lambda *a:None)
        self.assertEqual(probe.call_count,1)

    def test_other_presets_keep_cpu(self):
        with patch('studio.core.run') as probe:
            for preset in ('veryfast','medium'):
                name,args=export_encoder(Project(),preset,threading.Event(),lambda *a:None)
                self.assertEqual(args[1],'libx264')
                self.assertIn(preset,args)
        probe.assert_not_called()

    def test_probe_timeout_kills_child(self):
        import sys
        with self.assertRaises(TimeoutError):
            run([sys.executable,'-c','import time; time.sleep(10)'],timeout=.2)
