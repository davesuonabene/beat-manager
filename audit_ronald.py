
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def audit_videos(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found for {channel_id}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    # Target Video IDs from context
    target_ids = ["DP1S3PaxoIQ", "-4GRigCcaB8"]
    
    print(f"{'Video ID':<15} | {'Title':<50} | {'Status'}")
    print("-" * 80)
    
    # 1. Check the specific IDs provided
    v_response = youtube.videos().list(
        part="snippet,status",
        id=",".join(target_ids)
    ).execute()
    
    found_ids = []
    for item in v_response.get("items", []):
        video_id = item["id"]
        title = item["snippet"]["title"]
        privacy = item["status"]["privacyStatus"]
        found_ids.append(video_id)
        print(f"{video_id:<15} | {title:<50} | {privacy}")

    # 2. Search for other 'RONALD' videos to find duplicates or metadata issues
    search_response = youtube.search().list(
        part="snippet",
        q="RONALD",
        type="video",
        forMine=True,
        maxResults=50
    ).execute()
    
    print("\nRecent 'RONALD' related videos from search:")
    print(f"{'Video ID':<15} | {'Title':<50}")
    print("-" * 70)
    
    ronald_videos = []
    for item in search_response.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        ronald_videos.append({"id": video_id, "title": title})
        print(f"{video_id:<15} | {title:<50}")

    return ronald_videos

if __name__ == "__main__":
    audit_videos("default_channel")
