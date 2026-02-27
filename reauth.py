
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.readonly'
]

def reauth():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_path = os.path.join(base_dir, "tokens", "token_default_channel.pickle")
    
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    # This will prompt for a code/URL
    creds = flow.run_local_server(port=0)
    
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)
    print("Re-authenticated with full scopes.")

if __name__ == "__main__":
    reauth()
