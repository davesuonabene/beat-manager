
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_r9(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    with open(token_path, 'rb') as token:
        creds = pickle.load(token)
    youtube = build("youtube", "v3", credentials=creds)

    v_id = "-4GRigCcaB8"
    v_res = youtube.videos().list(part="snippet", id=v_id).execute()
    if not v_res["items"]:
        print("R9 not found.")
        return

    snippet = v_res["items"][0]["snippet"]
    new_title = '(FREE) yves tumor x clams casino type beat - "ronald r9" | beats[R][009] (ambient / experimental)'
    
    print(f"Updating R9 title to: {new_title}")
    snippet["title"] = new_title
    youtube.videos().update(
        part="snippet",
        body={"id": v_id, "snippet": snippet}
    ).execute()
    print("Update complete.")

if __name__ == "__main__":
    update_r9("default_channel")
