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

class CollectionType(str, Enum):
    BEAT = "beat"
    SAMPLE = "sample"

class SampleType(str, Enum):
    LOOP = "loop"
    ONE_SHOT = "one-shot"

class Collection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique identifier for the collection")
    name: str = Field(..., description="Name of the collection")
    type: CollectionType = Field(..., description="Type of collection (beat or sample)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class LibraryAsset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique identifier for the asset")
    data_type: AssetDataType = Field(..., description="The primitive data type")
    asset_type: AssetType = Field(default=AssetType.RAW, description="The logical type of asset")
    name: str = Field(..., description="Display name for the asset")
    path: str = Field(..., description="Absolute path to the asset folder or file")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata for the asset")
    in_trash: bool = Field(default=False, description="Whether the asset is currently in the trash")
    collection_id: Optional[str] = Field(None, description="ID of the collection this asset belongs to")

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
    cover_image_id: Optional[str] = Field(None, description="ID of the ImageAsset used as cover (Deprecated: Use linked_assets)")
    
    # New tracking fields
    raw_dir: Optional[str] = Field(None, description="Relative path to raw source directory within beat root")
    release_dir: Optional[str] = Field(None, description="Relative path to release/export directory within beat root")
    trash_path: Optional[str] = Field(None, description="Path to trash location if moved")
    linked_assets: Dict[str, str] = Field(default_factory=dict, description="Map of roles to asset IDs (e.g. {'project': 'id123', 'stems': 'id456'})")
    has_mp3: bool = Field(default=False, description="Whether the beat has an MP3 version")
    has_master: bool = Field(default=False, description="Whether the beat has a mastered version")
    stems_path: Optional[str] = Field(None, description="Path to the stems if available")

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

class YTVideoUploadSchema(BaseModel):
    video_file_path: str = Field(..., description="Path to the video file")
    thumbnail_file_path: Optional[str] = Field(None, description="Path to the thumbnail file")
    title: str = Field(..., description="Title of the video")
    description: str = Field(..., description="Description of the video")
    tags: List[str] = Field(default_factory=list, description="List of tags")
    category_id: str = Field(default="10", description="Category ID")
    privacy_status: PrivacyEnum = Field(default=PrivacyEnum.PRIVATE, description="Privacy status")
    publish_at: Optional[str] = Field(None, description="ISO 8601 publish date")

class VideoDataSchema(BaseModel):
    video_id: str
    views: int
    likes: int
    comment_count: int
    retention_rate: Optional[float] = None

class ChannelDataSchema(BaseModel):
    channel_id: str
    subscriber_count: int
    total_views: int
    video_count: int

class YTUploadAsset(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique identifier for the upload asset")
    video_file_path: str = Field(..., description="Path to the video file")
    thumbnail_file_path: Optional[str] = Field(None, description="Path to the thumbnail file")
    title: str = Field(..., description="YouTube video title")
    description: str = Field(default="", description="YouTube video description")
    tags: List[str] = Field(default_factory=list, description="List of tags")
    category_id: str = Field(default="10", description="Category ID")
    privacy_status: PrivacyEnum = Field(default=PrivacyEnum.PRIVATE, description="Video privacy setting")
    publish_at: Optional[str] = Field(None, description="ISO 8601 formatted string for scheduled publishing")
    status: str = Field(default="draft", description="Status: draft, queued, uploaded, error")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    youtube_id: Optional[str] = Field(None, description="YouTube Video ID once uploaded")

class SampleAsset(LibraryAsset):
    data_type: AssetDataType = AssetDataType.AUDIO
    asset_type: AssetType = AssetType.SAMPLE
    bpm: Optional[float] = None
    key: Optional[str] = None
    sample_type: SampleType = Field(default=SampleType.ONE_SHOT, description="Type of sample (loop or one-shot)")
    duration: Optional[float] = None

