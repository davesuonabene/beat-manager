
import os
import pickle
from googleapiclient.discovery import build

def list_my_videos(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found at {token_path}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    print("Fetching first 5 videos using videos().list (this needs specific IDs or myRating)...")
    # Alternatively, use activities
    try:
        request = youtube.activities().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=10
        )
        response = request.execute()
        
        print(f"{'Video ID':<15} | {'Title':<60} | {'Type'}")
        print("-" * 90)
        for item in response.get('items', []):
            if item['snippet']['type'] == 'upload':
                video_id = item['contentDetails']['upload']['videoId']
                title = item['snippet']['title']
                print(f"{video_id:<15} | {title[:60]:<60} | {item['snippet']['type']}")
    except Exception as e:
        print(f"Activities failed: {e}")

if __name__ == "__main__":
    list_my_videos("default_channel")
