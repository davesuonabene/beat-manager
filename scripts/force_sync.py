import os
import json
from tinydb import TinyDB, Query
from app.core.library_manager_engine import LibraryManagerEngine
from app.models.schemas import AssetType, AudioAsset, BeatAsset

BASE_DIR = "/home/dave/.openclaw/workspace/projects/beat-manager"
STATE_JSON = os.path.join(BASE_DIR, "state.json")

def force_sync():
    engine = LibraryManagerEngine()
    db = TinyDB(STATE_JSON)
    assets_table = db.table('library_assets')
    
    # Get all registered paths
    registered_paths = {a.get('path') for a in assets_table.all()}
    
    added_count = 0
    
    # Check Beats directory
    beats_root = engine.beats_dir
    for col_name in os.listdir(beats_root):
        col_path = os.path.join(beats_root, col_name)
        if not os.path.isdir(col_path): continue
        
        for folder_name in os.listdir(col_path):
            folder_path = os.path.join(col_path, folder_name)
            if not os.path.isdir(folder_path): continue
            
            if folder_path not in registered_paths:
                print(f"Found missing BEAT folder: {folder_name}")
                # Try to reconstruct BeatAsset
                # Extract ID from folder_name (expected format: Name_ID)
                parts = folder_name.split('_')
                asset_id = parts[-1] if len(parts) > 1 else folder_name[:8]
                name = "_".join(parts[:-1]) if len(parts) > 1 else folder_name
                
                # Find main audio
                raw_dir = "RAW"
                main_file = None
                raw_full = os.path.join(folder_path, raw_dir)
                if os.path.exists(raw_full):
                    files = [f for f in os.listdir(raw_full) if f.endswith(('.wav', '.mp3'))]
                    if files: main_file = os.path.join(raw_dir, files[0])
                
                if main_file:
                    new_beat = BeatAsset(
                        id=asset_id,
                        name=name,
                        path=folder_path,
                        versions={"main": main_file},
                        raw_dir=raw_dir,
                        release_dir="RELEASE",
                        collection_id=None # Hard to guess without more logic
                    )
                    assets_table.insert(new_beat.dict())
                    added_count += 1
                    print(f"  Added to state: {name}")

    print(f"Force sync complete. Added {added_count} missing assets.")

if __name__ == "__main__":
    force_sync()
