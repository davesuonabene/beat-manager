
import os
import sys
import pickle
from googleapiclient.discovery import build

def list_recent_uploads(channel_id, max_results=5):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found for {channel_id} at {token_path}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    try:
        # Get uploaded videos
        request = youtube.search().list(
            part="snippet",
            forMine=True,
            maxResults=max_results,
            type="video",
            order="date"
        )
        response = request.execute()
        
        print(f"{'Video ID':<15} | {'Title':<40} | {'Status'}")
        print("-" * 70)
        for item in response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            
            # Get specific video status (privacy)
            v_request = youtube.videos().list(
                part="status,snippet",
                id=video_id
            )
            v_response = v_request.execute()
            status = v_response['items'][0]['status']['privacyStatus']
            publish_at = v_response['items'][0]['status'].get('publishAt', 'N/A')
            
            print(f"{video_id:<15} | {title:<40} | {status} (PubAt: {publish_at})")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    list_recent_uploads("default_channel")
