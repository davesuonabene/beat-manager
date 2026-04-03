import os
import logging
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from app.models.schemas import UploadConfig, TaskResult, YTVideoUploadSchema, VideoDataSchema, ChannelDataSchema

# Internal logger for this module
logger = logging.getLogger(__name__)

# The SCOPES required for uploading to YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.force-ssl']

class YouTubeEngine:
    """
    Core engine for handling YouTube uploads using the Google API Python Client.
    Pure logic and maintains no application state.
    """
    def __init__(self, client_secrets_file: str, token_storage_dir: str = "tokens"):
        """
        :param client_secrets_file: Path to the client_secrets.json file from Google Cloud Console.
        :param token_storage_dir: Directory where channel-specific tokens will be stored.
        """
        self.client_secrets_file = client_secrets_file
        self.token_storage_dir = token_storage_dir
        if not os.path.exists(self.token_storage_dir):
            os.makedirs(self.token_storage_dir)

    def _get_credentials(self, channel_id: str):
        """
        Internal helper: gets valid user credentials from storage or runs the auth flow.
        """
        token_path = os.path.join(self.token_storage_dir, f"token_{channel_id}.pickle")
        creds = None

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                try:
                    creds = pickle.load(token)
                except Exception as e:
                    logger.warning(f"Failed to load existing token for {channel_id}: {e}")

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Token refresh failed for {channel_id}: {e}. Restarting auth flow.")
                    creds = self._run_auth_flow()
            else:
                creds = self._run_auth_flow()
            
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        return creds

    def _run_auth_flow(self):
        """Internal helper to run the OAuth flow."""
        if not os.path.exists(self.client_secrets_file):
            raise FileNotFoundError(f"Missing client secrets file: {self.client_secrets_file}")
        
        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, SCOPES)
        # For a CLI/TUI, run_local_server is usually best.
        return flow.run_local_server(port=0)

    def upload_video(self, channel_id: str, config: UploadConfig) -> TaskResult:
        """
        Uploads a video to YouTube using the provided configuration.
        
        :param channel_id: A unique identifier for the channel (used to name the token file).
        :param config: UploadConfig object containing video details.
        :return: TaskResult object containing the video ID as output_path if successful.
        """
        file_path = config.video_path
        if not os.path.exists(file_path):
            return TaskResult(success=False, error_message=f"Video file not found: {file_path}")

        try:
            creds = self._get_credentials(channel_id)
            # Re-initializing service per upload to ensure correct creds/timeout context
            import httplib2
            import google_auth_httplib2
            http_client = httplib2.Http(timeout=120)
            authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http_client)
            youtube = build("youtube", "v3", http=authorized_http)

            body = {
                'snippet': {
                    'title': config.title,
                    'description': config.description,
                    'categoryId': "10" # Default to Music
                },
                'status': {
                    'privacyStatus': config.privacy.value,
                    'selfDeclaredMadeForKids': False
                }
            }
            
            if config.publish_at:
                body['status']['publishAt'] = config.publish_at

            # Call the API's videos.insert method to create and upload the video.
            insert_request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
            )

            logger.info(f"Starting upload for: {config.title}")
            
            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    logger.info(f"Uploaded {int(status.progress() * 100)}%...")
            
            video_id = response.get("id")
            logger.info(f"Upload complete! Video ID: {video_id}")
            return TaskResult(success=True, output_path=video_id)

        except HttpError as e:
            error_msg = f"HTTP error {e.resp.status}: {e.content}"
            logger.error(error_msg)
            return TaskResult(success=False, error_message=error_msg)
        except Exception as e:
            logger.error(f"Unexpected error during YouTube upload: {str(e)}")
            return TaskResult(success=False, error_message=str(e))

    def upload_video_v2(self, upload_data: YTVideoUploadSchema) -> bool:
        """Mock upload video."""
        return True

    def get_video_data(self, video_id: str) -> VideoDataSchema:
        """Mock get video data."""
        return VideoDataSchema(
            video_id=video_id,
            views=1500,
            likes=120,
            comment_count=15,
            retention_rate=45.2
        )

    def get_channel_data(self, channel_id: str) -> ChannelDataSchema:
        """Mock get channel data."""
        return ChannelDataSchema(
            channel_id=channel_id,
            subscriber_count=10000,
            total_views=500000,
            video_count=42
        )

if __name__ == "__main__":
    print("YouTubeEngine class loaded from app.core.youtube_engine.")
