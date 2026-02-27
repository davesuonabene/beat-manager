import os
import json
import logging
import sys
from youtube_engine import YouTubeEngine
from google_auth_oauthlib.flow import InstalledAppFlow

# Setup logging to see the progress
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_upload_with_manual_auth():
    # Paths
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    metadata_file = os.path.join(base_dir, "upload_metadata.json")
    token_dir = os.path.join(base_dir, "tokens")
    
    # Load metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    # Initialize Engine
    if not os.path.exists(token_dir):
        os.makedirs(token_dir)
        
    engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    # Handle SCOPES and Flow for headless environment
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    # We check if token already exists to skip auth
    token_path = os.path.join(token_dir, "token_default_channel.pickle")
    if not os.path.exists(token_path):
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        
        # USE PROVIDED CODE
        code = "4/1AfrIepCApE10y-lHH6PingTne2QICdOwMmAdPhVNxyeYBMU5XOQsMvnk8GA"
        print(f"Attempting to fetch token with provided code: {code}")
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Save credentials for future use
        import pickle
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        print("Authentication successful and credentials saved.\n", flush=True)

    # Proceed with upload
    print(f"Starting upload for: {metadata['title']}", flush=True)
    video_id = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join("/home/davesuonabene/.openclaw/workspace", metadata['video_path']),
        title=metadata['title'],
        description=metadata['description'],
        tags=metadata['tags'].split(','),
        category_id=metadata['category'],
        privacy_status=metadata['privacy']
    )
    
    if video_id:
        print(f"SUCCESS: Video uploaded with ID: {video_id}", flush=True)
    else:
        print("FAILED: Video upload did not return an ID.", flush=True)

if __name__ == "__main__":
    run_upload_with_manual_auth()
