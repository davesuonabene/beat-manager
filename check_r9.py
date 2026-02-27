
import os
import pickle
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_r9(channel_id):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    with open(token_path, 'rb') as token:
        creds = pickle.load(token)
    youtube = build("youtube", "v3", credentials=creds)

    v_res = youtube.videos().list(part="status,snippet", id="-4GRigCcaB8").execute()
    if v_res["items"]:
        item = v_res["items"][0]
        print(f"R9 Status: {item['status']['privacyStatus']}")
        print(f"R9 Title: {item['snippet']['title']}")
        print(f"R9 PublishAt: {item['status'].get('publishAt', 'N/A')}")
    else:
        print("R9 (-4GRigCcaB8) not found!")

if __name__ == "__main__":
    check_r9("default_channel")
