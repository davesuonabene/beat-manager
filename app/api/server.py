import os
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import uvicorn
import uuid

from app.api.library_router import LibraryRouter
from app.core.video_engine import VideoEngine
from app.core.youtube_engine import YouTubeEngine
from app.models.schemas import RenderConfig, UploadConfig, PrivacyEnum

class RenderRequest(BaseModel):
    audio_path: str
    image_path: str
    title: str = "Untitled Beat"

class RenderResponse(BaseModel):
    video_path: str
    status: str

class UploadRequest(BaseModel):
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = []

class UploadResponse(BaseModel):
    youtube_id: str
    status: str

class PublishingRouter:
    """
    Object-oriented API router for BeatManager.
    Connects HTTP requests to the underlying dispatcher/engines.
    """
    def __init__(self):
        self.router = APIRouter(prefix="/publish", tags=["Publishing"])
        self.video_engine = VideoEngine()
        # We need the client_secrets.json path. Assuming it's in the project root.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        self.client_secrets_path = os.path.join(project_root, "client_secrets.json")
        self.youtube_engine = YouTubeEngine(self.client_secrets_path)
        self._setup_routes()

    def _setup_routes(self):
        @self.router.post("/render", response_model=RenderResponse)
        async def render_video(request: RenderRequest) -> RenderResponse:
            try:
                # Generate a temporary path for the rendered video in the library's root or system tmp
                safe_title = request.title.replace(" ", "_").replace("/", "_")
                output_path = f"/tmp/rendered_{safe_title}_{uuid.uuid4().hex[:6]}.mp4"
                
                config = RenderConfig(
                    audio_path=request.audio_path,
                    image_path=request.image_path,
                    output_path=output_path,
                    project_tag=request.title
                )
                
                result = self.video_engine.create_video(config)
                if not result.success:
                    raise Exception(result.error_message)
                
                return RenderResponse(video_path=result.output_path or output_path, status="success")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Render Engine Error: {str(e)}")

        @self.router.post("/upload", response_model=UploadResponse)
        async def upload_video(request: UploadRequest) -> UploadResponse:
            try:
                config = UploadConfig(
                    video_path=request.video_path,
                    title=request.title,
                    description=request.description,
                    privacy=PrivacyEnum.PRIVATE  # Default to private for safety
                )
                
                # The channel ID is used to scope the OAuth token
                result = self.youtube_engine.upload_video(channel_id="default_channel", config=config)
                
                if not result.success:
                    raise Exception(result.error_message)
                
                # Assume output_path contains the YouTube ID upon success from the engine.
                youtube_id = result.output_path or "unknown_id"
                
                return UploadResponse(youtube_id=youtube_id, status="success")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Upload Engine Error: {str(e)}")

def create_app() -> FastAPI:
    app = FastAPI(title="BeatManager API", version="1.0.0")
    publishing_router = PublishingRouter()
    library_router = LibraryRouter()
    app.include_router(publishing_router.router)
    app.include_router(library_router.router)
    return app

app = create_app()

if __name__ == "__main__":
    # URLs and ports should be configured via environment variables
    host = os.getenv("BEAT_MANAGER_HOST", "0.0.0.0")
    port = int(os.getenv("BEAT_MANAGER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
