import os
import shutil
import json
import logging
from tinydb import TinyDB, Query

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def migrate_db(state_json_path: str):
    if not os.path.exists(state_json_path):
        logger.error(f"State file not found at {state_json_path}")
        return

    db = TinyDB(state_json_path)
    assets_table = db.table('library_assets')
    
    # We only need to migrate BeatAssets
    BeatAssetQuery = Query()
    beats = assets_table.search(BeatAssetQuery.asset_type == 'beat')
    
    logger.info(f"Found {len(beats)} beats to migrate.")

    migrated_count = 0
    error_count = 0

    for beat in beats:
        try:
            beat_path = beat.get('path')
            if not beat_path or not os.path.exists(beat_path):
                logger.warning(f"Beat folder missing for {beat.get('name', 'Unknown')} at {beat_path}. Skipping physical migration.")
                continue

            # Create RAW and RELEASE directories
            raw_dir = "RAW"
            release_dir = "RELEASE"
            raw_path = os.path.join(beat_path, raw_dir)
            release_path = os.path.join(beat_path, release_dir)
            
            os.makedirs(raw_path, exist_ok=True)
            os.makedirs(release_path, exist_ok=True)

            # Move audio to RAW
            versions = beat.get('versions', {})
            main_filename = versions.get('main')
            new_main_path = main_filename
            
            if main_filename:
                # Check if it's already in RAW
                if not main_filename.startswith(raw_dir + os.sep):
                    old_audio_path = os.path.join(beat_path, main_filename)
                    if os.path.exists(old_audio_path):
                        new_audio_path = os.path.join(raw_path, os.path.basename(main_filename))
                        shutil.move(old_audio_path, new_audio_path)
                        new_main_path = os.path.join(raw_dir, os.path.basename(main_filename))
                        logger.info(f"Moved {main_filename} to RAW folder.")
                    else:
                        logger.warning(f"Main audio file {main_filename} not found at {old_audio_path}")
            else:
                 # Fallback: finding audio files
                 audio_exts = ('.wav', '.mp3', '.flac', '.aiff')
                 files = [f for f in os.listdir(beat_path) if os.path.isfile(os.path.join(beat_path, f)) and f.lower().endswith(audio_exts)]
                 if files:
                     for f in files:
                         shutil.move(os.path.join(beat_path, f), os.path.join(raw_path, f))
                     new_main_path = os.path.join(raw_dir, files[0])
                     logger.info(f"Moved {files} to RAW folder.")

            # Create metadata.json in root if missing
            metadata_path = os.path.join(beat_path, "metadata.json")
            if not os.path.exists(metadata_path):
                with open(metadata_path, 'w') as f:
                    json.dump({}, f)
                logger.info("Created empty metadata.json.")

            # Prepare update payload
            update_payload = {
                "raw_dir": raw_dir,
                "release_dir": release_dir,
                "has_mp3": beat.get('has_mp3', False),
                "has_master": beat.get('has_master', False),
                "stems_path": beat.get('stems_path', None)
            }
            
            if new_main_path and new_main_path != main_filename:
                versions["main"] = new_main_path
                update_payload["versions"] = versions

            # Ensure linked_assets is present
            if 'linked_assets' not in beat:
                 update_payload["linked_assets"] = {}
                 
            # Copy cover_image_id to linked_assets if present
            cover_id = beat.get("cover_image_id")
            if cover_id:
                linked = beat.get("linked_assets", {})
                if "cover" not in linked:
                    linked["cover"] = cover_id
                    update_payload["linked_assets"] = linked

            # Perform DB update
            assets_table.update(update_payload, doc_ids=[beat.doc_id])
            migrated_count += 1
            
        except Exception as e:
            logger.error(f"Error migrating beat {beat.get('name', 'Unknown')}: {str(e)}")
            error_count += 1

    logger.info(f"Migration completed. Successfully migrated {migrated_count} beats. Errors: {error_count}.")

if __name__ == "__main__":
    # Pointing to the actual state.json in the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    state_json = os.path.join(project_root, "state.json")
    migrate_db(state_json)
