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

    def test_cancel_preserves_input(self):
        original = dict(enabled=False, zoom=1.0)
        d = EffectsDialog(None, original)
        d.controls['zoom'].setValue(1.5)
        d.reject()
        self.assertEqual(original, dict(enabled=False, zoom=1.0))
        self.assertEqual(d.result(), QDialog.Rejected)


if __name__ == '__main__': unittest.main()
