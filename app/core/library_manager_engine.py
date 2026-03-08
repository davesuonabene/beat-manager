import os
import shutil
import json
from typing import List, Optional, Dict, Any
from tinydb import Query
import mutagen
from app.core.state_manager import StateManager
from app.models.schemas import BeatAsset, AssetType, LibraryAsset

# Project paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
STATE_JSON = os.path.join(project_root, "state.json")
DEFAULT_LIBRARY_ROOT = os.path.join(project_root, "assets", "library")

class LibraryManagerEngine:
    def __init__(self, state_json: str = STATE_JSON, library_root: str = DEFAULT_LIBRARY_ROOT):
        self.state_manager = StateManager(state_json)
        self.library_root = library_root
        self.assets_table = self.state_manager.db.table('library_assets')
        
        # Ensure library root exists
        if not os.path.exists(self.library_root):
            os.makedirs(self.library_root, exist_ok=True)

    def _slugify(self, text: str) -> str:
        return text.lower().replace(" ", "-").replace("_", "-")

    def create_beat_asset(self, name: str, audio_source: str, notes: str = "") -> BeatAsset:
        """Create a new beat asset by copying files to the centralized library."""
        asset_id = self._slugify(name)
        asset_dir = os.path.join(self.library_root, "beats", asset_id)
        
        # Avoid overwriting
        if os.path.exists(asset_dir):
            counter = 1
            while os.path.exists(f"{asset_dir}-{counter}"):
                counter += 1
            asset_id = f"{asset_id}-{counter}"
            asset_dir = f"{asset_dir}-{counter}"

        os.makedirs(asset_dir, exist_ok=True)

        # Copy audio file
        audio_ext = os.path.splitext(audio_source)[1]
        dest_audio = f"audio{audio_ext}"
        shutil.copy2(audio_source, os.path.join(asset_dir, dest_audio))

        # Create notes file
        notes_file = "notes.txt"
        with open(os.path.join(asset_dir, notes_file), "w") as f:
            f.write(notes)

        # Extract basic metadata using mutagen
        duration = 0
        try:
            audio = mutagen.File(audio_source)
            if audio and hasattr(audio.info, 'length'):
                duration = audio.info.length
        except:
            pass

        # Create asset object
        asset = BeatAsset(
            id=asset_id,
            type=AssetType.BEAT,
            name=name,
            path=asset_dir,
            audio_file=dest_audio,
            notes_file=notes_file,
            duration=duration,
            metadata={}
        )

        # Store in DB
        self.assets_table.insert(asset.dict())
        return asset

    def scan_for_import(self, search_path: str) -> List[Dict[str, Any]]:
        """Scan a path for potential beat assets (audio + matching txt)."""
        if not os.path.exists(search_path):
            return []

        potential_assets = []
        audio_extensions = ('.wav', '.mp3', '.flac', '.aiff')
        
        for root, _, files in os.walk(search_path):
            for file in files:
                if file.lower().endswith(audio_extensions):
                    audio_path = os.path.join(root, file)
                    base_name = os.path.splitext(file)[0]
                    
                    # Robust matching for .txt notes
                    notes_path = None
                    # Option 1: my_beat.txt
                    potential_txt_1 = os.path.join(root, f"{base_name}.txt")
                    # Option 2: my_beat.wav.txt
                    potential_txt_2 = os.path.join(root, f"{file}.txt")
                    
                    if os.path.exists(potential_txt_1):
                        notes_path = potential_txt_1
                    elif os.path.exists(potential_txt_2):
                        notes_path = potential_txt_2
                    
                    potential_assets.append({
                        "name": base_name,
                        "audio_path": audio_path,
                        "notes_path": notes_path,
                        "status": "ready"
                    })
        
        return potential_assets

    def import_beat_asset(self, name: str, audio_source: str, notes_source: Optional[str] = None, delete_source: bool = False) -> BeatAsset:
        """Import a beat asset from source files, copying them to the library."""
        notes_content = ""
        if notes_source and os.path.exists(notes_source):
            with open(notes_source, "r") as f:
                notes_content = f.read()
        
        asset = self.create_beat_asset(name, audio_source, notes_content)

        if delete_source:
            try:
                if os.path.exists(audio_source):
                    os.remove(audio_source)
                if notes_source and os.path.exists(notes_source):
                    os.remove(notes_source)
            except Exception as e:
                # We don't want to crash if deletion fails after a successful copy
                pass
        
        return asset

    def get_assets(self, asset_type: Optional[AssetType] = None) -> List[Dict[str, Any]]:
        if asset_type:
            return self.assets_table.search(Query().type == asset_type.value)
        return self.assets_table.all()

    def get_asset_by_id(self, asset_id: str) -> Optional[Dict[str, Any]]:
        return self.assets_table.get(Query().id == asset_id)

    def delete_asset(self, asset_id: str):
        asset = self.assets_table.get(Query().id == asset_id)
        if asset:
            if os.path.exists(asset['path']):
                shutil.rmtree(asset['path'])
            self.assets_table.remove(Query().id == asset_id)

    def update_notes(self, asset_id: str, new_notes: str):
        asset_doc = self.assets_table.get(Query().id == asset_id)
        if asset_doc:
            notes_path = os.path.join(asset_doc['path'], asset_doc['notes_file'])
            with open(notes_path, "w") as f:
                f.write(new_notes)
            return True
        return False

    def get_notes(self, asset_id: str) -> str:
        asset_doc = self.assets_table.get(Query().id == asset_id)
        if asset_doc:
            notes_path = os.path.join(asset_doc['path'], asset_doc['notes_file'])
            if os.path.exists(notes_path):
                with open(notes_path, "r") as f:
                    return f.read()
        return ""
