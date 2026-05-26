import os
import shutil
import uuid
import re
import json
import logging
import yaml
from datetime import datetime
from typing import List, Optional, Dict, Any
from tinydb import Query
import mutagen
from app.core.state_manager import StateManager
from app.models.schemas import (
    LibraryAsset, AssetDataType, AssetType, 
    AudioAsset, BeatAsset, ImageAsset, SongAsset
)

# Project paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
DEFAULT_LIBRARY_ROOT = os.path.join(project_root, "assets", "library")

logger = logging.getLogger(__name__)

class LibraryManagerEngine:
    def __init__(self, db_path: Optional[str] = None, library_root: str = DEFAULT_LIBRARY_ROOT):
        self.state_manager = StateManager(db_path)
        self.library_root = library_root
        self.assets_table = self.state_manager.db.table('library_assets')
        
        # Ensure subdirectories exist
        self.audio_dir = os.path.join(self.library_root, "audio")
        self.stems_dir = os.path.join(self.library_root, "stems")
        self.md_dir = os.path.join(self.library_root, "md")
        self.image_dir = os.path.join(self.library_root, "image")
        self.trash_dir = os.path.join(self.library_root, "trash")
        for d in [self.audio_dir, self.stems_dir, self.md_dir, self.image_dir, self.trash_dir]:
            os.makedirs(d, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        s = re.sub(r'[^a-zA-Z0-9\.\-_]', '_', name)
        s = re.sub(r'_+', '_', s)
        return s.strip('_')

    def _read_md_metadata(self, md_path: str) -> Dict[str, Any]:
        """Reads metadata from YAML frontmatter in a markdown file."""
        meta = {"tags": []}
        if not os.path.exists(md_path): return meta
        try:
            with open(md_path, "r") as f:
                content = f.read()
                
            # Match YAML frontmatter
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if match:
                yaml_content = match.group(1)
                data = yaml.safe_load(yaml_content)
                if isinstance(data, dict):
                    # Ensure all values are JSON serializable (YAML parser might return datetime objects)
                    for k, v in data.items():
                        if isinstance(v, datetime):
                            data[k] = v.isoformat()
                    meta.update(data)
                    # Normalize tags to list
                    if "tags" in meta:
                        if isinstance(meta["tags"], str):
                            meta["tags"] = [t.strip() for t in meta["tags"].split(",") if t.strip()]
                        elif not isinstance(meta["tags"], list):
                            meta["tags"] = []
            else:
                # Fallback to old simple colon parsing if no frontmatter exists
                for line in content.split("\n"):
                    if ":" in line and not line.startswith("#"):
                        key, val = line.split(":", 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key == "tags":
                            meta["tags"] = [t.strip() for t in val.split(",") if t.strip()]
                        elif key in ("id", "type"):
                            meta[key] = val
        except Exception as e:
            logger.error(f"Failed to read MD metadata from {md_path}: {e}")
        return meta

    def _write_md_metadata(self, md_path: str, updates: Dict[str, Any]) -> bool:
        """Updates or adds YAML frontmatter in the markdown file."""
        if not os.path.exists(md_path): return False
        try:
            with open(md_path, "r") as f:
                content = f.read()
            
            frontmatter = {}
            body = content
            
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
            if match:
                yaml_content = match.group(1)
                body = match.group(2)
                frontmatter = yaml.safe_load(yaml_content) or {}
            else:
                # If no frontmatter, try to strip old-style header lines to migrate
                # But only if they look like our old headers (ID:, Type:, Tags:)
                new_body_lines = []
                lines = content.split("\n")
                in_header = True
                for line in lines:
                    line_lower = line.lower()
                    if in_header and (re.match(r"^(ID|Type|Tags|Created):", line, re.I) or not line.strip() or line.startswith("# ")):
                        if line_lower.startswith("id:") or line_lower.startswith("type:") or line_lower.startswith("tags:") or line_lower.startswith("created:"):
                            # Capture existing data for migration
                            key, val = line.split(":", 1)
                            frontmatter[key.lower().strip()] = val.strip()
                            continue
                        elif line.startswith("# "):
                            # Keep title in body but out of header stripping
                            new_body_lines.append(line)
                            continue
                        # Skip empty lines at very top
                        continue
                    else:
                        in_header = False
                        new_body_lines.append(line)
                body = "\n".join(new_body_lines).lstrip()

            # Apply updates
            for k, v in updates.items():
                frontmatter[k.lower()] = v
            
            # Reconstruct file
            new_yaml = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
            new_content = f"---\n{new_yaml}\n---\n\n{body}"
            
            with open(md_path, "w") as f:
                f.write(new_content)
            return True
        except Exception as e:
            logger.error(f"Failed to write MD metadata to {md_path}: {e}")
            return False

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Helper to get a single asset by ID."""
        asset = self.assets_table.get(doc_id=asset_id)
        if not asset:
            asset = self.assets_table.get(Query().id == asset_id)
        return asset

    def get_assets(self, data_type: Optional[AssetDataType] = None, asset_type: Optional[AssetType] = None) -> List[Dict[str, Any]]:
        results = self.assets_table.all()
        if data_type:
            results = [r for r in results if r.get('data_type') == data_type.value]
        if asset_type:
            results = [r for r in results if r.get('asset_type') == asset_type.value]
        return results

    def import_raw_audio(self, name: str, audio_source: str, notes_source: Optional[str] = None, delete_source: bool = False) -> AudioAsset:
        """Import a raw audio file and its notes into the central folders."""
        asset_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(audio_source)[1]
        safe_name = self._sanitize_filename(name)
        
        dest_audio_filename = f"{safe_name}_{asset_id}{ext}"
        dest_audio_path = os.path.join(self.audio_dir, dest_audio_filename)
        
        shutil.copy2(audio_source, dest_audio_path)
        
        dest_notes_filename = f"{safe_name}_{asset_id}_notes.md"
        if notes_source and os.path.exists(notes_source):
            shutil.copy2(notes_source, os.path.join(self.md_dir, dest_notes_filename))
        else:
             with open(os.path.join(self.md_dir, dest_notes_filename), 'w') as f:
                 f.write(f"# Notes for {name}\n")

        # Extract metadata
        duration = 0
        try:
            audio = mutagen.File(dest_audio_path)
            if audio and hasattr(audio.info, 'length'):
                duration = audio.info.length
        except:
            pass

        asset = AudioAsset(
            id=asset_id,
            name=name,
            path=dest_audio_path,
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
        """Import an image file into the central image folder."""
        asset_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(source_path)[1]
        safe_name = self._sanitize_filename(name)
        
        dest_filename = f"{safe_name}_{asset_id}{ext}"
        dest_path = os.path.join(self.image_dir, dest_filename)
        
        shutil.copy2(source_path, dest_path)

        asset = ImageAsset(
            id=asset_id,
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

    def create_beat_from_audio(self, audio_asset_id: str, beat_name: Optional[str] = None) -> BeatAsset:
        """Convert a raw audio asset into a promoted BEAT represented by a markdown file."""
        audio_doc = self.assets_table.get(doc_id=audio_asset_id)
        if not audio_doc:
            audio_doc = self.assets_table.get(Query().id == audio_asset_id)
        
        if not audio_doc or audio_doc.get('asset_type') != AssetType.RAW:
            raise ValueError("Valid raw audio asset required to create a beat.")

        name = beat_name or audio_doc['name']
        asset_id = str(uuid.uuid4())[:8]
        safe_beat_name = self._sanitize_filename(name)
        
        # Unified audio path retrieval (essential since asset['path'] points to MD)
        audio_path = self.get_audio_path(audio_asset_id)
        if not audio_path:
            raise ValueError("Could not locate source audio for this asset.")
            
        audio_filename = os.path.basename(audio_path)
        
        # New notes file (renamed from raw notes)
        new_notes_filename = f"{safe_beat_name}_{asset_id}_notes.md"
        new_notes_path = os.path.join(self.md_dir, new_notes_filename)
        
        if audio_doc.get('notes_file'):
            old_notes_path = os.path.join(self.md_dir, audio_doc['notes_file'])
            if os.path.exists(old_notes_path):
                shutil.move(old_notes_path, new_notes_path)
        
        if not os.path.exists(new_notes_path):
            with open(new_notes_path, 'w') as f:
                f.write(f"# Notes for {name}\n")

        # Create the Promoted Markdown file (Master file)
        md_filename = f"{safe_beat_name}_{asset_id}.md"
        md_path = os.path.join(self.md_dir, md_filename)
        
        initial_tags = []

        with open(md_path, 'w') as f:
            f.write(f"---\nid: {asset_id}\ntype: Beat\ntags: {', '.join(initial_tags)}\ncreated: {datetime.now().isoformat()}\n---\n\n")
            f.write(f"# {name}\n\n")
            f.write("## Files\n")
            f.write(f"- Audio: [[{audio_filename}]]\n")
            f.write(f"- Notes: [[{new_notes_filename}]]\n")

        beat = BeatAsset(
            id=asset_id,
            name=name,
            path=md_path,
            versions={"main": audio_filename},
            notes_file=new_notes_filename,
            duration=audio_doc.get('duration'),
            bpm=audio_doc.get('bpm'),
            key=audio_doc.get('key'),
            metadata=audio_doc.get('metadata', {}),
            tags=initial_tags
        )

        # Remove old raw audio entry and insert new beat entry
        self.assets_table.remove(Query().id == audio_doc['id'])
        self.assets_table.insert(beat.dict())
        return beat

    def get_audio_path(self, asset_id: str) -> Optional[str]:
        """Unified method to get the primary audio path for an asset."""
        resolved = self.resolve_asset_paths(asset_id)
        versions = resolved.get("versions", [])
        if not versions: return None
        
        # Priority: Master/Version > Raw Original > Stem
        # Since sorted by type 'version' first, we look for 'Master' or 'Linked'
        for v in versions:
            if v["type"] == "version":
                # If multiple versions, prefer anything that isn't 'Original (Raw)' if possible, 
                # but usually the first one is fine.
                return v["path"]
        
        # Fallback to the very first audio found
        return versions[0]["path"]

    def resolve_asset_paths(self, asset_id: str) -> Dict[str, Any]:
        """Resolves an asset ID to its constituent file paths and audio versions."""
        audio_exts = ('.wav', '.mp3', '.flac')
        asset = self.assets_table.get(doc_id=asset_id)
        if not asset:
            asset = self.assets_table.get(Query().id == asset_id)
        if not asset:
            return {}

        res = {
            "name": asset['name'], 
            "id": asset['id'], 
            "tags": asset.get('tags', []),
            "versions": [] # List of {"name": str, "path": str, "type": str}
        }
        
        if asset.get('asset_type') in (AssetType.RAW, AssetType.BEAT, AssetType.SONG):
            # All primary audio assets now have a primary MD file
            md_path = asset['path']
            if not md_path.endswith(".md"):
                md_filename = f"{self._sanitize_filename(asset['name'])}_{asset_id}.md"
                md_path = os.path.join(self.md_dir, md_filename)

            res["markdown"] = md_path

            # 1. Discover versions from DB/Metadata
            db_versions = asset.get('versions', {})
            if isinstance(db_versions, dict):
                for v_name, v_file in db_versions.items():
                    v_path = os.path.join(self.audio_dir, v_file)
                    if os.path.exists(v_path):
                        label = "Original (Raw)" if v_name == "main" else v_name.capitalize()
                        res["versions"].append({"name": label, "path": v_path, "type": "version"})

            # 2. Discover from MD links (Obsidian style)
            if os.path.exists(md_path):
                md_meta = self._read_md_metadata(md_path)
                if md_meta.get("tags"): res["tags"] = md_meta["tags"]
                if md_meta.get("stems_id"): res["stems_id"] = md_meta["stems_id"]
                
                with open(md_path, 'r') as f:
                    content = f.read()
                    links = re.findall(r'\[\[(.*?)\]\]', content)
                    for link in links:
                        link_path = None
                        if link.lower().endswith(audio_exts):
                            link_path = os.path.join(self.audio_dir, link)
                            if link_path and os.path.exists(link_path):
                                # Avoid duplicates
                                if not any(v["path"] == link_path for v in res["versions"]):
                                    res["versions"].append({"name": "Linked Audio", "path": link_path, "type": "version"})
                        elif link.endswith('_notes.md'):
                            res["notes"] = os.path.join(self.md_dir, link)

            # 3. Deep discovery of stems in the stems directory
            # Stems are stored in a folder named ST + asset_id
            stems_folder = os.path.join(self.stems_dir, f"ST{asset_id}")
            if os.path.exists(stems_folder):
                for f in os.listdir(stems_folder):
                    if f.lower().endswith(audio_exts):
                        stem_path = os.path.join(stems_folder, f)
                        stem_label = os.path.splitext(f)[0].capitalize()
                        res["versions"].append({"name": f"{stem_label} (Stem)", "path": stem_path, "type": "stem"})
            
            # Final sort: Versions first, then Stems
            res["versions"].sort(key=lambda x: (x["type"] != "version", x["name"]))

            if "notes" not in res and asset.get('notes_file'):
                res["notes"] = os.path.join(self.md_dir, asset['notes_file'])

        elif asset.get('asset_type') == AssetType.SONG_STEMS:
            md_path = asset['path']
            res["markdown"] = md_path
            parent_id = asset['metadata'].get('parent_id', 'unknown')
            stems_folder = os.path.join(self.stems_dir, f"ST{parent_id}")
            if os.path.exists(stems_folder):
                for f in os.listdir(stems_folder):
                    if f.lower().endswith(audio_exts):
                        res["versions"].append({
                            "name": os.path.splitext(f)[0].capitalize(),
                            "path": os.path.join(stems_folder, f),
                            "type": "stem"
                        })

        elif asset.get('data_type') == AssetDataType.IMAGE:
            res["image"] = asset['path']

        return res

    def rename_asset(self, asset_id: str, new_name: str) -> bool:
        """Renames an asset and all its associated files (Audio, MD, Notes)."""
        asset = self.get_asset(asset_id)
        if not asset: return False
        
        safe_new = self._sanitize_filename(new_name)
        resolved = self.resolve_asset_paths(asset_id)
        
        # 1. Rename physical audio file if it exists
        old_audio_path = resolved.get("audio")
        new_audio_filename = None
        if old_audio_path and os.path.exists(old_audio_path):
            ext = os.path.splitext(old_audio_path)[1]
            new_audio_filename = f"{safe_new}_{asset_id}{ext}"
            new_audio_path = os.path.join(self.audio_dir, new_audio_filename)
            try:
                os.rename(old_audio_path, new_audio_path)
            except Exception as e:
                logger.error(f"Failed to rename audio: {e}")
                return False

        # 2. Rename physical notes file if it exists
        old_notes_path = resolved.get("notes")
        new_notes_filename = None
        if old_notes_path and os.path.exists(old_notes_path):
            new_notes_filename = f"{safe_new}_{asset_id}_notes.md"
            new_notes_path = os.path.join(self.md_dir, new_notes_filename)
            try:
                os.rename(old_notes_path, new_notes_path)
            except: pass

        # 3. Rename main Markdown file if it exists
        old_md_path = resolved.get("markdown")
        new_md_path = None
        if old_md_path and os.path.exists(old_md_path):
            new_md_filename = f"{safe_new}_{asset_id}.md"
            new_md_path = os.path.join(self.md_dir, new_md_filename)
            try:
                os.rename(old_md_path, new_md_path)
                
                # 4. Update links INSIDE the new MD file
                if new_audio_filename or new_notes_filename:
                    with open(new_md_path, "r") as f:
                        content = f.read()
                    
                    if new_audio_filename:
                        # Find the old audio link and replace it
                        old_audio_name = os.path.basename(old_audio_path)
                        content = content.replace(f"[[{old_audio_name}]]", f"[[{new_audio_filename}]]")
                    
                    if new_notes_filename:
                        old_notes_name = os.path.basename(old_notes_path)
                        content = content.replace(f"[[{old_notes_name}]]", f"[[{new_notes_filename}]]")
                    
                    with open(new_md_path, "w") as f:
                        f.write(content)
            except Exception as e:
                logger.error(f"Failed to rename MD: {e}")

        # 5. Update Database
        updates = {
            "name": new_name,
            "path": new_md_path or asset.get("path")
        }
        if new_audio_filename:
            updates["versions"] = {"main": new_audio_filename}
        if new_notes_filename:
            updates["notes_file"] = new_notes_filename
            
        return self.update_asset(asset_id, updates)

    def delete_asset(self, asset_id: str) -> bool:
        asset = self.assets_table.get(Query().id == asset_id)
        if not asset: return False
        
        subdir = os.path.join(self.trash_dir, f"{self._sanitize_filename(asset['name'])}_{asset_id}")
        os.makedirs(subdir, exist_ok=True)
        
        resolved = self.resolve_asset_paths(asset_id)
        for key, path in resolved.items():
            if key in ('audio', 'notes', 'markdown', 'image') and os.path.exists(path):
                try: shutil.move(path, os.path.join(subdir, os.path.basename(path)))
                except: pass
                
        self.assets_table.remove(Query().id == asset_id)
        return True

    def downgrade_beat_to_raw(self, beat_id: str) -> AudioAsset:
        beat = self.assets_table.get(Query().id == beat_id)
        if not beat or beat.get('asset_type') != AssetType.BEAT:
            raise ValueError("Not a beat")
        
        resolved = self.resolve_asset_paths(beat_id)
        audio_path = resolved.get('audio')
        
        if os.path.exists(beat['path']):
            os.remove(beat['path'])
            
        raw = AudioAsset(
            id=beat_id, name=beat['name'], path=audio_path,
            audio_file=os.path.basename(audio_path),
            notes_file=beat.get('notes_file'),
            duration=beat.get('duration'), asset_type=AssetType.RAW
        )
        self.assets_table.remove(Query().id == beat_id)
        self.assets_table.insert(raw.dict())
        return raw

    def create_song_from_audio(self, audio_asset_id: str, song_name: Optional[str] = None) -> SongAsset:
        """Convert a raw audio asset into a promoted SONG represented by a markdown file."""
        audio_doc = self.assets_table.get(doc_id=audio_asset_id)
        if not audio_doc:
            audio_doc = self.assets_table.get(Query().id == audio_asset_id)
        
        if not audio_doc or audio_doc.get('asset_type') != AssetType.RAW:
            raise ValueError("Valid raw audio asset required to create a song.")

        name = song_name or audio_doc['name']
        asset_id = str(uuid.uuid4())[:8]
        safe_song_name = self._sanitize_filename(name)
        
        # Unified audio path retrieval
        audio_path = self.get_audio_path(audio_asset_id)
        if not audio_path:
            raise ValueError("Could not locate source audio for this asset.")

        audio_filename = os.path.basename(audio_path)
        
        # New notes file
        new_notes_filename = f"{safe_song_name}_{asset_id}_notes.md"
        new_notes_path = os.path.join(self.md_dir, new_notes_filename)
        
        if audio_doc.get('notes_file'):
            old_notes_path = os.path.join(self.md_dir, audio_doc['notes_file'])
            if os.path.exists(old_notes_path):
                shutil.move(old_notes_path, new_notes_path)
        
        if not os.path.exists(new_notes_path):
            with open(new_notes_path, 'w') as f:
                f.write(f"# Notes for {name}\n")

        # Create the Promoted Markdown file
        md_filename = f"{safe_song_name}_{asset_id}.md"
        md_path = os.path.join(self.md_dir, md_filename)
        
        initial_tags = []

        with open(md_path, 'w') as f:
            f.write(f"---\nid: {asset_id}\ntype: Song\ntags: {', '.join(initial_tags)}\ncreated: {datetime.now().isoformat()}\n---\n\n")
            f.write(f"# {name}\n\n")
            f.write("## Files\n")
            f.write(f"- Audio: [[{audio_filename}]]\n")
            f.write(f"- Notes: [[{new_notes_filename}]]\n")

        song = SongAsset(
            id=asset_id,
            name=name,
            path=md_path,
            versions={"main": audio_filename},
            notes_file=new_notes_filename,
            duration=audio_doc.get('duration'),
            bpm=audio_doc.get('bpm'),
            key=audio_doc.get('key'),
            metadata=audio_doc.get('metadata', {}),
            tags=initial_tags
        )

        self.assets_table.remove(Query().id == audio_doc['id'])
        self.assets_table.insert(song.dict())
        return song

    def create_stems_asset(self, parent_asset_id: str, stems_folder: str) -> str:
        """Create a new SONG_STEMS asset and link it to the parent."""
        parent = self.get_asset(parent_asset_id)
        if not parent: return None
        
        # Consistent ID for stems: ST + parent_id
        stems_id = f"ST{parent_asset_id}"
        stems_name = f"{parent['name']} [STEMS]"
        
        # Create MD file for stems
        md_filename = f"{self._sanitize_filename(stems_name)}_{stems_id}.md"
        md_path = os.path.join(self.md_dir, md_filename)
        
        stem_files = [f for f in os.listdir(stems_folder) if f.endswith(('.wav', '.mp3'))]
        
        with open(md_path, 'w') as f:
            f.write(f"---\nid: {stems_id}\ntype: SongStems\nparent_id: {parent_asset_id}\ncreated: {datetime.now().isoformat()}\n---\n\n")
            f.write(f"# {stems_name}\n\n")
            f.write("## Stems\n")
            for sf in stem_files:
                f.write(f"- {sf.capitalize().replace('.wav', '')}: [[{sf}]]\n")

        stems_asset = {
            "id": stems_id,
            "name": stems_name,
            "path": md_path,
            "data_type": AssetDataType.AUDIO,
            "asset_type": AssetType.SONG_STEMS,
            "created_at": datetime.now().isoformat(),
            "versions": {os.path.splitext(sf)[0]: sf for sf in stem_files},
            "metadata": {"parent_id": parent_asset_id},
            "tags": parent.get('tags', [])
        }
        
        self.assets_table.insert(stems_asset)
        
        # Link to parent
        self.update_asset(parent_asset_id, {"stems_id": stems_id})
        
        # Update parent MD file
        parent_path = parent.get('path')
        if parent_path and os.path.exists(parent_path):
            self._write_md_metadata(parent_path, {"stems_id": stems_id})
            # Check if stems section already exists
            with open(parent_path, 'r') as f:
                content = f.read()
            
            if "## Stems" not in content:
                with open(parent_path, 'a') as f:
                    f.write(f"\n## Stems\n- Stems: [[{os.path.basename(md_path)}]]\n")
        
        return stems_id

    def update_asset(self, asset_id: str, updates: Dict[str, Any]) -> bool:
        """Update an asset's data in the database."""
        try:
            asset = self.get_asset(asset_id)
            if not asset: return False

            # Sync with MD file if it's a promoted asset (Beat or Song)
            if asset.get('asset_type') in (AssetType.BEAT, AssetType.SONG):
                md_path = asset.get('path')
                if md_path and os.path.exists(md_path):
                    md_updates = {}
                    if 'tags' in updates: md_updates['tags'] = updates['tags']
                    if 'stems_id' in updates: md_updates['stems_id'] = updates['stems_id']
                    
                    if md_updates:
                        self._write_md_metadata(md_path, md_updates)

            self.assets_table.update(updates, Query().id == asset_id)
            return True
        except Exception as e:
            logger.error(f"Failed to update asset {asset_id}: {e}")
            return False

    def sync_library_with_disk(self) -> int:
        """Deep scan the library, ensure MD files exist for all assets, and rebuild DB index."""
        logger.info("Starting deep library synchronization (Metadata-Master mode)...")
        
        # 1. Prepare for rebuild
        self.assets_table.truncate() # Clear all
        audio_exts = ('.wav', '.mp3', '.flac')
        
        # Map to keep track of which audio files are linked to which MD
        audio_to_md_map = {} 
        count = 0

        # 2. First pass: Move any MD files from audio/ to md/ for consolidation
        if os.path.exists(self.audio_dir):
            for f in os.listdir(self.audio_dir):
                if f.endswith(".md"):
                    try:
                        shutil.move(os.path.join(self.audio_dir, f), os.path.join(self.md_dir, f))
                    except: pass

        # 3. Second pass: Process all Markdown files in the md/ directory
        md_files = [f for f in os.listdir(self.md_dir) if f.endswith(".md") and not f.endswith("_notes.md")]
        for f in md_files:
            md_path = os.path.join(self.md_dir, f)
            meta = self._read_md_metadata(md_path)
            asset_id = str(meta.get("id") or str(uuid.uuid4())[:8])
            
            # Determine asset name
            base_name = os.path.splitext(f)[0]
            clean_name = base_name.split("_" + asset_id)[0] if asset_id in base_name else base_name
            name = meta.get("name") or clean_name
            
            # Determine type
            asset_type_str = str(meta.get("type", "Raw")).lower()
            asset_type = AssetType.RAW
            if asset_type_str == "beat": asset_type = AssetType.BEAT
            elif asset_type_str == "song": asset_type = AssetType.SONG
            elif asset_type_str == "sample": asset_type = AssetType.SAMPLE
            elif asset_type_str == "songstems": asset_type = AssetType.SONG_STEMS

            # Find linked audio
            audio_file = None
            notes_file = None
            with open(md_path, "r") as mf:
                content = mf.read()
                # Find [[audio.wav]] or [[notes.md]]
                links = re.findall(r"\[\[(.*?)\]\]", content)
                for link in links:
                    if link.lower().endswith(audio_exts):
                        audio_file = link
                    elif link.endswith("_notes.md"):
                        notes_file = link

            # Fallback audio discovery
            if not audio_file:
                for af in os.listdir(self.audio_dir):
                    if af.lower().endswith(audio_exts):
                        if asset_id in af or clean_name in af:
                            audio_file = af
                            # Repair link in MD
                            with open(md_path, "a") as mf:
                                mf.write(f"\nAudio: [[{af}]]\n")
                            break

            if audio_file:
                audio_to_md_map[audio_file] = md_path

            # Add to DB
            new_asset = {
                "id": asset_id,
                "name": name,
                "path": md_path, # ALWAYS point to MD for consistency
                "data_type": AssetDataType.AUDIO,
                "asset_type": asset_type,
                "created_at": meta.get("created", datetime.now().isoformat()),
                "versions": {"main": audio_file} if audio_file else {},
                "metadata": meta,
                "tags": meta.get("tags", []),
                "notes_file": notes_file,
                "stems_id": meta.get("stems_id")
            }
            self.assets_table.insert(new_asset)
            count += 1

        # 4. Third pass: Handle any orphaned audio files
        if os.path.exists(self.audio_dir):
            for af in os.listdir(self.audio_dir):
                if af.lower().endswith(audio_exts) and af not in audio_to_md_map:
                    # Create new Raw entry
                    asset_id = str(uuid.uuid4())[:8]
                    base_af = os.path.splitext(af)[0]
                    clean_af_name = base_af
                    
                    md_filename = f"{self._sanitize_filename(clean_af_name)}_{asset_id}.md"
                    target_md_path = os.path.join(self.md_dir, md_filename)
                    
                    with open(target_md_path, "w") as mf:
                        mf.write(f"---\nid: {asset_id}\ntype: Raw\ntags: []\ncreated: {datetime.now().isoformat()}\n---\n\n")
                        mf.write(f"# {clean_af_name}\n\n")
                        mf.write(f"Audio: [[{af}]]\n")
                    
                    new_asset = {
                        "id": asset_id,
                        "name": clean_af_name,
                        "path": target_md_path,
                        "data_type": AssetDataType.AUDIO,
                        "asset_type": AssetType.RAW,
                        "created_at": datetime.now().isoformat(),
                        "versions": {"main": af},
                        "metadata": {"type": "Raw", "id": asset_id},
                        "tags": [],
                        "notes_file": None
                    }
                    self.assets_table.insert(new_asset)
                    count += 1
                    
        return count

    def scan_for_import(self, search_path: str) -> List[Dict[str, Any]]:
        potential = []
        audio_exts = ('.wav', '.mp3', '.flac')
        for root, _, files in os.walk(search_path):
            for f in files:
                if f.lower().endswith(audio_exts):
                    potential.append({"name": os.path.splitext(f)[0], "type": "audio", "path": os.path.join(root, f)})
        return potential
