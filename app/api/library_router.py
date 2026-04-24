import os
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from tinydb import Query as TinyQuery
from app.models.schemas import BeatAsset, ImageAsset, LinkImageRequest, BeatPreparationResult, AssetDataType, AssetType
from app.core.library_manager_engine import LibraryManagerEngine
from app.core.state_manager import StateManager, STATE_JSON

class LibraryRouter:
    """
    Object-oriented API router for BeatManager Library.
    """
    def __init__(self):
        self.router = APIRouter(prefix="/library", tags=["Library"])
        self.engine = LibraryManagerEngine()
        self.state_manager = StateManager(STATE_JSON)
        self._setup_routes()

    def _setup_routes(self):
        @self.router.get("/beats")
        async def get_beats(unassigned_only: bool = Query(True)):
            try:
                # Get all beats
                assets = self.engine.get_assets(AssetDataType.AUDIO, AssetType.BEAT)
                
                if unassigned_only:
                    # Filter out beats that already have a cover linked
                    assets = [a for a in assets if not a.get("cover_image_id") and not a.get("linked_assets", {}).get("cover")]
                
                # Convert dicts from TinyDB into the expected schemas (or dict representations)
                return assets
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/images")
        async def get_images():
            try:
                assets = self.engine.get_assets(AssetDataType.IMAGE, AssetType.COVER)
                return assets
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/beats/{beat_id}/link")
        async def link_cover_to_beat(beat_id: str, request: LinkImageRequest):
            try:
                # Update the beat with the image ID
                self.engine.set_beat_cover(beat_id, request.image_id)
                return {"status": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/beats/{beat_id}/payload", response_model=BeatPreparationResult)
        async def get_beat_payload(beat_id: str) -> BeatPreparationResult:
            try:
                q = TinyQuery()
                beat_data = self.engine.assets_table.get(q.id == beat_id)
                if not beat_data:
                    raise HTTPException(status_code=404, detail="Beat not found")
                
                # Get the image ID
                image_id = beat_data.get("cover_image_id") or beat_data.get("linked_assets", {}).get("cover")
                if not image_id:
                    raise HTTPException(status_code=400, detail="Beat does not have a cover linked")

                image_data = self.engine.assets_table.get(q.id == image_id)
                if not image_data:
                    raise HTTPException(status_code=404, detail="Linked cover image not found in database")
                
                # Resolve Absolute Paths
                # The engine stores absolute paths in the 'path' field for raw assets, 
                # or within the beat's directory structure for beats.
                # The schema says 'path' is absolute path to the asset folder or file
                beat_root = beat_data.get("path")
                # Need to find the actual audio file. BeatAsset schema says versions['main'] might be used
                versions = beat_data.get("versions", {})
                main_audio = versions.get("main") or versions.get("master") or beat_data.get("name")
                
                if not beat_root or not main_audio:
                    raise HTTPException(status_code=400, detail="Beat path or main audio file is missing")
                
                audio_path = os.path.join(beat_root, main_audio) if os.path.isdir(beat_root) else beat_root
                if not os.path.exists(audio_path):
                     # fallback
                     audio_path = beat_root
                
                image_path = image_data.get("path")

                # Get title defaults
                defaults = self.state_manager.get_yt_defaults()
                
                # Apply metadata formatting
                metadata = {
                    "name": beat_data.get("name", "Untitled Beat"),
                    "bpm": str(beat_data.get("bpm", "")),
                    "key": str(beat_data.get("key", "")),
                    "genre": str(beat_data.get("metadata", {}).get("genre", "")),
                    "mood": str(beat_data.get("metadata", {}).get("mood", ""))
                }

                class SafeDict(dict):
                    def __missing__(self, key):
                        return '{' + key + '}'
                
                suggested_title = defaults.get("title_template", "{name} | {genre} Type Beat").format_map(SafeDict(metadata))

                return BeatPreparationResult(
                    beat_id=beat_id,
                    audio_path=audio_path,
                    image_path=image_path,
                    suggested_title=suggested_title,
                    is_ready_for_dispatch=True
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
