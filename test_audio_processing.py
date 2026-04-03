import os
import shutil
import uuid
import unittest
from unittest.mock import patch, MagicMock
from tinydb import TinyDB

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.core.library_manager_engine import LibraryManagerEngine
from app.models.schemas import BeatAsset, AssetType, AssetDataType

class TestAudioProcessing(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_audio_proc_env"
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, "test_state.json")
        self.engine = LibraryManagerEngine(state_json=self.db_path, library_root=self.test_dir)
        
        # Setup a dummy beat
        self.beat_id = str(uuid.uuid4())[:8]
        self.beat_path = os.path.join(self.engine.beats_dir, self.beat_id)
        os.makedirs(self.beat_path, exist_ok=True)
        
        self.raw_dir = "RAW"
        self.release_dir = "RELEASE"
        os.makedirs(os.path.join(self.beat_path, self.raw_dir), exist_ok=True)
        os.makedirs(os.path.join(self.beat_path, self.release_dir), exist_ok=True)
        
        self.audio_filename = "raw-audio.wav"
        self.audio_path = os.path.join(self.beat_path, self.raw_dir, self.audio_filename)
        with open(self.audio_path, "w") as f:
            f.write("fake audio")
            
        beat = BeatAsset(
            id=self.beat_id,
            name="TestBeat",
            path=self.beat_path,
            versions={"main": os.path.join(self.raw_dir, self.audio_filename)},
            raw_dir=self.raw_dir,
            release_dir=self.release_dir
        )
        self.engine.assets_table.insert(beat.dict())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('subprocess.run')
    def test_generate_mp3_for_beat(self, mock_run):
        mock_run.return_value = MagicMock()
        
        success = self.engine.generate_mp3_for_beat(self.beat_id)
        self.assertTrue(success)
        
        record = self.engine.assets_table.get(doc_id=1)
        self.assertTrue(record.get('has_mp3'))
        
        # Verify ffmpeg arguments
        expected_source = os.path.join(self.beat_path, self.raw_dir, self.audio_filename)
        expected_target = os.path.join(self.beat_path, self.release_dir, "raw-audio.mp3")
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn(expected_source, cmd)
        self.assertIn(expected_target, cmd)

    def test_add_master_version(self):
        fake_master_path = os.path.join(self.test_dir, "my_master.wav")
        with open(fake_master_path, "w") as f:
            f.write("fake master")
            
        success = self.engine.add_master_version(self.beat_id, fake_master_path)
        self.assertTrue(success)
        
        record = self.engine.assets_table.get(doc_id=1)
        self.assertTrue(record.get('has_master'))
        
        expected_copied_path = os.path.join(self.beat_path, self.release_dir, "master_my_master.wav")
        self.assertTrue(os.path.exists(expected_copied_path))

if __name__ == '__main__':
    unittest.main()
