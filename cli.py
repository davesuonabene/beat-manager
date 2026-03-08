import argparse
import os
import sys
import json
import traceback
from state_manager import StateManager
from strategy_manager import StrategyManager
from app.services.dispatcher import TaskDispatcher
from app.models.schemas import RenderConfig, UploadConfig, PrivacyEnum

def main():
    parser = argparse.ArgumentParser(description="Beat Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Render Command
    render_parser = subparsers.add_parser("render", help="Render a video from audio and image")
    render_parser.add_argument("--audio", required=True)
    render_parser.add_argument("--image", required=True)
    render_parser.add_argument("--output", default="output.mp4")
    render_parser.add_argument("--tag", default="cli_render")

    # Upload Command
    upload_parser = subparsers.add_parser("upload", help="Upload a video to YouTube")
    upload_parser.add_argument("--video", required=True)
    upload_parser.add_argument("--title", required=True)
    upload_parser.add_argument("--description", default="Automated upload.")
    upload_parser.add_argument("--privacy", default="private", choices=["private", "public", "unlisted"])
    upload_parser.add_argument("--publish_at", help="Schedule time (ISO 8601)")

    # Queue Command
    queue_parser = subparsers.add_parser("queue", help="Manage the weekly queue")
    queue_parser.add_argument("--list", action="store_true", help="List all items in the weekly queue")
    queue_parser.add_argument("--activate", type=int, help="Activate a queue item by index")

    # Process Command
    process_parser = subparsers.add_parser("process", help="Execute pending tasks in the state")
    process_parser.add_argument("--id", type=int, help="Task ID to process. If omitted, processes all pending.")

    # Strategy Command
    strat_parser = subparsers.add_parser("strategy", help="Manage strategy and compile queue")
    strat_parser.add_argument("--compile", action="store_true")
    strat_parser.add_argument("--show", action="store_true")

    # Status Command
    subparsers.add_parser("status", help="Show current state tasks")

    args = parser.parse_args()
    
    # Initialize Dispatcher (handles State and Strategy managers internally)
    project_root = os.path.dirname(os.path.abspath(__file__))
    dispatcher = TaskDispatcher(project_root)

    if args.command == "render":
        config = RenderConfig(
            audio_path=args.audio,
            image_path=args.image,
            output_path=args.output,
            project_tag=args.tag
        )
        print(f"Starting render: {args.output}...")
        result = dispatcher.run_render(config)
        if result.success:
            print(f"SUCCESS: Video rendered to {result.output_path}")
        else:
            print(f"FAILED: {result.error_message}")

    elif args.command == "upload":
        config = UploadConfig(
            video_path=args.video,
            title=args.title,
            description=args.description,
            privacy=PrivacyEnum(args.privacy),
            publish_at=args.publish_at
        )
        print(f"Starting upload: {args.title}...")
        result = dispatcher.run_upload(config)
        if result.success:
            print(f"SUCCESS: Uploaded! Video ID: {result.output_path}")
        else:
            print(f"FAILED: {result.error_message}")

    elif args.command == "queue":
        if args.list:
            queue = dispatcher.strategy_manager.get_queue()
            print(f"{'IDX':<4} | {'TIME':<20} | {'ACTION':<15} | {'STATUS'}")
            print("-" * 55)
            for idx, item in enumerate(queue):
                print(f"{idx:<4} | {item['timestamp']:<20} | {item['action']:<15} | {item['status']}")
        
        elif args.activate is not None:
            task_id = dispatcher.activate_from_queue(args.activate)
            if task_id:
                print(f"Task #{task_id} activated. Run 'process --id {task_id}' to execute.")
            else:
                print("Failed to activate task. Check if index is valid and status is not 'scheduled'.")

    elif args.command == "process":
        if args.id:
            result = dispatcher.process_task(args.id)
            if result.success:
                print(f"Task #{args.id} completed.")
            else:
                print(f"Task #{args.id} failed: {result.error_message}")
        else:
            pending = dispatcher.state.get_pending_tasks()
            if not pending:
                print("No pending tasks.")
            for t in pending:
                print(f"Processing Task #{t.doc_id} ({t['type']})...")
                dispatcher.process_task(t.doc_id)

    elif args.command == "strategy":
        sm = dispatcher.strategy_manager
        if args.compile:
            sm.compile_queue_from_plan()
            print("Queue compiled from plan.")
        if args.show:
            print("STRATEGY:", json.dumps(sm.get_strategy(), indent=2))
            print("PLAN:", json.dumps(sm.get_plan(), indent=2))

    elif args.command == "status":
        tasks = dispatcher.state.get_tasks()
        if not tasks:
            print("No tasks in state.")
        else:
            print(f"{'ID':<4} | {'TYPE':<10} | {'STATUS':<15} | {'TARGET'}")
            print("-" * 60)
            for t in tasks:
                print(f"{t.doc_id:<4} | {t['type']:<10} | {t['status']:<15} | {t['target']}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
