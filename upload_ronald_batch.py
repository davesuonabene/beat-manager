import os
import datetime
from youtube_engine import YouTubeEngine

def upload_ronald_videos():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_dir = os.path.join(base_dir, "tokens")
    
    engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    # Metadata templates
    tags = "experimental type beat, wide broad beats, experimental hip hop, avant-garde beats, atmospheric type beat, underground hip hop, dark experimental beat"
    description_template = """Experimental Type Beat - "{title}"
Part of the Ronald Mixtape series.

Exploring wide, broad soundscapes and experimental textures.
#experimental #typebeat #ronald #mixtape #hiphop

(Scheduled Upload)"""

    # Video 1: r7 - Scheduled Feb 28, 2026 at 10:00 AM UTC
    # Note: Using UTC for simplicity, adjust if needed.
    publish_time_r7 = "2026-02-28T10:00:00Z"
    
    print(f"Uploading Video 1 (r7)...")
    id7 = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join(base_dir, "temp_videos/ronald_r7.mp4"),
        title="Ronald - Track 7 (Experimental Type Beat)",
        description=description_template.format(title="Track 7"),
        tags=tags.split(','),
        category_id="10",
        privacy_status="private",
        publish_at=publish_time_r7
    )
    print(f"Video 1 Uploaded: {id7}")

    # Video 2: r9 - Scheduled Mar 02, 2026 at 10:00 AM UTC
    publish_time_r9 = "2026-03-02T10:00:00Z"
    
    print(f"Uploading Video 2 (r9)...")
    id9 = engine.upload_video(
        channel_id="default_channel",
        file_path=os.path.join(base_dir, "temp_videos/ronald_r9.mp4"),
        title="Ronald - Track 9 (Experimental Type Beat)",
        description=description_template.format(title="Track 9"),
        tags=tags.split(','),
        category_id="10",
        privacy_status="private",
        publish_at=publish_time_r9
    )
    print(f"Video 2 Uploaded: {id9}")

if __name__ == "__main__":
    upload_ronald_videos()
