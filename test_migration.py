import os
import shutil
import json
import uuid
from tinydb import TinyDB

# Ensure scripts dir is importable
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'scripts')))
from migrate_assets_v2 import migrate_db

def setup_mock_data():
    test_dir = "test_migration_env"
    os.makedirs(test_dir, exist_ok=True)
    
    db_path = os.path.join(test_dir, "test_state.json")
    db = TinyDB(db_path)
    
    beats_dir = os.path.join(test_dir, "assets", "library", "beats")
    os.makedirs(beats_dir, exist_ok=True)
    
    # Create a mock beat folder (old structure)
    beat_id = str(uuid.uuid4())[:8]
    beat_path = os.path.join(beats_dir, beat_id)
    os.makedirs(beat_path, exist_ok=True)
    
    # Create fake audio and notes
    audio_file = f"raw-MyAwesomeBeat.wav"
    notes_file = "notes.txt"
    
    with open(os.path.join(beat_path, audio_file), "w") as f:
        f.write("fake audio content")
    with open(os.path.join(beat_path, notes_file), "w") as f:
        f.write("fake notes content")
        
    # Insert old schema record
    db.table('library_assets').insert({
        "id": beat_id,
        "name": "MyAwesomeBeat",
        "asset_type": "beat",
        "data_type": "audio",
        "path": beat_path,
        "versions": {"main": audio_file},
        "notes_file": notes_file
    })
    
    return test_dir, db_path, beat_path, audio_file

def run_test():
    print("Setting up mock data...")
    test_dir, db_path, beat_path, audio_file = setup_mock_data()
    
    print("Running migration...")
    migrate_db(db_path)
    
    print("Verifying results...")
    # Verify folder structure
    assert os.path.exists(os.path.join(beat_path, "RAW")), "RAW folder not created"
    assert os.path.exists(os.path.join(beat_path, "RELEASE")), "RELEASE folder not created"
    assert os.path.exists(os.path.join(beat_path, "RAW", audio_file)), "Audio file not moved to RAW"
    assert not os.path.exists(os.path.join(beat_path, audio_file)), "Audio file still in root"
    assert os.path.exists(os.path.join(beat_path, "notes.txt")), "Notes file missing from root"
    assert os.path.exists(os.path.join(beat_path, "metadata.json")), "metadata.json not created in root"
    
    # Verify DB update
    db = TinyDB(db_path)
    record = db.table('library_assets').all()[0]
    
    assert record.get("raw_dir") == "RAW", "raw_dir not set in DB"
    assert record.get("release_dir") == "RELEASE", "release_dir not set in DB"
    assert "has_mp3" in record, "has_mp3 not set in DB"
    assert "has_master" in record, "has_master not set in DB"
    assert "stems_path" in record, "stems_path not set in DB"
    assert record["versions"]["main"] == os.path.join("RAW", audio_file), "versions['main'] not updated correctly"
    
    print("ALL TESTS PASSED!")
    
    # Cleanup
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    run_test()
