import os
import datetime
from youtube_engine import YouTubeEngine

def upload_clean_ronald_videos():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_dir = os.path.join(base_dir, "tokens")
    
    engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    # Metadata based on research report
    # Strategy: Use one aggressive and one atmospheric/dreamy for variety
    
    # Video 1: r7 (Track 7) - Scheduled Feb 28, 2026 at 10:00 AM UTC
    title_r7 = '[FREE] KANYE WEST X JPEGMAFIA TYPE BEAT | "RONALD R7" [INDUSTRIAL/EXPERIMENTAL]'
    description_r7 = """[FREE FOR PROFIT] Experimental Type Beat - "RONALD R7"

💰 Purchase/Lease: [Link]
🔥 Subscribe for more experimental sounds.

TIMESTAMPS:
0:00 Intro
0:15 Drop
0:45 Verse
1:15 Hook
1:45 Outro

TAGS: #ExperimentalTypeBeat #JPEGMAFIA #YvesTumor #ClamsCasino #UndergroundHipHop #RonaldMixtape"""
    tags_r7 = "Avant-Garde, Underground Hip Hop, Glitch, Industrial, Ethereal, Utopia Type Beat, Yeezus Type Beat, Ambient Trap, Future Beats"
    publish_time_r7 = "2026-02-28T10:00:00Z"
    
    print(f"Uploading Video 1 (r7_clean)...")
    id7 = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join(base_dir, "temp_videos/ronald_r7_clean.mp4"),
        title=title_r7,
        description=description_r7,
        tags=[t.strip() for t in tags_r7.split(',')],
        category_id="10",
        privacy_status="private",
        publish_at=publish_time_r7
    )
    print(f"Video 1 Uploaded: {id7}")

    # Video 2: r9 (Track 9) - Scheduled Mar 02, 2026 at 10:00 AM UTC
    title_r9 = '(FREE) yves tumor x clams casino type beat - "ronald r9" (ambient / experimental)'
    description_r9 = """[FREE FOR PROFIT] Experimental Type Beat - "RONALD R9"

💰 Purchase/Lease: [Link]
🔥 Subscribe for more experimental sounds.

TIMESTAMPS:
0:00 Intro
0:15 Drop
0:45 Verse
1:15 Hook
1:45 Outro

TAGS: #ExperimentalTypeBeat #JPEGMAFIA #YvesTumor #ClamsCasino #UndergroundHipHop #RonaldMixtape"""
    tags_r9 = "Avant-Garde, Underground Hip Hop, Glitch, Industrial, Ethereal, Utopia Type Beat, Yeezus Type Beat, Ambient Trap, Future Beats"
    publish_time_r9 = "2026-03-02T10:00:00Z"
    
    print(f"Uploading Video 2 (r9_clean)...")
    id9 = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join(base_dir, "temp_videos/ronald_r9_clean.mp4"),
        title=title_r9,
        description=description_r9,
        tags=[t.strip() for t in tags_r9.split(',')],
        category_id="10",
        privacy_status="private",
        publish_at=publish_time_r9
    )
    print(f"Video 2 Uploaded: {id9}")

if __name__ == "__main__":
    upload_clean_ronald_videos()
