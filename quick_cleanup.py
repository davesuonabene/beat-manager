
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def quick_cleanup(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)

    # 1. LIST VIDEOS (Using uploads playlist)
    try:
        channels_response = youtube.channels().list(mine=True, part="contentDetails").execute()
        uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        playlist_items = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=20
        ).execute()
        
        known_r9_id = "-4GRigCcaB8"
        known_r7_id = "DP1S3PaxoIQ"
        
        for item in playlist_items.get("items", []):
            v_id = item["snippet"]["resourceId"]["videoId"]
            
            # Fetch status/schedule
            v_res = youtube.videos().list(part="status,snippet", id=v_id).execute()
            if not v_res["items"]: continue
            
            video_item = v_res["items"][0]
            snippet = video_item["snippet"]
            status = video_item["status"]
            publish_at = status.get("publishAt", "")
            title = snippet["title"]
            
            # DUPLICATE CHECK: R9 on March 2nd
            if "R9" in title and "2026-03-02" in publish_at:
                if v_id != known_r9_id:
                    logger.info(f"Deleting duplicate R9: {v_id} ('{title}') scheduled for {publish_at}")
                    youtube.videos().delete(id=v_id).execute()
                    logger.info("Deleted successfully.")
                    continue

            # METADATA UPDATE: beats[R][00x]
            r_num = None
            if "R7" in title: r_num = "007"
            elif "R9" in title: r_num = "009"
            
            if r_num:
                new_title = f"[FREE] RONALD R{r_num[2]} | beats[R][{r_num}] (Experimental Type Beat)"
                if title != new_title:
                    logger.info(f"Updating {v_id} title to: {new_title}")
                    snippet["title"] = new_title
                    youtube.videos().update(
                        part="snippet",
                        body={"id": v_id, "snippet": snippet}
                    ).execute()
                    logger.info("Updated successfully.")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

if __name__ == "__main__":
    quick_cleanup("default_channel")
