import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import threading
import unittest
from unittest.mock import Mock,patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from studio.ui import Window,QMessageBox
from studio.core import Project,Cue
from studio.composition import SUBTITLE_PRESETS,new_layer


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=Window();self.w.show()
        self.w.p=Project(video='/tmp/workflow-source.mp4',width=640,height=360,duration=120,cues=[Cue(0,1,'Câu Việt')])
        # Decode is independently covered with real video; this suite exercises navigation and job state.
        self.decode=patch.object(self.w,'refresh_effect_preview');self.decoder_mock=self.decode.start()
        self.w.load_controls();self.w.changed(dirty=False)
    def tearDown(self):
        self.decode.stop();self.w.close_cpu();self.w.dirty=False;self.w.close();self.w.deleteLater();QTest.qWait(20)
    def test_navigation_preserves_project_and_has_one_inspector(self):
        before=self.w.p.to_dict();self.decoder_mock.reset_mock()
        for _ in range(2):
            for stage in range(5):self.assertTrue(self.w.go_stage(stage))
        self.assertEqual(before,self.w.p.to_dict());self.decoder_mock.assert_not_called()
        self.assertEqual(self.w.workflow_stack.count(),5)
        self.assertFalse(self.w.p.mask['enabled'])
        self.assertEqual(len([x for x in self.w.findChildren(QPushButton) if x.text()=='Xem thử 10 giây']),1)
        self.assertEqual(len([x for x in self.w.findChildren(QPushButton) if x.text()=='Xuất toàn bộ video…']),1)
        self.w.go_stage(2);panel=self.w.layers_panel;self.w.go_stage(1);self.w.go_stage(2)
        self.assertIs(panel,self.w.layers_panel)
    def test_source_edit_mode_ends_on_stage_change(self):
        self.w.go_stage(1);self.w.mask_edit.setChecked(True)
        self.w.go_stage(2);self.assertFalse(self.w.mask_edit.isChecked())
        self.assertFalse(self.w.split.widget(0).isVisible())
        self.w.go_stage(3);self.assertTrue(self.w.split.widget(0).isVisible());self.assertFalse(self.w.timeline.isVisible())
        self.w.timeline_toggle.setChecked(True);self.assertTrue(self.w.timeline.isVisible())
        self.w.focus_preview();self.assertFalse(self.w.timeline.isVisible())
        self.w.focus_preview();self.assertTrue(self.w.timeline.isVisible())
        self.w.go_stage(4);self.assertFalse(self.w.timeline.isVisible())
    def test_subtitle_presets_roundtrip_and_undo(self):
        self.w.go_stage(3)
        for i,(_,values) in enumerate(SUBTITLE_PRESETS):
            self.w.preset.setCurrentIndex(i)
            self.assertTrue(all(self.w.p.style.get(k,v)==v for k,v in values.items()))
        self.w.p.style['color']='#123456';self.w.load_controls()
        self.assertEqual(self.w.preset.currentIndex(),len(SUBTITLE_PRESETS))
        self.w.preset.setCurrentIndex(4);self.w.undo_action()
        self.assertEqual(self.w.p.style['color'],'#123456')
    def test_export_and_preview_share_audio_and_no_hidden_overrides(self):
        w=self.w;w.p.original_volume=.37;w.p.original_muted=True;w.load_controls();w.go_stage(4)
        w.include_voice.setChecked(False);w.selection=(5,15)
        w.start_job=lambda fn,done,label:fn(threading.Event(),lambda *a:None)
        with patch('studio.ui.check_project'),patch('studio.ui.QFileDialog.getSaveFileName',return_value=('/tmp/workflow-output.mp4','')),patch('studio.ui.export_video') as render:
            w.export_workflow()
            full=render.call_args
            self.assertEqual(full.args[0].original_volume,.37);self.assertTrue(full.args[0].original_muted)
            self.assertIsNone(full.kwargs['preview']);self.assertIsNone(full.kwargs['segment'])
            w.render_preview();sample=render.call_args
            self.assertEqual(sample.args[0].original_volume,.37);self.assertTrue(sample.args[0].original_muted)
            self.assertFalse(sample.kwargs['with_voice']);self.assertIsNotNone(sample.kwargs['preview'])
        self.assertEqual(w.p.original_volume,.37)
    def test_voice_scope_dispatches_only_selected_action(self):
        actions=[Mock() for _ in range(4)]
        for name,action in zip(('show_batches','generate','generate_selected','generate_region'),actions):setattr(self.w,name,action)
        for i,action in enumerate(actions):
            self.w.voice_scope.setCurrentIndex(i);self.w.generate_workflow();action.assert_called_once()
        self.assertEqual(sum(a.call_count for a in actions),4)
    def test_busy_job_locks_stage_controls_until_completion(self):
        finish=threading.Event();done=Mock()
        self.w.start_job(lambda cancel,report:finish.wait(2),done,'Test task')
        try:
            self.assertFalse(self.w.workflow_stack.isEnabled());self.assertFalse(self.w.go_stage(2));self.assertFalse(self.w.sample_btn.isEnabled())
        finally:finish.set()
        for _ in range(60):
            QTest.qWait(20)
            if not self.w.busy:break
        self.assertFalse(self.w.busy);self.assertTrue(self.w.workflow_stack.isEnabled());done.assert_called_once()
    def test_logo_hides_typography_and_editor_stays_in_app(self):
        self.w.p.overlays=[new_layer('image',120)];self.w.go_stage(2);QTest.qWait(30)
        self.assertFalse(self.w.layers_panel.controls['font'].isVisible())
        self.assertTrue(self.w.layers_panel.logo_button.isVisible())
        self.w.go_stage(3);self.w.select_id(self.w.p.cues[0].id);self.w.show_editor()
        self.assertFalse(self.w.editor_dialog.isFloating());self.assertFalse(self.w.timeline.isVisible())
