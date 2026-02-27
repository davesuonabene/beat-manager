import os
import logging
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# The SCOPES required for uploading to YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.force-ssl']

class YouTubeEngine:
    """
    Core engine for handling YouTube uploads using the Google API Python Client.
    Supports multiple channels by managing separate credential/token files.
    """
    def __init__(self, client_secrets_file, token_storage_dir="tokens"):
        """
        :param client_secrets_file: Path to the client_secrets.json file from Google Cloud Console.
        :param token_storage_dir: Directory where channel-specific tokens will be stored.
        """
        self.client_secrets_file = client_secrets_file
        self.token_storage_dir = token_storage_dir
        if not os.path.exists(self.token_storage_dir):
            os.makedirs(self.token_storage_dir)

    def _get_credentials(self, channel_id):
        """
        Gets valid user credentials from storage or runs the auth flow.
        """
        token_path = os.path.join(self.token_storage_dir, f"token_{channel_id}.pickle")
        creds = None

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, SCOPES)
                # For a CLI/TUI, run_local_server is usually best.
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        return creds

    def upload_video(self, channel_id, file_path, title, description, tags=None, category_id="10", privacy_status="private", publish_at=None):
        """
        Uploads a video to YouTube.
        
        :param channel_id: A unique identifier for the channel (used to name the token file).
        :param file_path: Path to the video file.
        :param title: Video title.
        :param description: Video description.
        :param tags: List of tags.
        :param category_id: Category ID (default 10 is 'Music').
        :param privacy_status: 'public', 'private', or 'unlisted'.
        :param publish_at: ISO 8601 datetime string for scheduling. Requires privacy_status='private'.
        :return: Video ID if successful.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        creds = self._get_credentials(channel_id)
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        if publish_at:
            body['status']['publishAt'] = publish_at

        # Call the API's videos.insert method to create and upload the video.
        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
        )

        logger.info(f"Starting upload for: {title}")
        
        video_id = None
        try:
            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    logger.info(f"Uploaded {int(status.progress() * 100)}%...")
            
            video_id = response.get("id")
            logger.info(f"Upload complete! Video ID: {video_id}")
            return video_id

        except HttpError as e:
            logger.error(f"An HTTP error %d occurred: %s" % (e.resp.status, e.content))
            raise
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            raise

    def update_video_metadata(self, channel_id, video_id, title=None, description=None, tags=None):
        """
        Updates metadata for an existing YouTube video.
        """
        creds = self._get_credentials(channel_id)
        youtube = build("youtube", "v3", credentials=creds)

        # 1. Retrieve existing snippet
        list_request = youtube.videos().list(part="snippet", id=video_id)
        list_response = list_request.execute()
        
        if not list_response["items"]:
            raise ValueError(f"Video {video_id} not found.")
        
        snippet = list_response["items"][0]["snippet"]

        # 2. Update fields
        if title: snippet["title"] = title
        if description: snippet["description"] = description
        if tags is not None: snippet["tags"] = tags

        # 3. Push update
        update_request = youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": snippet
            }
        )
        update_response = update_request.execute()
        logger.info(f"Metadata updated for video {video_id}")
        return update_response
