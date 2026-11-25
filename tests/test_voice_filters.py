import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from studio.core import Cue,Project,raw_key,signature
from studio.voices import VIENEU_PREFIX,VOICES,VOICE_METADATA,matching_voices
from studio.ui import Window
from studio.voice_preview_ui import VoicePreviewDialog


class VoiceFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):self.window=Window()
    def tearDown(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater()

    def filter(self,controls,gender,region):
        controls.gender.setCurrentIndex(controls.gender.findData(gender))
        controls.region.setCurrentIndex(controls.region.findData(region))

    def test_catalogue_combines_gender_and_region_without_guessing_edge_accent(self):
        names=lambda gender,region:{v.removeprefix(VIENEU_PREFIX) for _,v in matching_voices(gender,region)}
        self.assertEqual(set(VOICE_METADATA),set(VOICES.values()))
        self.assertEqual(names('female','south'),{'Thùy Dung','Thục Đoan','Mỹ Duyên','Kim Thanh'})
        self.assertEqual(names('male','central'),{'Quang Sơn'})
        self.assertEqual(names('female','central'),{'Ngọc Trân'})
        self.assertEqual(names('male','unknown'),{'vi-VN-NamMinhNeural'})
        self.assertEqual(names('female','unknown'),{'vi-VN-HoaiMyNeural'})
        self.assertEqual(len(matching_voices()),27)

    def test_filtering_alone_preserves_project_audio_identity_and_dirty_state(self):
        w=self.window;w.p.cues=[Cue(0,1,'Xin chào')]
        before=signature(w.p);key=raw_key(w.p.cues[0],w.p)
        with patch.object(w.local_tts_session,'speak',side_effect=AssertionError('Filtering must not synthesize')):
            self.filter(w.voice_filters,'female','south')
        self.assertEqual(signature(w.p),before)
        self.assertEqual(raw_key(w.p.cues[0],w.p),key)
        self.assertFalse(w.dirty);self.assertEqual(w.undo,[])
        self.assertEqual(w.voice.currentData(),w.p.voice)
        self.assertIn('ngoài bộ lọc',w.voice.currentText())
        self.assertIn('4 giọng phù hợp',w.voice_filters.summary.text())
        w.voice.setCurrentIndex(w.voice.findData(VIENEU_PREFIX+'Mỹ Duyên'))
        self.assertEqual(w.p.voice,VIENEU_PREFIX+'Mỹ Duyên')
        self.assertTrue(w.dirty)
        self.assertNotEqual(signature(w.p),before)
        self.assertEqual(w.voice.count(),4)

    def test_per_cue_filter_keeps_default_and_saved_override_until_explicit_apply(self):
        w=self.window
        first=Cue(0,1,'Câu một')
        second=Cue(2,3,'Câu hai',voice=VIENEU_PREFIX+'Ngọc Trân')
        w.p.cues=[first,second];w.p.duration=4;w.model.refresh();w.select_id(first.id)
        second_key=raw_key(second,w.p)
        self.filter(w.cue_voice_filters,'female','south')
        self.assertEqual(w.cue_voice.currentData(),'')
        self.assertEqual(first.voice,'')
        self.assertFalse(w.editor_dirty)
        w.cue_voice.setCurrentIndex(w.cue_voice.findData(VIENEU_PREFIX+'Thục Đoan'))
        self.assertEqual(first.voice,'')
        self.assertTrue(w.commit_editor())
        self.assertEqual(first.voice,VIENEU_PREFIX+'Thục Đoan')
        self.assertEqual(w.p.voice,'vi-VN-NamMinhNeural')
        w.select_id(second.id)
        self.assertEqual(w.cue_voice.currentData(),VIENEU_PREFIX+'Ngọc Trân')
        self.assertIn('ngoài bộ lọc',w.cue_voice.currentText())
        self.assertEqual(raw_key(second,w.p),second_key)
        self.assertFalse(w.editor_dirty)

    def test_loading_and_undo_preserve_saved_voice_outside_current_filter(self):
        w=self.window
        self.filter(w.voice_filters,'male','south')
        w.p=Project(voice=VIENEU_PREFIX+'Trúc Ly')
        w.load_controls()
        self.assertEqual(w.voice.currentData(),VIENEU_PREFIX+'Trúc Ly')
        self.assertEqual(w.p.voice,VIENEU_PREFIX+'Trúc Ly')
        w.rate.setValue(10)
        self.assertEqual(w.p.voice,VIENEU_PREFIX+'Trúc Ly')
        w.undo_action()
        self.assertEqual(w.p.tts_rate,0)
        self.assertEqual(w.p.voice,VIENEU_PREFIX+'Trúc Ly')
        self.assertEqual(w.voice.currentData(),w.p.voice)

    def test_preview_filter_and_apply_select_intended_voice_without_auto_playback(self):
        w=self.window
        self.filter(w.voice_filters,'male','north')
        dialog=VoicePreviewDialog(w)
        try:
            with patch.object(dialog.player,'play') as play,patch.object(w,'start_job') as job:
                self.filter(dialog.filters,'female','south')
                dialog.voice.setCurrentIndex(dialog.voice.findData(VIENEU_PREFIX+'Kim Thanh'))
                play.assert_not_called();job.assert_not_called()
            self.assertEqual(w.p.voice,'vi-VN-NamMinhNeural')
            dialog.apply_to_project()
            self.assertEqual(w.p.voice,VIENEU_PREFIX+'Kim Thanh')
            self.assertEqual(w.voice.currentData(),VIENEU_PREFIX+'Kim Thanh')
            self.assertIn('ngoài bộ lọc',w.voice.currentText())
        finally:dialog.reject();dialog.deleteLater()


if __name__=='__main__':unittest.main()
