import os
import json
import logging
from google_auth_oauthlib.flow import InstalledAppFlow

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_auth_url():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    
    # Use a redirect URI that is standard for "manual copy-paste" (though Google is phasing it out, some libraries still support it or allow showing the URL)
    # The most reliable way in modern OAuth for headless is run_local_server(open_browser=False) 
    # but that expects the redirect to actually hit the server.
    
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets, 
        scopes=SCOPES,
        redirect_uri='http://localhost:8080'
    )
    
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    print(f"AUTH_URL_START")
    print(auth_url)
    print(f"AUTH_URL_END")

if __name__ == "__main__":
    get_auth_url()
