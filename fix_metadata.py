
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_ronald_metadata(channel_id, video_id, r_num):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        logger.error(f"Token not found for {channel_id}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    # 1. Retrieve existing snippet
    try:
        list_request = youtube.videos().list(part="snippet", id=video_id)
        list_response = list_request.execute()
        
        if not list_response["items"]:
            logger.error(f"Video {video_id} not found.")
            return
        
        snippet = list_response["items"][0]["snippet"]
        old_title = snippet["title"]
        
        # 2. Format new title: beats[R][00x]
        # Example: beats[R][007] or beats[R][009]
        formatted_num = str(r_num).zfill(3)
        tag = f"beats[R][{formatted_num}]"
        
        if tag in old_title:
            logger.info(f"Video {video_id} already has correct tag. Skipping.")
            return

        new_title = f"{old_title} {tag}"
        snippet["title"] = new_title

        # 3. Push update
        update_request = youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": snippet
            }
        )
        update_response = update_request.execute()
        logger.info(f"Updated {video_id}: {old_title} -> {new_title}")
        return update_response
        
    except Exception as e:
        logger.error(f"Error updating {video_id}: {e}")

if __name__ == "__main__":
    # RONALD R7: DP1S3PaxoIQ
    # RONALD R9: -4GRigCcaB8
    update_ronald_metadata("default_channel", "DP1S3PaxoIQ", 7)
    update_ronald_metadata("default_channel", "-4GRigCcaB8", 9)
