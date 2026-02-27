
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
    
    print("Fetching channel uploads playlist ID...")
    ch_request = youtube.channels().list(part="contentDetails", mine=True)
    ch_response = ch_request.execute()
    uploads_playlist_id = ch_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    print(f"Uploads playlist ID: {uploads_playlist_id}")

    print("Fetching first 10 items from uploads playlist...")
    pi_request = youtube.playlistItems().list(
        part="snippet,contentDetails,status",
        playlistId=uploads_playlist_id,
        maxResults=10
    )
    pi_response = pi_request.execute()
    playlist_items = pi_response.get('items', [])

    print(f"{'Video ID':<15} | {'Title':<60} | {'Status':<10} | {'Publish At'}")
    print("-" * 105)
    for item in playlist_items:
        video_id = item['contentDetails']['videoId']
        title = item['snippet']['title']
        
        v_request = youtube.videos().list(part="snippet,status", id=video_id)
        v_response = v_request.execute()
        if not v_response['items']: continue
        
        v_item = v_response['items'][0]
        status = v_item['status']['privacyStatus']
        publish_at = v_item['status'].get('publishAt', 'N/A')
        
        print(f"{video_id:<15} | {title[:60]:<60} | {status:<10} | {publish_at}")

if __name__ == "__main__":
    list_my_videos("default_channel")
