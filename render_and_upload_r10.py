
import os
import sys
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine

def main():
    base_dir = "/home/davesuonabene/.openclaw/workspace/projects/beat-manager"
    audio_path = os.path.join(base_dir, "assets/ronald/r10 - ronald v1 (mixtape).wav")
    image_path = os.path.join(base_dir, "assets/ronald/coverart_MIX1.png")
    output_video = os.path.join(base_dir, "temp_videos/ronald_r10.mp4")
    
    if not os.path.exists(os.path.dirname(output_video)):
        os.makedirs(os.path.dirname(output_video))

    # 1. Render
    print(f"--- Rendering Video: {output_video} ---")
    video_engine = VideoEngine()
    video_engine.create_video(audio_path, image_path, output_video)
    
    # 2. Upload/Schedule
    print(f"--- Uploading/Scheduling Video for Mar 01 ---")
    client_secrets = os.path.join(base_dir, "client_secrets.json")
    token_dir = os.path.join(base_dir, "tokens")
    yt_engine = YouTubeEngine(client_secrets, token_storage_dir=token_dir)
    
    title = '[FREE] MELODIC TRAP BEAT | "beats[R][010]" (EXPERIMENTAL)'
    description = """[FREE] Experimental Melodic Trap Beat - "beats[R][010]" (Mar 01)

Part of the Ronald Mixtape series.
#MelodicTrap #Experimental #TypeBeat #RonaldMixtape"""
    tags = ["melodic trap", "experimental type beat", "ronald mixtape", "underground hip hop"]
    
    # Schedule for Mar 01, 2026 at 10:00 AM UTC
    publish_time = "2026-03-01T10:00:00Z"
    
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
    print(f"Successfully scheduled Video r10. YouTube ID: {video_id}")

if __name__ == "__main__":
    main()
