import os
import shutil
import uuid
from typing import List, Optional, Dict, Any
from tinydb import Query
import mutagen
from app.core.state_manager import StateManager
from app.models.schemas import (
    LibraryAsset, AssetDataType, AssetType, 
    AudioAsset, BeatAsset, ImageAsset
)

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
        
        # Ensure subdirectories exist
        self.audio_dir = os.path.join(self.library_root, "audio")
        self.beats_dir = os.path.join(self.library_root, "beats")
        self.image_dir = os.path.join(self.library_root, "images")
        for d in [self.audio_dir, self.beats_dir, self.image_dir]:
            os.makedirs(d, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        return "".join([c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in name]).strip().replace(' ', '_')

    def get_assets(self, data_type: Optional[AssetDataType] = None, asset_type: Optional[AssetType] = None) -> List[Dict[str, Any]]:
        q = Query()
        results = self.assets_table.all()
        if data_type:
            results = [r for r in results if r.get('data_type') == data_type.value]
        if asset_type:
            results = [r for r in results if r.get('asset_type') == asset_type.value]
        return results

    def import_raw_audio(self, name: str, audio_source: str, notes_source: Optional[str] = None, delete_source: bool = False) -> AudioAsset:
        """Import a raw audio file and its notes into the central audio folder."""
        ext = os.path.splitext(audio_source)[1]
        safe_name = self._sanitize_filename(name)
        
        dest_audio_filename = f"{safe_name}{ext}"
        dest_audio_path = os.path.join(self.audio_dir, dest_audio_filename)
        
        # Handle filename collisions
        if os.path.exists(dest_audio_path):
            count = 1
            while os.path.exists(os.path.join(self.audio_dir, f"{safe_name}_{count}{ext}")):
                count += 1
            safe_name = f"{safe_name}_{count}"
            dest_audio_filename = f"{safe_name}{ext}"
            dest_audio_path = os.path.join(self.audio_dir, dest_audio_filename)

        shutil.copy2(audio_source, dest_audio_path)
        
        dest_notes_filename = None
        if notes_source and os.path.exists(notes_source):
            dest_notes_filename = f"{safe_name}.txt"
            shutil.copy2(notes_source, os.path.join(self.audio_dir, dest_notes_filename))
        elif not notes_source:
             # Create empty notes if none provided
             dest_notes_filename = f"{safe_name}.txt"
             open(os.path.join(self.audio_dir, dest_notes_filename), 'w').close()

        # Extract metadata
        duration = 0
        try:
            audio = mutagen.File(dest_audio_path)
            if audio and hasattr(audio.info, 'length'):
                duration = audio.info.length
        except:
            pass

        asset = AudioAsset(
            name=name,
            path=dest_audio_path, # For raw audio, path points to the file
            audio_file=dest_audio_filename,
            notes_file=dest_notes_filename,
            duration=duration,
            asset_type=AssetType.RAW
        )

        self.assets_table.insert(asset.dict())
        
        if delete_source:
            try:
                os.remove(audio_source)
                if notes_source: os.remove(notes_source)
            except: pass
            
        return asset

    def import_image(self, name: str, source_path: str, delete_source: bool = False) -> ImageAsset:
        """Import an image file into the central images folder."""
        ext = os.path.splitext(source_path)[1]
        safe_name = self._sanitize_filename(name)
        
        dest_filename = f"{safe_name}{ext}"
        dest_path = os.path.join(self.image_dir, dest_filename)
        
        # Handle filename collisions
        if os.path.exists(dest_path):
            count = 1
            while os.path.exists(os.path.join(self.image_dir, f"{safe_name}_{count}{ext}")):
                count += 1
            dest_filename = f"{safe_name}_{count}{ext}"
            dest_path = os.path.join(self.image_dir, dest_filename)

        shutil.copy2(source_path, dest_path)

        asset = ImageAsset(
            name=name,
            path=dest_path,
            data_type=AssetDataType.IMAGE,
            asset_type=AssetType.COVER
        )

        self.assets_table.insert(asset.dict())
        
        if delete_source:
            try: os.remove(source_path)
            except: pass
            
        return asset

    def set_beat_cover(self, beat_id: str, image_id: str):
        """Links an image asset as the cover for a beat asset."""
        self.assets_table.update({"cover_image_id": image_id}, Query().id == beat_id)

    def create_beat_from_audio(self, audio_asset_id: str, beat_name: Optional[str] = None) -> BeatAsset:
        """Convert a raw audio asset into a structured BEAT asset folder."""
        audio_doc = self.assets_table.get(doc_id=int(audio_asset_id) if isinstance(audio_asset_id, int) or audio_asset_id.isdigit() else 0)
        # Fallback search if doc_id fails
        if not audio_doc:
            audio_doc = self.assets_table.get(Query().id == audio_asset_id)
        
        if not audio_doc or audio_doc.get('asset_type') != AssetType.RAW:
            raise ValueError("Valid raw audio asset required to create a beat.")

        name = beat_name or audio_doc['name']
        asset_id = str(uuid.uuid4())[:8]
        beat_path = os.path.join(self.beats_dir, asset_id)
        os.makedirs(beat_path, exist_ok=True)

        # Move files
        old_audio_path = audio_doc['path']
        audio_ext = os.path.splitext(old_audio_path)[1]
        new_audio_filename = f"main{audio_ext}"
        new_audio_path = os.path.join(beat_path, new_audio_filename)
        shutil.move(old_audio_path, new_audio_path)

        new_notes_filename = "notes.txt"
        if audio_doc.get('notes_file'):
            old_notes_path = os.path.join(os.path.dirname(old_audio_path), audio_doc['notes_file'])
            if os.path.exists(old_notes_path):
                shutil.move(old_notes_path, os.path.join(beat_path, new_notes_filename))
        
        if not os.path.exists(os.path.join(beat_path, new_notes_filename)):
            open(os.path.join(beat_path, new_notes_filename), 'w').close()

        beat = BeatAsset(
            id=asset_id,
            name=name,
            path=beat_path,
            versions={"main": new_audio_filename},
            notes_file=new_notes_filename,
            duration=audio_doc.get('duration'),
            bpm=audio_doc.get('bpm'),
            key=audio_doc.get('key')
        )

        # Remove old raw audio entry and insert new beat entry
        if hasattr(audio_doc, 'doc_id'):
            self.assets_table.remove(doc_ids=[audio_doc.doc_id])
        else:
            self.assets_table.remove(Query().id == audio_doc['id'])
            
        self.assets_table.insert(beat.dict())
        return beat

    def rename_asset(self, asset_id: str, new_name: str):
        asset_doc = self.assets_table.get(Query().id == asset_id)
        if not asset_doc: return False

        old_name = asset_doc.get('name')
        if old_name == new_name: return True

        safe_new_name = self._sanitize_filename(new_name)
        asset_type = asset_doc.get('asset_type', asset_doc.get('type', 'raw'))

        if asset_type == AssetType.RAW or asset_type == 'raw':
            # Rename files in the shared folder
            old_path = asset_doc.get('path')
            if not old_path or not os.path.exists(old_path): return False
            
            ext = os.path.splitext(old_path)[1]
            new_audio_filename = f"{safe_new_name}{ext}"
            new_path = os.path.join(self.audio_dir, new_audio_filename)
            
            if os.path.exists(new_path):
                 return False

            os.rename(old_path, new_path)
            
            new_notes_filename = None
            if asset_doc.get('notes_file'):
                old_notes_path = os.path.join(self.audio_dir, asset_doc['notes_file'])
                new_notes_filename = f"{safe_new_name}.txt"
                new_notes_path = os.path.join(self.audio_dir, new_notes_filename)
                if os.path.exists(old_notes_path):
                    os.rename(old_notes_path, new_notes_path)
            
            self.assets_table.update({
                "name": new_name,
                "path": new_path,
                "audio_file": new_audio_filename,
                "notes_file": new_notes_filename
            }, Query().id == asset_id)
            
        else:
            self.assets_table.update({"name": new_name}, Query().id == asset_id)
        
        return True

    def update_asset(self, asset_id: str, updates: Dict[str, Any]) -> bool:
        """Update arbitrary metadata fields (like bpm, key) for an asset."""
        asset = self.assets_table.get(Query().id == asset_id)
        if not asset: return False
        
        # Prevent modifying core fields via this method
        safe_updates = {k: v for k, v in updates.items() if k not in ('id', 'path', 'asset_type', 'data_type', 'created_at')}
        
        if safe_updates:
            self.assets_table.update(safe_updates, Query().id == asset_id)
            return True
        return False

    def delete_asset(self, asset_id: str) -> bool:
        """Safely deletes an asset and its physical files."""
        try:
            asset = self.assets_table.get(Query().id == asset_id)
            if not asset:
                return False
                
            asset_type = asset.get('asset_type', asset.get('type', 'raw'))
            path = asset.get('path')
            
            if path and os.path.exists(path):
                try:
                    if asset_type == AssetType.RAW or asset_type == 'raw':
                        if os.path.isfile(path):
                            os.remove(path)
                        # Try to remove associated notes if it's a raw audio asset
                        notes_file = asset.get('notes_file')
                        if notes_file:
                            notes_path = os.path.join(self.audio_dir, notes_file)
                            if os.path.exists(notes_path):
                                os.remove(notes_path)
                    else:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                except OSError:
                    # Log but continue to remove from DB if requested? 
                    # For now, we want the DB to stay in sync with disk if possible.
                    pass

            self.assets_table.remove(Query().id == asset_id)
            return True
        except Exception:
            return False

    def sync_library_with_disk(self) -> int:
        """Removes database entries for assets whose files no longer exist on disk."""
        assets = self.assets_table.all()
        removed_count = 0
        for asset in assets:
            path = asset.get('path')
            # For RAW, path is the file. For BEAT, path is the folder.
            if not path or not os.path.exists(path):
                self.assets_table.remove(doc_ids=[asset.doc_id])
                removed_count += 1
        return removed_count

    def scan_for_import(self, search_path: str) -> List[Dict[str, Any]]:
        """Scan a path for potential audio and image assets."""
        if not os.path.exists(search_path):
            return []

        existing_names = {a.get('name') for a in self.assets_table.all() if a.get('name')}

        potential_assets = []
        audio_extensions = ('.wav', '.mp3', '.flac', '.aiff')
        image_extensions = ('.jpg', '.jpeg', '.png', '.webp')
        
        for root, _, files in os.walk(search_path):
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith(audio_extensions):
                    audio_path = os.path.join(root, file)
                    base_name = os.path.splitext(file)[0]
                    
                    notes_path = None
                    potential_txt_1 = os.path.join(root, f"{base_name}.txt")
                    potential_txt_2 = os.path.join(root, f"{file}.txt")
                    
                    if os.path.exists(potential_txt_1):
                        notes_path = potential_txt_1
                    elif os.path.exists(potential_txt_2):
                        notes_path = potential_txt_2
                    
                    status = "Exists" if base_name in existing_names else "New"
                    
                    potential_assets.append({
                        "name": base_name,
                        "type": "audio",
                        "path": audio_path,
                        "notes_path": notes_path,
                        "status": status
                    })
                elif file_lower.endswith(image_extensions):
                    base_name = os.path.splitext(file)[0]
                    status = "Exists" if base_name in existing_names else "New"
                    potential_assets.append({
                        "name": base_name,
                        "type": "image",
                        "path": os.path.join(root, file),
                        "status": status
                    })
        
        return potential_assets
