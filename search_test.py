
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_search_scopes(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    try:
        print("Attempting search().list with q='RONALD'...")
        # Search doesn't require forMine if public
        request = youtube.search().list(
            part="snippet",
            q="RONALD",
            type="video",
            maxResults=10
        )
        response = request.execute()
        for item in response.get("items", []):
            print(f"Found: {item['snippet']['title']} ({item['id']['videoId']})")
            
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    check_search_scopes("default_channel")
