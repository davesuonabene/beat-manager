from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
import uuid

class PrivacyEnum(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"

class AssetDataType(str, Enum):
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"

class AssetType(str, Enum):
    RAW = "raw"
    BEAT = "beat"
    SAMPLE = "sample"
    COVER = "cover"
    PROJECT = "project"

class LibraryAsset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique identifier for the asset")
    data_type: AssetDataType = Field(..., description="The primitive data type")
    asset_type: AssetType = Field(default=AssetType.RAW, description="The logical type of asset")
    name: str = Field(..., description="Display name for the asset")
    path: str = Field(..., description="Absolute path to the asset folder or file")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata for the asset")

class AudioAsset(LibraryAsset):
    data_type: AssetDataType = AssetDataType.AUDIO
    audio_file: str = Field(..., description="Filename of the audio")
    notes_file: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[float] = None
    key: Optional[str] = None

class ImageAsset(LibraryAsset):
    data_type: AssetDataType = AssetDataType.IMAGE
    asset_type: AssetType = AssetType.COVER
    width: Optional[int] = None
    height: Optional[int] = None

class BeatAsset(LibraryAsset):
    data_type: AssetDataType = AssetDataType.AUDIO
    asset_type: AssetType = AssetType.BEAT
    # Links to audio files within the beat folder
    versions: Dict[str, str] = Field(default_factory=dict, description="Map of version name to filename (e.g. {'main': 'beat.wav'})")
    notes_file: str = "notes.txt"
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[float] = None
    cover_image_id: Optional[str] = Field(None, description="ID of the ImageAsset used as cover")

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

class TaskResult(BaseModel):
    success: bool = Field(..., description="Whether the task completed successfully")
    output_path: Optional[str] = Field(None, description="Path to the produced output, if applicable")
    error_message: Optional[str] = Field(None, description="Error message if the task failed")
