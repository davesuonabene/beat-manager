
import os
import pickle
from googleapiclient.discovery import build

def list_scheduled_videos(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found for {channel_id}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    # List uploaded videos
    request = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=50
    )
    response = request.execute()
    
    print(f"{'Video ID':<15} | {'Title':<40} | {'Published At'}")
    print("-" * 75)
    for item in response.get('items', []):
        video_id = item['id']['videoId']
        title = item['snippet']['title']
        published_at = item['snippet']['publishedAt']
        print(f"{video_id:<15} | {title:<40} | {published_at}")

if __name__ == "__main__":
    list_scheduled_videos("default_channel")
