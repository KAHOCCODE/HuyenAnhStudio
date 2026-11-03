import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QImage, QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from studio.effects_ui import EffectsDialog


class DirectFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = EffectsDialog(None, {})
        self.dialog.resize(1000, 650)
        image = QImage(640, 360, QImage.Format_RGB32)
        image.fill(QColor('blue'))
        self.dialog.canvas.image = image
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()

    def test_edit_enables_and_drag_updates_export_settings(self):
        d = self.dialog
        self.assertFalse(d.enabled.isChecked())
        self.assertTrue(d.controls['zoom'].isEnabled())
        d.controls['zoom'].setValue(1.5)
        self.assertTrue(d.enabled.isChecked())
        canvas = d.canvas
        center = canvas.geometry_data()[0].center().toPoint()
        QTest.mousePress(canvas, Qt.LeftButton, pos=center)
        QTest.mouseMove(canvas, center+QPoint(25, 10))
        QTest.mouseRelease(canvas, Qt.LeftButton, pos=center+QPoint(25, 10))
        self.assertLess(d.controls['x'].value(), 50)
        self.assertLess(d.controls['y'].value(), 50)
        d.apply(False)
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertLess(d.values['x'], 50)

    def test_wheel_corner_and_center(self):
        d = self.dialog; canvas = d.canvas
        center = canvas.geometry_data()[0].center()
        event = QWheelEvent(center, center, QPoint(), QPoint(0, 120),
                            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        self.app.sendEvent(canvas, event)
        self.assertAlmostEqual(d.controls['zoom'].value(), 1.05)
        corner = canvas.handles()[3].center().toPoint()
        QTest.mousePress(canvas, Qt.LeftButton, pos=corner)
        QTest.mouseMove(canvas, corner+QPoint(20, 20))
        QTest.mouseRelease(canvas, Qt.LeftButton, pos=corner+QPoint(20, 20))
        self.assertGreater(d.controls['zoom'].value(), 1.05)
        d.controls['x'].setValue(15)
        QTest.mouseDClick(canvas, Qt.LeftButton, pos=center.toPoint())
        self.assertEqual(d.controls['x'].value(), 50)

    def test_full_export_action_is_distinct_from_sample(self):
        self.dialog.controls['zoom'].setValue(1.15)
        self.dialog.export_full()
        self.assertEqual(self.dialog.result(), QDialog.Accepted)
        self.assertTrue(self.dialog.full_export_requested)
        self.assertFalse(self.dialog.preview_requested)
        self.assertEqual(self.dialog.values['zoom'], 1.15)

    def test_full_export_ignores_timeline_selection_and_needs_no_saved_project(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from studio.core import Project
        from studio.ui import Window, QMessageBox
        project=Project(video='/tmp/source.mp4',duration=120,has_audio=True)
        project.video_effects=dict(enabled=True,zoom=1.15)
        fake=SimpleNamespace(p=project,cache='/tmp/cache',editor_dirty=False,
            selection=(5,15),guard=lambda:True,show_full_result=Mock(),export_done=Mock())
        fake.start_job=lambda work,done,label:work(None,lambda *a:None)
        with patch('studio.ui.check_project'), patch('studio.ui.QFileDialog.getSaveFileName',
                return_value=('/tmp/full.mp4','')), patch('studio.ui.export_video') as render:
            Window.export(fake,voice_choice=QMessageBox.No,preserve_original=True,show_result=True)
        args,kwargs=render.call_args
        self.assertIsNone(kwargs['preview'])
        self.assertIsNone(kwargs['segment'])
        self.assertEqual(args[0].duration,120)
        self.assertEqual(args[0].video_effects['zoom'],1.15)
        self.assertEqual(args[0].original_volume,1)
        self.assertEqual(project.original_volume,.12)

    def test_cancel_preserves_input(self):
        original = dict(enabled=False, zoom=1.0)
        d = EffectsDialog(None, original)
        d.controls['zoom'].setValue(1.5)
        d.reject()
        self.assertEqual(original, dict(enabled=False, zoom=1.0))
        self.assertEqual(d.result(), QDialog.Rejected)


if __name__ == '__main__': unittest.main()
