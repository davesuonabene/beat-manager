
import os
import sys
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine

def main():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    audio_path = os.path.join(base_dir, "assets/ronald/r6 - ronald v1 (mixtape).wav")
    image_path = os.path.join(base_dir, "assets/ronald/coverart_MIX1.png")
    output_video = os.path.join(base_dir, "temp_videos/ronald_r6.mp4")
    
    if not os.path.exists(os.path.dirname(output_video)):
        os.makedirs(os.path.dirname(output_video))

    # 1. Render
    print(f"--- Rendering Video: {output_video} ---")
    video_engine = VideoEngine()
    video_engine.create_video(audio_path, image_path, output_video)
    
    # 2. Upload/Schedule
    print(f"--- Uploading/Scheduling Video for Feb 27 ---")
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_dir = os.path.join(base_dir, "tokens")
    yt_engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    # Research-backed metadata for r6 (Ambient/Atmospheric)
    title = "(free) yves tumor x clams casino type beat - \"ronald\" (ambient / experimental)"
    description = """(FREE) Experimental Type Beat - "RONALD" (Track 6)

Part of the Ronald Mixtape series. Atmospheric and ambient textures.
💰 Purchase/Lease: [Link]
🔥 Subscribe for more experimental sounds.

TIMESTAMPS:
0:00 intro
0:15 drop
0:45 verse
1:15 hook
1:45 outro

TAGS: #ExperimentalTypeBeat #YvesTumor #ClamsCasino #UndergroundHipHop #RonaldMixtape #AmbientTrap"""
    tags = ["yves tumor", "clams casino", "experimental type beat", "ambient trap", "ethereal", "ronald mixtape", "underground hip hop", "glitch", "atmospheric"]
    
    # Schedule for Feb 27, 2026 at 10:00 AM UTC
    publish_time = "2026-02-27T10:00:00Z"
    
    video_id = yt_engine.upload_video(
        channel_id="default_channel",
        file_path=output_video,
        title=title,
        description=description,
        tags=tags,
        category_id="10",
        privacy_status="private",
        publish_at=publish_time
    )
    print(f"Successfully scheduled Video r6. YouTube ID: {video_id}")

if __name__ == "__main__":
    main()
