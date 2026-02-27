from video_engine import VideoEngine
import os

def create_ronald_videos():
    ve = VideoEngine()
    assets_dir = "assets/ronald"
    output_dir = "temp_videos"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Track r7 -> Scheduled Feb 28
    audio_r7 = os.path.join(assets_dir, "r7 - ronald v1 (mixtape).wav")
    image = os.path.join(assets_dir, "coverart_MIX1.png")
    output_r7 = os.path.join(output_dir, "ronald_r7.mp4")
    
    print(f"Creating video for r7...")
    ve.create_video(audio_r7, image, output_r7, title_overlay="Ronald - Track 7 (Mixtape)")
    
    # Track r9 -> Scheduled Mar 2
    audio_r9 = os.path.join(assets_dir, "r9 - ronald v1 (mixtape).wav")
    output_r9 = os.path.join(output_dir, "ronald_r9.mp4")
    
    print(f"Creating video for r9...")
    ve.create_video(audio_r9, image, output_r9, title_overlay="Ronald - Track 9 (Mixtape)")

if __name__ == "__main__":
    create_ronald_videos()
