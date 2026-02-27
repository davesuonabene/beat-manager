import os
import json
import logging
from youtube_engine import YouTubeEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_scheduled_upload():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    metadata_file = os.path.join(base_dir, "upload_metadata.json")
    token_dir = os.path.join(base_dir, "tokens")
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    # Use the publish_at from metadata
    print(f"Starting scheduled upload for: {metadata['title']} (Scheduled: {metadata['publish_at']})")
    
    video_id = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join("/home/davesuonabene/.openclaw/workspace", metadata['video_path']),
        title=metadata['title'],
        description=metadata['description'],
        tags=metadata['tags'].split(','),
        category_id=metadata['category'],
        privacy_status="private", # Must be private to be scheduled
        publish_at=metadata['publish_at']
    )
    
    if video_id:
        print(f"SUCCESS: Video uploaded and scheduled with ID: {video_id}")
    else:
        print("FAILED: Video upload failed.")

if __name__ == "__main__":
    run_scheduled_upload()