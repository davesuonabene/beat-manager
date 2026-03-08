from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

class PrivacyEnum(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"

class AssetType(str, Enum):
    BEAT = "beat"
    SAMPLE = "sample"
    IMAGE = "image"
    VIDEO = "video"

class LibraryAsset(BaseModel):
    id: str = Field(..., description="Unique identifier for the asset (slug or UUID)")
    type: AssetType = Field(..., description="The type of asset")
    name: str = Field(..., description="Display name for the asset")
    path: str = Field(..., description="The directory containing the asset files")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata for the asset")

class BeatAsset(LibraryAsset):
    audio_file: str = Field(..., description="Relative path to the main audio file (relative to asset path)")
    notes_file: str = Field(..., description="Relative path to the notes.txt file (relative to asset path)")
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[float] = None

class RenderConfig(BaseModel):
    audio_path: str = Field(..., description="Path to the audio file")
    image_path: str = Field(..., description="Path to the background image")
    output_path: str = Field(..., description="Target path for the rendered video")
    project_tag: str = Field(..., description="Tag for identifying the project and mapping assets")

class UploadConfig(BaseModel):
    video_path: str = Field(..., description="Path to the video file to upload")
    title: str = Field(..., description="YouTube video title")
    description: str = Field(default="Automated upload.", description="YouTube video description")
    privacy: PrivacyEnum = Field(default=PrivacyEnum.PRIVATE, description="Video privacy setting")
    publish_at: Optional[str] = Field(None, description="ISO 8601 formatted string for scheduled publishing")

class ResearchConfig(BaseModel):
    niche: str = Field(..., description="Niche or topic for research")
    keywords_count: int = Field(default=10, description="Number of keywords to extract")

class TaskResult(BaseModel):
    success: bool = Field(..., description="Whether the task completed successfully")
    output_path: Optional[str] = Field(None, description="Path to the produced output, if applicable")
    error_message: Optional[str] = Field(None, description="Error message if the task failed")
