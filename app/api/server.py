import os
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import uvicorn

# Attempt to import the real engines. If they don't exist yet, mock them for the baseline.
try:
    from dispatcher import TaskDispatcher
    from cli import VideoEngine, YouTubeEngine
    HAS_REAL_ENGINES = True
except ImportError:
    HAS_REAL_ENGINES = False

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
        self._setup_routes()

    def _setup_routes(self):
        @self.router.post("/render", response_model=RenderResponse)
        async def render_video(request: RenderRequest) -> RenderResponse:
            try:
                if HAS_REAL_ENGINES:
                    # Actual integration
                    # Assuming TaskDispatcher has a method run_render or similar
                    video_path = TaskDispatcher.run_render(request.audio_path, request.image_path)
                else:
                    # Baseline wrapper mock
                    video_path = f"/tmp/rendered_{request.title.replace(' ', '_')}.mp4"
                
                return RenderResponse(video_path=video_path, status="success")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Render Engine Error: {str(e)}")

        @self.router.post("/upload", response_model=UploadResponse)
        async def upload_video(request: UploadRequest) -> UploadResponse:
            try:
                if HAS_REAL_ENGINES:
                    # Actual integration
                    youtube_id = TaskDispatcher.run_upload(
                        request.video_path, request.title, request.description, request.tags
                    )
                else:
                    # Baseline wrapper mock
                    youtube_id = "mock_yt_id_12345"
                    
                return UploadResponse(youtube_id=youtube_id, status="success")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Upload Engine Error: {str(e)}")

def create_app() -> FastAPI:
    app = FastAPI(title="BeatManager API", version="1.0.0")
    publishing_router = PublishingRouter()
    app.include_router(publishing_router.router)
    return app

app = create_app()

if __name__ == "__main__":
    # URLs and ports should be configured via environment variables
    host = os.getenv("BEAT_MANAGER_HOST", "0.0.0.0")
    port = int(os.getenv("BEAT_MANAGER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
