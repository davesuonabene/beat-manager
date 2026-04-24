import os
import httpx
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models.schemas import BeatAsset, ImageAsset, LinkImageRequest, BeatPreparationResult, AssetDataType, AssetType

# Attempt to import real engine.
try:
    from app.core.library_engine import LibraryManagerEngine
    HAS_LIBRARY_ENGINE = True
except ImportError:
    HAS_LIBRARY_ENGINE = False

class LibraryRouter:
    """
    Object-oriented API router for BeatManager Library.
    """
    def __init__(self):
        self.router = APIRouter(prefix="/library", tags=["Library"])
        # Mock engine instance if real one is not available
        self.engine = LibraryManagerEngine() if HAS_LIBRARY_ENGINE else MockLibraryEngine()
        self._setup_routes()

    def _setup_routes(self):
        @self.router.get("/beats", response_model=List[BeatAsset])
        async def get_beats(unassigned_only: bool = Query(True)):
            try:
                beats = self.engine.get_beats(unassigned_only=unassigned_only)
                return beats
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/images", response_model=List[ImageAsset])
        async def get_images():
            try:
                images = self.engine.get_images()
                return images
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/beats/{beat_id}/link")
        async def link_cover_to_beat(beat_id: str, request: LinkImageRequest):
            try:
                success = self.engine.set_beat_cover(beat_id, request.image_id)
                if not success:
                    raise HTTPException(status_code=404, detail="Beat or Image not found")
                return {"status": "success"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/beats/{beat_id}/payload", response_model=BeatPreparationResult)
        async def get_beat_payload(beat_id: str) -> BeatPreparationResult:
            try:
                payload = self.engine.get_beat_payload(beat_id)
                if not payload:
                    raise HTTPException(status_code=404, detail="Beat not found or incomplete")
                return payload
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

class MockLibraryEngine:
    """Fallback mock engine for baseline."""
    def get_beats(self, unassigned_only: bool) -> List[BeatAsset]:
        return [
            BeatAsset(
                id="beat_1", 
                data_type=AssetDataType.AUDIO,
                asset_type=AssetType.BEAT,
                path="/mock/audio/beat1.wav", 
                name="beat1.wav", 
                metadata={"suggested_title": "Dark Trap Beat"}
            )
        ]
    def get_images(self) -> List[ImageAsset]:
        return [
            ImageAsset(
                id="img_1", 
                data_type=AssetDataType.IMAGE,
                asset_type=AssetType.COVER,
                path="/mock/img/cover1.jpg", 
                name="cover1.jpg", 
                metadata={"tags": ["dark", "trap"]}
            )
        ]
    def set_beat_cover(self, beat_id: str, image_id: str) -> bool:
        return True
    def get_beat_payload(self, beat_id: str) -> BeatPreparationResult:
        return BeatPreparationResult(
            beat_id=beat_id,
            audio_path=f"/mock/audio/{beat_id}.wav",
            image_path="/mock/img/linked_cover.jpg",
            suggested_title="Dark Trap Beat",
            is_ready_for_dispatch=True
        )
