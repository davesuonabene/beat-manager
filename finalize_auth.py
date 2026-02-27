
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

def save_token(url):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_path = os.path.join(base_dir, "tokens", "token_default_channel.pickle")
    
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube.force-ssl',
        'https://www.googleapis.com/auth/youtube.readonly'
    ]
    
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets, 
        SCOPES,
        redirect_uri='http://localhost:43841/'
    )
    
    flow.fetch_token(authorization_response=url)
    creds = flow.credentials
    
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)
    print("Token saved successfully with full scopes.")

if __name__ == "__main__":
    url = "http://localhost:43841/?state=xHfewgE1xvhxNUcl5yz16hxOMqg2mv&iss=https://accounts.google.com&code=4/0AfrIepATLLVjcHxKfASGeNen_tMEcwHikvTG288_GPUNnEaeT2TZiDy-pF7yCaCx6JJ7hw&scope=https://www.googleapis.com/auth/youtube.force-ssl%20https://www.googleapis.com/auth/youtube.readonly%20https://www.googleapis.com/auth/youtube.upload"
    save_token(url)
