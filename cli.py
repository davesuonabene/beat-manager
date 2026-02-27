import argparse
import os
import sys
from state_manager import StateManager
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine
from analytics_engine import AnalyticsEngine
from strategy_engine import StrategyEngine

def main():
    parser = argparse.ArgumentParser(description="Beat Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Render Command
    render_parser = subparsers.add_parser("render", help="Render a video from audio and image")
    render_parser.add_argument("--audio", required=True, help="Path to audio file (.mp3)")
    render_parser.add_argument("--image", required=True, help="Path to image file (.png)")
    render_parser.add_argument("--title", help="Title for the project (optional)")
    render_parser.add_argument("--output", default="output.mp4", help="Output video path")

    # Upload Command
    upload_parser = subparsers.add_parser("upload", help="Upload a video to YouTube")
    upload_parser.add_argument("--video", required=True, help="Path to video file")
    upload_parser.add_argument("--title", required=True, help="YouTube video title")
    upload_parser.add_argument("--description", default="", help="YouTube video description")
    upload_parser.add_argument("--tags", default="", help="Comma-separated tags")
    upload_parser.add_argument("--channel", default="default_channel", help="Channel name to upload to")
    upload_parser.add_argument("--category", default="10", help="Category ID (default 10: Music)")
    upload_parser.add_argument("--privacy", default="private", choices=["public", "private", "unlisted"], help="Privacy status")
    upload_parser.add_argument("--publish_at", help="Schedule time (ISO 8601 string)")

    # Analyze Command
    analyze_parser = subparsers.add_parser("analyze", help="Perform keyword and trend analysis")
    analyze_parser.add_argument("--keywords", required=True, help="Comma-separated keywords to analyze")
    analyze_parser.add_argument("--deep", action="store_true", help="Perform targeted YouTube deep-dive")

    # Discover Command
    discover_parser = subparsers.add_parser("discover", help="Perform niche discovery and strategy planning")
    discover_parser.add_argument("--seed", required=True, help="Seed Niche or Intent (e.g., 'trip hop, clams casino')")

    # Update Metadata Command
    update_parser = subparsers.add_parser("update", help="Update metadata of an existing YouTube video")
    update_parser.add_argument("--video_id", required=True, help="The YouTube Video ID")
    update_parser.add_argument("--title", help="New title")
    update_parser.add_argument("--description", help="New description")
    update_parser.add_argument("--tags", help="New comma-separated tags")
    update_parser.add_argument("--channel", default="default_channel", help="Channel name")

    # Status Command
    status_parser = subparsers.add_parser("status", help="Show current queue and state")

    args = parser.parse_args()
    state = StateManager()

    if args.command == "render":
        task_id = state.add_task("RENDER", args.output, audio=args.audio, image=args.image)
        print(f"Added RENDER task for {args.output} (ID: {task_id})")
        
        try:
            state.update_task_status(task_id, "Rendering...")
            engine = VideoEngine()
            engine.create_video(args.audio, args.image, args.output)
            state.update_task_status(task_id, "Finished")
            print(f"Successfully rendered: {args.output}")
        except Exception as e:
            state.update_task_status(task_id, f"Error: {str(e)}")
            print(f"Error rendering video: {e}", file=sys.stderr)

    elif args.command == "upload":
        task_id = state.add_task("UPLOAD", args.title, video=args.video)
        print(f"Added UPLOAD task for {args.title} (ID: {task_id})")

        try:
            state.update_task_status(task_id, "Uploading...")
            if not os.path.exists("client_secrets.json"):
                raise FileNotFoundError("client_secrets.json not found.")
            
            engine = YouTubeEngine("client_secrets.json")
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            engine.upload_video(args.channel, args.video, args.title, args.description, tags, args.category, args.privacy, publish_at=args.publish_at)
            state.update_task_status(task_id, "Uploaded")
            print(f"Successfully uploaded: {args.title}")
        except Exception as e:
            state.update_task_status(task_id, f"Error: {str(e)}")
            print(f"Error uploading video: {e}", file=sys.stderr)

    elif args.command == "analyze":
        task_id = state.add_task("ANALYZE", args.keywords)
        print(f"Added ANALYZE task for {args.keywords} (ID: {task_id})")
        
        try:
            state.update_task_status(task_id, "Analyzing...")
            engine = AnalyticsEngine()
            keywords = [k.strip() for k in args.keywords.split(",")]
            results = engine.analyze_keywords(keywords, use_youtube=args.deep)
            state.update_task_status(task_id, "Completed")
            print(f"Successfully completed analysis for: {args.keywords}")
        except Exception as e:
            state.update_task_status(task_id, f"Error: {str(e)}")
            print(f"Error during analysis: {e}", file=sys.stderr)

    elif args.command == "discover":
        task_id = state.add_task("DISCOVER", args.seed)
        print(f"Added DISCOVER task for {args.seed} (ID: {task_id})")

        try:
            state.update_task_status(task_id, "Discovering...")
            engine = StrategyEngine()
            niche_map = engine.generate_niche_map(args.seed)
            template_path = os.path.join("branding", "strategy_template.md")
            output_dir = os.path.join("branding", "reports")
            report_path = engine.generate_report(niche_map, template_path, output_dir)
            state.update_task_status(task_id, "Completed")
            print(f"Successfully completed discovery for: {args.seed}")
            print(f"Report generated at: {report_path}")
        except Exception as e:
            state.update_task_status(task_id, f"Error: {str(e)}")
            print(f"Error during discovery: {e}", file=sys.stderr)

    elif args.command == "update":
        print(f"Updating metadata for video {args.video_id}...")
        try:
            if not os.path.exists("client_secrets.json"):
                raise FileNotFoundError("client_secrets.json not found.")
            
            engine = YouTubeEngine("client_secrets.json")
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
            engine.update_video_metadata(
                args.channel, 
                args.video_id, 
                title=args.title, 
                description=args.description, 
                tags=tags
            )
            print(f"Successfully updated metadata for: {args.video_id}")
        except Exception as e:
            print(f"Error updating video metadata: {e}", file=sys.stderr)

    elif args.command == "status":
        tasks = state.get_tasks()
        if not tasks:
            print("Queue is empty.")
        else:
            print(f"{'ID':<4} | {'Type':<8} | {'Target':<20} | {'Status':<15}")
            print("-" * 55)
            for task in tasks:
                print(f"{task.doc_id:<4} | {task['type']:<8} | {task['target']:<20} | {task['status']:<15}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
