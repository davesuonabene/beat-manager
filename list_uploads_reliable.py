
import os
import pickle
import sys
from googleapiclient.discovery import build

def list_videos(channel_id, max_results=50):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found for {channel_id} at {token_path}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    try:
        # Get channel's uploads playlist
        channels_response = youtube.channels().list(
            mine=True,
            part="contentDetails"
        ).execute()
        
        uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # List videos in uploads playlist
        playlist_items_response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet,status",
            maxResults=max_results
        ).execute()
        
        print(f"{'Video ID':<15} | {'Title':<50} | {'Status':<10} | {'Scheduled'}")
        print("-" * 100)
        
        for item in playlist_items_response.get("items", []):
            video_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            
            # Detailed status
            v_response = youtube.videos().list(
                part="status,snippet",
                id=video_id
            ).execute()
            
            if not v_response["items"]:
                continue
                
            v_status = v_response["items"][0]["status"]
            privacy = v_status["privacyStatus"]
            publish_at = v_status.get("publishAt", "N/A")
            
            print(f"{video_id:<15} | {title:<50} | {privacy:<10} | {publish_at}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    list_videos("default_channel")
