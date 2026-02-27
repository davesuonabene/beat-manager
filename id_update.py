
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_by_id(channel_id, video_id, r_num):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)

    try:
        v_res = youtube.videos().list(part="snippet", id=video_id).execute()
        if not v_res["items"]:
            logger.error(f"Video {video_id} not found.")
            return
            
        snippet = v_res["items"][0]["snippet"]
        formatted_num = str(r_num).zfill(3)
        new_title = f"[FREE] RONALD R{r_num} | beats[R][{formatted_num}] (Experimental Type Beat)"
        
        logger.info(f"Updating {video_id} to: {new_title}")
        snippet["title"] = new_title
        
        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet}
        ).execute()
        logger.info("Done.")
    except Exception as e:
        logger.error(f"Failed to update {video_id}: {e}")

if __name__ == "__main__":
    # R7
    update_by_id("default_channel", "DP1S3PaxoIQ", 7)
    # R9
    update_by_id("default_channel", "-4GRigCcaB8", 9)
