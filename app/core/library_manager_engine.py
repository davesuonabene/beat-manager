import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from tinydb import Query
import mutagen
from app.core.state_manager import StateManager
from app.models.schemas import (
    LibraryAsset, AssetDataType, AssetType, 
    AudioAsset, BeatAsset, ImageAsset, SampleAsset
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
        self.samples_dir = os.path.join(self.library_root, "samples")
        self.image_dir = os.path.join(self.library_root, "images")
        self.trash_dir = os.path.join(self.library_root, "trash")
        for d in [self.audio_dir, self.beats_dir, self.samples_dir, self.image_dir, self.trash_dir]:
            os.makedirs(d, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        import re
        # Replace non-alphanumeric (except . - _) with _
        s = re.sub(r'[^a-zA-Z0-9\.\-_]', '_', name)
        # Replace multiple underscores with one
        s = re.sub(r'_+', '_', s)
        # Remove leading/trailing underscores
        return s.strip('_')

    def _get_collection_name(self, collection_id: Optional[str]) -> str:
        if not collection_id:
            return "Unassigned"
        col = self.state_manager.collections_table.get(Query().id == collection_id)
        if col:
            return self._sanitize_filename(col.get('name', 'Unassigned'))
        return "Unassigned"

    def create_collection_folder(self, collection_name: str, asset_type: str) -> str:
        """Ensures the physical directory for a collection exists and returns its path."""
        safe_name = self._sanitize_filename(collection_name)
        base_dir = self.beats_dir if asset_type == 'beat' else self.samples_dir
        col_path = os.path.join(base_dir, safe_name)
        os.makedirs(col_path, exist_ok=True)
        return col_path

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

    def create_beat_from_audio(self, audio_asset_id: str, beat_name: Optional[str] = None, collection_id: Optional[str] = None) -> BeatAsset:
        """Convert a raw audio asset into a structured BEAT asset folder."""
        audio_doc = self.assets_table.get(doc_id=int(audio_asset_id) if isinstance(audio_asset_id, int) or audio_asset_id.isdigit() else 0)
        # Fallback search if doc_id fails
        if not audio_doc:
            audio_doc = self.assets_table.get(Query().id == audio_asset_id)
        
        if not audio_doc or audio_doc.get('asset_type') != AssetType.RAW:
            raise ValueError("Valid raw audio asset required to create a beat.")

        name = beat_name or audio_doc['name']
        asset_id = str(uuid.uuid4())[:8]
        
        # We always put new beats in the Unassigned directory unless it's part of a specific collection
        col_name = self._get_collection_name(collection_id)
        if not collection_id:
            col_name = "Unassigned"
            
        safe_beat_name = self._sanitize_filename(name)
        # Folder name: BeatName_ID
        folder_name = f"{safe_beat_name}_{asset_id}"
        beat_path = os.path.join(self.beats_dir, col_name, folder_name)
        
        # No need for extensive collision handling if ID is unique, but safety first
        if os.path.exists(beat_path):
            count = 1
            while os.path.exists(f"{beat_path}_{count}"):
                count += 1
            beat_path = f"{beat_path}_{count}"
            folder_name = os.path.basename(beat_path)

        os.makedirs(beat_path, exist_ok=True)

        # Create nested structure
        raw_dir = "RAW"
        release_dir = "RELEASE"
        os.makedirs(os.path.join(beat_path, raw_dir), exist_ok=True)
        os.makedirs(os.path.join(beat_path, release_dir), exist_ok=True)

        # Move audio files into RAW subdirectory
        old_audio_path = audio_doc['path']
        audio_ext = os.path.splitext(old_audio_path)[1]
        # New convention: BeatName_raw.ext
        new_audio_filename = f"{safe_beat_name}_raw{audio_ext}"
        new_audio_path = os.path.join(beat_path, raw_dir, new_audio_filename)
        shutil.move(old_audio_path, new_audio_path)

        # Move notes into the beat ROOT directory
        new_notes_filename = "notes.txt"
        if audio_doc.get('notes_file'):
            old_notes_path = os.path.join(os.path.dirname(old_audio_path), audio_doc['notes_file'])
            if os.path.exists(old_notes_path):
                shutil.move(old_notes_path, os.path.join(beat_path, new_notes_filename))
        
        if not os.path.exists(os.path.join(beat_path, new_notes_filename)):
            open(os.path.join(beat_path, new_notes_filename), 'w').close()

        # Create an empty metadata.json alongside the notes file
        metadata_path = os.path.join(beat_path, "metadata.json")
        if not os.path.exists(metadata_path):
            import json
            with open(metadata_path, 'w') as f:
                json.dump({}, f)

        beat = BeatAsset(
            id=asset_id,
            name=name,
            path=beat_path,
            # Versions now includes relative path to file from beat root
            versions={"main": os.path.join(raw_dir, new_audio_filename)},
            notes_file=new_notes_filename,
            duration=audio_doc.get('duration'),
            bpm=audio_doc.get('bpm'),
            key=audio_doc.get('key'),
            raw_dir=raw_dir,
            release_dir=release_dir,
            metadata=audio_doc.get('metadata', {}),
            collection_id=collection_id,
            compilation="Unassigned" if not collection_id else col_name
        )

        # Remove old raw audio entry and insert new beat entry
        if hasattr(audio_doc, 'doc_id'):
            self.assets_table.remove(doc_ids=[audio_doc.doc_id])
        else:
            self.assets_table.remove(Query().id == audio_doc['id'])
        self.assets_table.insert(beat.dict())
        return beat

    def create_sample_from_audio(self, audio_asset_id: str, sample_name: Optional[str] = None, collection_id: Optional[str] = None) -> SampleAsset:
        """Convert a raw audio asset into a structured SAMPLE asset folder."""
        audio_doc = self.assets_table.get(doc_id=int(audio_asset_id) if isinstance(audio_asset_id, int) or audio_asset_id.isdigit() else 0)
        if not audio_doc:
            audio_doc = self.assets_table.get(Query().id == audio_asset_id)

        if not audio_doc or audio_doc.get('asset_type') != AssetType.RAW:
            raise ValueError("Valid raw audio asset required to create a sample.")

        name = sample_name or audio_doc['name']
        asset_id = str(uuid.uuid4())[:8]

        col_name = self._get_collection_name(collection_id)
        col_dir = os.path.join(self.samples_dir, col_name)
        os.makedirs(col_dir, exist_ok=True)

        # Move audio file into collection folder
        old_audio_path = audio_doc['path']
        audio_ext = os.path.splitext(old_audio_path)[1]
        safe_sample_name = self._sanitize_filename(name)
        new_audio_filename = f"sample-{safe_sample_name}-{asset_id}{audio_ext}"
        new_audio_path = os.path.join(col_dir, new_audio_filename)
        shutil.move(old_audio_path, new_audio_path)

        sample = SampleAsset(
            id=asset_id,
            name=name,
            path=new_audio_path,
            duration=audio_doc.get('duration'),
            bpm=audio_doc.get('bpm'),
            key=audio_doc.get('key'),
            collection_id=collection_id
        )

        # Remove old raw audio entry and insert new sample entry
        if hasattr(audio_doc, 'doc_id'):
            self.assets_table.remove(doc_ids=[audio_doc.doc_id])
        else:
            self.assets_table.remove(Query().id == audio_doc['id'])
        self.assets_table.insert(sample.dict())
        return sample

    def import_sample(self, name: str, source_path: str, collection_id: Optional[str] = None, delete_source: bool = False, **kwargs) -> SampleAsset:
        """Import a sample into the collection-based sample folder."""
        from app.models.schemas import SampleAsset
        col_name = self._get_collection_name(collection_id)
        col_dir = os.path.join(self.samples_dir, col_name)
        os.makedirs(col_dir, exist_ok=True)
        
        asset_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(source_path)[1]
        safe_name = self._sanitize_filename(name)
        dest_filename = f"{safe_name}-{asset_id}{ext}"
        dest_path = os.path.join(col_dir, dest_filename)
        
        shutil.copy2(source_path, dest_path)
        
        # Metadata extraction
        duration = 0
        try:
            audio = mutagen.File(dest_path)
            if audio and hasattr(audio.info, 'length'):
                duration = audio.info.length
        except:
            pass
            
        sample = SampleAsset(
            id=asset_id,
            name=name,
            path=dest_path,
            collection_id=collection_id,
            duration=duration,
            **kwargs
        )
        
        self.assets_table.insert(sample.dict())
        
        if delete_source:
            try: os.remove(source_path)
            except: pass
            
        return sample

    def assign_to_collection(self, asset_id: str, collection_id: Optional[str], asset_type: str) -> bool:
        """Safely moves an asset to a new collection folder and updates the state."""
        asset = self.assets_table.get(Query().id == asset_id)
        if not asset:
            return False
            
        old_path = asset['path']
        if not os.path.exists(old_path):
            return False
            
        new_col_name = self._get_collection_name(collection_id)
        base_dir = self.beats_dir if asset_type == 'beat' else self.samples_dir
        
        # Determine new path
        new_parent_dir = os.path.join(base_dir, new_col_name)
        os.makedirs(new_parent_dir, exist_ok=True)
        new_path = os.path.join(new_parent_dir, os.path.basename(old_path))
            
        if old_path == new_path:
            # Update state anyway in case collection_id changed but resulted in same path (e.g. both None)
            self.assets_table.update({"collection_id": collection_id}, Query().id == asset_id)
            return True
            
        # Move physical file/folder
        shutil.move(old_path, new_path)
        
        # Update state
        self.assets_table.update({
            "path": new_path,
            "collection_id": collection_id
        }, Query().id == asset_id)
        
        return True

    def downgrade_beat_to_raw(self, beat_id: str) -> AudioAsset:
        """Convert a structured BEAT asset back into a raw audio asset."""
        beat_doc = self.assets_table.get(Query().id == beat_id)
        if not beat_doc or beat_doc.get('asset_type') != AssetType.BEAT:
            raise ValueError(f"Asset {beat_id} is not a valid BEAT.")

        beat_path = beat_doc['path']
        if not os.path.exists(beat_path):
            raise FileNotFoundError(f"Beat folder not found: {beat_path}")

        # 1. Handle RELEASE folder and Trash (Always create a trash entry)
        release_dir_name = beat_doc.get('release_dir', 'RELEASE')
        release_path = os.path.join(beat_path, release_dir_name)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitize_filename(beat_doc['name'])
        unique_trash_name = f"{safe_name}_{timestamp}"
        dest_trash_path = os.path.join(self.trash_dir, unique_trash_name)
        os.makedirs(dest_trash_path, exist_ok=True)
        trash_info = dest_trash_path

        if os.path.exists(release_path):
            # Move entire RELEASE folder into the unique trash folder
            shutil.move(release_path, os.path.join(dest_trash_path, release_dir_name))

        # 2. Identify main audio file
        versions = beat_doc.get('versions', {})
        main_filename = versions.get('main')
        
        # Fallback if 'main' is missing or just generic detection
        if not main_filename or not os.path.exists(os.path.join(beat_path, main_filename)):
            audio_exts = ('.wav', '.mp3', '.flac', '.aiff')
            # Check root and RAW subdirectory
            raw_dir = beat_doc.get('raw_dir', 'RAW')
            search_paths = [beat_path, os.path.join(beat_path, raw_dir)]
            
            found_file = None
            for p in search_paths:
                if os.path.exists(p):
                    files = [f for f in os.listdir(p) if f.lower().endswith(audio_exts)]
                    if files:
                        found_file = os.path.join(p, files[0])
                        break
            
            if not found_file:
                raise FileNotFoundError("No audio file found in beat folder or RAW subdirectory.")
            main_audio_path = found_file
            main_filename = os.path.basename(found_file)
        else:
            main_audio_path = os.path.join(beat_path, main_filename)

        # 3. Identify notes if they exist
        notes_filename = beat_doc.get('notes_file', 'notes.txt')
        notes_path = os.path.join(beat_path, notes_filename)
        has_notes = os.path.exists(notes_path)

        # 4. Prepare destinations in central audio_dir
        safe_name = self._sanitize_filename(beat_doc['name'])
        ext = os.path.splitext(main_filename)[1]
        
        dest_audio_filename = f"{safe_name}{ext}"
        dest_audio_path = os.path.join(self.audio_dir, dest_audio_filename)
        
        # Handle collision in audio_dir
        if os.path.exists(dest_audio_path):
            count = 1
            while os.path.exists(os.path.join(self.audio_dir, f"{safe_name}_{count}{ext}")):
                count += 1
            safe_name = f"{safe_name}_{count}"
            dest_audio_filename = f"{safe_name}{ext}"
            dest_audio_path = os.path.join(self.audio_dir, dest_audio_filename)

        # 5. Move audio and renamed notes
        shutil.move(main_audio_path, dest_audio_path)
        
        dest_notes_filename = f"{safe_name}.txt"
        if has_notes:
            shutil.move(notes_path, os.path.join(self.audio_dir, dest_notes_filename))
        else:
             # Ensure a notes file exists
             open(os.path.join(self.audio_dir, dest_notes_filename), 'w').close()

        # 6. Cleanup remaining beat folder structure
        try:
            shutil.rmtree(beat_path)
        except Exception:
            pass

        # 7. Update DB (remove beat, insert raw audio)
        metadata = beat_doc.get('metadata', {})
        
        raw_asset = AudioAsset(
            name=beat_doc['name'],
            path=dest_audio_path,
            audio_file=dest_audio_filename,
            notes_file=dest_notes_filename,
            duration=beat_doc.get('duration', 0),
            bpm=beat_doc.get('bpm'),
            key=beat_doc.get('key'),
            asset_type=AssetType.RAW,
            metadata=metadata
        )

        self.assets_table.remove(Query().id == beat_id)
        self.assets_table.insert(raw_asset.dict())
        
        # Store a link to the ID of the raw audio file to allow for restore
        if trash_info:
            import json
            try:
                meta_path = os.path.join(trash_info, "metadata.json")
                with open(meta_path, "w") as f:
                    json.dump({"raw_audio_id": raw_asset.id, "beat_name": beat_doc['name']}, f)
            except Exception:
                pass
        
        return raw_asset

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
            
        elif asset_type == AssetType.BEAT or asset_type == 'beat':
            # Rename beat folder and raw file
            old_path = asset_doc.get('path')
            if not old_path or not os.path.exists(old_path):
                 self.assets_table.update({"name": new_name}, Query().id == asset_id)
                 return True
            
            parent_dir = os.path.dirname(old_path)
            new_beat_path = os.path.join(parent_dir, f"{safe_new_name}_{asset_id}")
            
            # Handle directory collision (though unlikely with ID)
            if os.path.exists(new_beat_path) and new_beat_path != old_path:
                 count = 1
                 while os.path.exists(f"{new_beat_path}_{count}"):
                      count += 1
                 new_beat_path = f"{new_beat_path}_{count}"

            if old_path != new_beat_path:
                os.rename(old_path, new_beat_path)
            
            # Rename raw audio file inside RAW/
            versions = asset_doc.get('versions', {})
            main_rel_path = versions.get('main')
            if main_rel_path:
                old_raw_path = os.path.join(new_beat_path, main_rel_path)
                if os.path.exists(old_raw_path):
                    raw_dir = asset_doc.get('raw_dir', 'RAW')
                    ext = os.path.splitext(main_rel_path)[1]
                    new_raw_filename = f"{safe_new_name}_raw{ext}"
                    new_raw_path = os.path.join(new_beat_path, raw_dir, new_raw_filename)
                    if old_raw_path != new_raw_path:
                        os.rename(old_raw_path, new_raw_path)
                    versions['main'] = os.path.join(raw_dir, new_raw_filename)

            self.assets_table.update({
                "name": new_name,
                "path": new_beat_path,
                "versions": versions
            }, Query().id == asset_id)
            
        else:
            self.assets_table.update({"name": new_name}, Query().id == asset_id)
        
        return True

    def update_asset(self, asset_id: str, updates: Dict[str, Any]) -> bool:
        """Update arbitrary metadata fields (like bpm, key) for an asset."""
        asset = self.assets_table.get(Query().id == asset_id)
        if not asset: return False

        # Prevent modifying core fields via this method
        safe_updates = {k: v for k, v in updates.items() if k not in ('id', 'asset_type', 'data_type', 'created_at')}

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
                    elif asset_type == AssetType.BEAT or asset_type == 'beat':
                        # Move to trash instead of just deleting
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_name = self._sanitize_filename(asset.get('name', 'deleted_beat'))
                        unique_trash_name = f"{safe_name}_{timestamp}_deleted"
                        dest_trash_path = os.path.join(self.trash_dir, unique_trash_name)
                        os.makedirs(dest_trash_path, exist_ok=True)
                        
                        release_dir_name = asset.get('release_dir', 'RELEASE')
                        release_path = os.path.join(path, release_dir_name)
                        if os.path.exists(release_path):
                            shutil.move(release_path, os.path.join(dest_trash_path, release_dir_name))
                            
                        import json
                        try:
                            meta_path = os.path.join(dest_trash_path, "metadata.json")
                            with open(meta_path, "w") as f:
                                json.dump({"beat_name": asset.get('name'), "deleted": True}, f)
                        except Exception:
                            pass
                            
                        shutil.rmtree(path)
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

    def empty_trash(self) -> int:
        """Permanently deletes everything in the trash directory and cleans up DB metadata."""
        deleted_count = 0
        if not os.path.exists(self.trash_dir):
            return 0
            
        for item in os.listdir(self.trash_dir):
            item_path = os.path.join(self.trash_dir, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                deleted_count += 1
            except Exception:
                pass
        
        # Cleanup metadata references in DB
        assets = self.assets_table.all()
        for asset in assets:
            metadata = asset.get('metadata', {})
            if 'archived_release_path' in metadata:
                # Check if it was in our trash_dir
                path_str = str(metadata['archived_release_path'])
                if path_str.startswith(self.trash_dir) or not os.path.exists(path_str):
                    del metadata['archived_release_path']
                    self.assets_table.update({'metadata': metadata}, doc_ids=[asset.doc_id])
                    
        return deleted_count

    def restore_from_trash(self, trash_id_or_path: str, target_beat_id: str) -> bool:
        """Moves files from a trash folder back into a beat's RELEASE folder."""
        # 1. Resolve trash path
        trash_path = trash_id_or_path
        if not os.path.isabs(trash_path):
            trash_path = os.path.join(self.trash_dir, trash_id_or_path)
            
        if not os.path.exists(trash_path):
            raise FileNotFoundError(f"Trash source not found: {trash_path}")
            
        # 2. Get target beat
        beat = self.assets_table.get(Query().id == target_beat_id)
        if not beat or beat.get('asset_type') != AssetType.BEAT:
            raise ValueError(f"Target {target_beat_id} is not a valid BEAT.")
            
        beat_path = beat['path']
        release_dir_name = beat.get('release_dir', 'RELEASE')
        target_release_path = os.path.join(beat_path, release_dir_name)
        os.makedirs(target_release_path, exist_ok=True)
        
        # 3. Move files
        # If the trash folder contains a 'RELEASE' subfolder, move its contents.
        # Otherwise move everything from the trash folder.
        source_dir = trash_path
        potential_release = os.path.join(trash_path, release_dir_name)
        if os.path.exists(potential_release) and os.path.isdir(potential_release):
            source_dir = potential_release
            
        moved_any = False
        for item in os.listdir(source_dir):
            s = os.path.join(source_dir, item)
            d = os.path.join(target_release_path, item)
            if os.path.exists(d):
                if os.path.isdir(d): shutil.rmtree(d)
                else: os.remove(d)
            shutil.move(s, d)
            moved_any = True
            
        # 4. Cleanup trash folder
        try:
            if source_dir != trash_path and not os.listdir(source_dir):
                shutil.rmtree(source_dir)
            
            # Remove metadata.json if it exists so we can clean the folder
            meta_path = os.path.join(trash_path, "metadata.json")
            if os.path.exists(meta_path):
                os.remove(meta_path)
                
            if not os.listdir(trash_path):
                shutil.rmtree(trash_path)
        except Exception:
            pass
            
        # 5. Update metadata if it pointed to this trash path
        metadata = beat.get('metadata', {})
        if metadata.get('archived_release_path') == trash_path:
            del metadata['archived_release_path']
            self.assets_table.update({'metadata': metadata}, Query().id == target_beat_id)
            
        return moved_any

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

    def export_beat(self, beat_id: str, destination_dir: str) -> bool:
        """Copies a beat folder and its contents to a target directory outside the library."""
        asset = self.assets_table.get(Query().id == beat_id)
        if not asset or asset.get('asset_type') != AssetType.BEAT:
            return False
            
        source_path = asset.get('path')
        if not source_path or not os.path.exists(source_path):
            return False
            
        os.makedirs(destination_dir, exist_ok=True)
        # Using beat name as folder name in destination
        safe_name = self._sanitize_filename(asset.get('name', 'exported_beat'))
        dest_path = os.path.join(destination_dir, safe_name)
        
        # Handle filename collisions in destination
        if os.path.exists(dest_path):
            count = 1
            while os.path.exists(f"{dest_path}_{count}"):
                count += 1
            dest_path = f"{dest_path}_{count}"
            
        shutil.copytree(source_path, dest_path)
        return True

    def move_beat(self, beat_id: str, destination_dir: str) -> bool:
        """Moves a beat folder to a target directory and updates the library path."""
        asset = self.assets_table.get(Query().id == beat_id)
        if not asset or asset.get('asset_type') != AssetType.BEAT:
            return False
            
        source_path = asset.get('path')
        if not source_path or not os.path.exists(source_path):
            return False
            
        os.makedirs(destination_dir, exist_ok=True)
        safe_name = self._sanitize_filename(asset.get('name', 'moved_beat'))
        dest_path = os.path.join(destination_dir, safe_name)
        
        # Handle filename collisions in destination
        if os.path.exists(dest_path):
            count = 1
            while os.path.exists(f"{dest_path}_{count}"):
                count += 1
            dest_path = f"{dest_path}_{count}"
            
        shutil.move(source_path, dest_path)
        self.assets_table.update({"path": dest_path}, Query().id == beat_id)
        return True

    def generate_mp3_for_beat(self, beat_id: str) -> bool:
        """Converts the main release WAV to MP3 and updates DB."""
        from app.core.processing_engine import ProcessingEngine
        beat = self.assets_table.get(Query().id == beat_id)
        if not beat or beat.get('asset_type') != AssetType.BEAT:
            return False
            
        beat_path = beat['path']
        release_dir_name = beat.get('release_dir', 'RELEASE')
        release_path = os.path.join(beat_path, release_dir_name)
        os.makedirs(release_path, exist_ok=True)
        
        main_filename = beat.get('versions', {}).get('main')
        if not main_filename:
            return False
            
        source_path = os.path.join(beat_path, main_filename)
        if not os.path.exists(source_path):
            return False
            
        source_basename = os.path.basename(main_filename)
        mp3_filename = os.path.splitext(source_basename)[0] + ".mp3"
        target_path = os.path.join(release_path, mp3_filename)
        
        success = ProcessingEngine.convert_wav_to_mp3(source_path, target_path)
        if success:
            self.assets_table.update({"has_mp3": True}, Query().id == beat_id)
        return success

    def add_master_version(self, beat_id: str, master_file_path: str) -> bool:
        """Copies a master version to the RELEASE folder and updates DB."""
        if not os.path.exists(master_file_path):
            return False
            
        beat = self.assets_table.get(Query().id == beat_id)
        if not beat or beat.get('asset_type') != AssetType.BEAT:
            return False
            
        beat_path = beat['path']
        release_dir_name = beat.get('release_dir', 'RELEASE')
        release_path = os.path.join(beat_path, release_dir_name)
        os.makedirs(release_path, exist_ok=True)
        
        target_filename = "master_" + os.path.basename(master_file_path)
        target_path = os.path.join(release_path, target_filename)
        
        shutil.copy2(master_file_path, target_path)
        
        self.assets_table.update({"has_master": True}, Query().id == beat_id)
        return True
