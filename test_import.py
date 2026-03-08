import os
import shutil
from app.core.library_manager_engine import LibraryManagerEngine

def test():
    # Setup dummy files
    test_dir = "/home/dave/.openclaw/workspace/projects/beat-manager/test_import_data"
    os.makedirs(test_dir, exist_ok=True)
    
    audio_path = os.path.join(test_dir, "test_beat.wav")
    with open(audio_path, "wb") as f:
        f.write(b"dummy audio data")
        
    notes_path = os.path.join(test_dir, "test_beat.txt")
    with open(notes_path, "w") as f:
        f.write("test notes content")
        
    engine = LibraryManagerEngine()
    
    print("Attempting to import beat asset...")
    try:
        asset = engine.import_beat_asset(
            name="Test Beat",
            audio_source=audio_path,
            notes_source=notes_path,
            delete_source=False
        )
        print(f"Import successful! Asset ID: {asset.id}")
        print(f"Asset Path: {asset.path}")
    except Exception as e:
        print(f"Import CRASHED with error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"Cleaned up {test_dir}")

if __name__ == "__main__":
    test()
