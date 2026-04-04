import os
import shutil
import json
from tinydb import TinyDB, Query

# Project paths
BASE_DIR = "/home/dave/.openclaw/workspace/projects/beat-manager"
STATE_JSON = os.path.join(BASE_DIR, "state.json")

def sanitize_filename(name):
    import re
    # Replace non-alphanumeric (except . - _) with _
    s = re.sub(r'[^a-zA-Z0-9\.\-_]', '_', name)
    # Replace multiple underscores with one
    s = re.sub(r'_+', '_', s)
    # Remove leading/trailing underscores
    return s.strip('_')

def run_sanitization():
    if not os.path.exists(STATE_JSON):
        print(f"Error: {STATE_JSON} not found.")
        return

    db = TinyDB(STATE_JSON)
    assets_table = db.table('library_assets')
    assets = assets_table.all()

    modified_count = 0
    
    print(f"Scanning {len(assets)} assets...")

    for asset in assets:
        asset_id = asset.get('id')
        asset_type = asset.get('asset_type')
        name = asset.get('name')
        old_path = asset.get('path')

        if asset_type != 'beat' or not old_path or not os.path.exists(old_path):
            continue

        safe_name = sanitize_filename(name)
        parent_dir = os.path.dirname(old_path)
        # New folder naming: BeatName_ID
        new_path = os.path.join(parent_dir, f"{safe_name}_{asset_id}")

        # 1. Rename Folder if needed
        if old_path != new_path:
            # Handle collision
            if os.path.exists(new_path) and new_path != old_path:
                count = 1
                while os.path.exists(f"{new_path}_{count}"):
                    count += 1
                new_path = f"{new_path}_{count}"
            
            print(f"Renaming folder: {os.path.basename(old_path)} -> {os.path.basename(new_path)}")
            os.rename(old_path, new_path)
            asset['path'] = new_path
            modified_count += 1

        # 2. Rename Raw Audio inside RAW/
        versions = asset.get('versions', {})
        main_rel = versions.get('main')
        if main_rel:
            old_raw_full = os.path.join(new_path, main_rel)
            if os.path.exists(old_raw_full):
                raw_dir = asset.get('raw_dir', 'RAW')
                ext = os.path.splitext(main_rel)[1]
                # New raw filename: BeatName_raw.ext
                new_raw_filename = f"{safe_name}_raw{ext}"
                new_raw_full = os.path.join(new_path, raw_dir, new_raw_filename)
                
                if old_raw_full != new_raw_full:
                    print(f"  Renaming raw: {os.path.basename(old_raw_full)} -> {new_raw_filename}")
                    os.rename(old_raw_full, new_raw_full)
                    versions['main'] = os.path.join(raw_dir, new_raw_filename)
                    asset['versions'] = versions
                    modified_count += 1

        # Update the entry in DB
        assets_table.update(asset, doc_ids=[asset.doc_id])

    print(f"Sanitization complete. Modified {modified_count} items.")

if __name__ == "__main__":
    run_sanitization()
