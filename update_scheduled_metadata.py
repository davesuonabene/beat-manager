
import os
import sys
import pickle
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def update_video_metadata(channel_id, video_id, new_title, new_description, new_tags):
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_path = os.path.join(base_dir, "tokens", f"token_{channel_id}.pickle")
    
    if not os.path.exists(token_path):
        print(f"Token not found for {channel_id} at {token_path}")
        return

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    youtube = build("youtube", "v3", credentials=creds)
    
    body = {
        'id': video_id,
        'snippet': {
            'title': new_title,
            'description': new_description,
            'tags': new_tags,
            'categoryId': "10"
        }
    }
    
    try:
        print(f"Updating metadata for Video ID: {video_id}...")
        request = youtube.videos().update(
            part="snippet",
            body=body
        )
        response = request.execute()
        print(f"Successfully updated Video: {response.get('snippet', {}).get('title')}")
    except HttpError as e:
        print(f"Error updating video %d: %s" % (e.resp.status, e.content))
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Aggressive: [FREE] KANYE WEST X JPEGMAFIA TYPE BEAT | "RONALD" [INDUSTRIAL/EXPERIMENTAL]
    # Ambient: (free) yves tumor x clams casino type beat - "ronald" (ambient / experimental)
    
    # Track 7 (Feb 28) - Aggressive
    update_video_metadata(
        "default_channel", 
        "VIDEO_ID_R7", # Need to find the real IDs
        "[FREE] KANYE WEST X JPEGMAFIA TYPE BEAT | \"RONALD\" [INDUSTRIAL/EXPERIMENTAL]",
        """[FREE FOR PROFIT] Experimental Type Beat - "RONALD" (Track 7)

Part of the Ronald Mixtape series. Aggressive and industrial textures.
💰 Purchase/Lease: [Link]
🔥 Subscribe for more experimental sounds.

TIMESTAMPS:
0:00 Intro
0:15 Drop
0:45 Verse
1:15 Hook
1:45 Outro

TAGS: #ExperimentalTypeBeat #KanyeWest #JPEGMAFIA #IndustrialHipHop #RonaldMixtape""",
        ["kanye west", "jpegmafia", "industrial type beat", "experimental type beat", "yeezus era", "ronald mixtape", "underground hip hop", "glitch", "aggressive"]
    )
    
    # Track 9 (Mar 02) - Ambient
    update_video_metadata(
        "default_channel",
        "VIDEO_ID_R9", # Need to find the real IDs
        "(free) yves tumor x clams casino type beat - \"ronald\" (ambient / experimental)",
        """(FREE) Experimental Type Beat - "RONALD" (Track 9)

Part of the Ronald Mixtape series. Atmospheric and ambient textures.
💰 Purchase/Lease: [Link]
🔥 Subscribe for more experimental sounds.

TIMESTAMPS:
0:00 intro
0:15 drop
0:45 verse
1:15 hook
1:45 outro

TAGS: #ExperimentalTypeBeat #YvesTumor #ClamsCasino #UndergroundHipHop #RonaldMixtape #AmbientTrap""",
        ["yves tumor", "clams casino", "experimental type beat", "ambient trap", "ethereal", "ronald mixtape", "underground hip hop", "glitch", "atmospheric"]
    )
