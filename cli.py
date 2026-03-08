import argparse
import os
import sys
import json
import traceback
from state_manager import StateManager
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine
from strategy_manager import StrategyManager
from backend import Backend

def main():
    parser = argparse.ArgumentParser(description="Beat Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Render Command
    render_parser = subparsers.add_parser("render", help="Render a video from audio and image")
    render_parser.add_argument("--audio", required=True)
    render_parser.add_argument("--image", required=True)
    render_parser.add_argument("--output", default="output.mp4")

    # Upload Command
    upload_parser = subparsers.add_parser("upload", help="Upload a video to YouTube")
    upload_parser.add_argument("--video", required=True)
    upload_parser.add_argument("--title", required=True)
    upload_parser.add_argument("--description", default="")
    upload_parser.add_argument("--privacy", default="private")
    upload_parser.add_argument("--publish_at", help="Schedule time (ISO 8601)")

    # Queue Command
    queue_parser = subparsers.add_parser("queue", help="Manage the weekly queue")
    queue_parser.add_argument("--list", action="store_true", help="List all items in the weekly queue")
    queue_parser.add_argument("--activate", type=int, help="Activate a queue item by index")
    queue_parser.add_argument("--check", action="store_true", help="Perform machine-readable validation")

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
    state = StateManager()
    backend = Backend()

    if args.command == "render":
        task_id = state.add_task("RENDER", args.output, audio=args.audio, image=args.image)
        backend.process_task(task_id)

    elif args.command == "upload":
        task_id = state.add_task("UPLOAD", args.title, video=args.video, publish_at=args.publish_at)
        backend.process_task(task_id)

    elif args.command == "queue":
        if args.list:
            queue = StrategyManager().get_queue()
            print(f"{'IDX':<4} | {'TIME':<20} | {'ACTION':<15} | {'STATUS'}")
            print("-" * 55)
            for idx, item in enumerate(queue):
                print(f"{idx:<4} | {item['timestamp']:<20} | {item['action']:<15} | {item['status']}")
        
        elif args.check:
            issues = StrategyManager().validate_queue()
            print(json.dumps(issues, indent=2))

        elif args.activate is not None:
            task_id = backend.activate_from_queue(args.activate)
            if task_id:
                # Pre-flight check immediately after activation
                check = backend.pre_flight_check(task_id)
                if not check["ready"]:
                    print(f"Task #{task_id} activated but PRE-FLIGHT FAILED: {', '.join(check.get('errors', []))}")
                else:
                    print(f"Task #{task_id} activated and passed pre-flight. Run 'process --id {task_id}' to execute.")
            else:
                print("Failed to activate task. Check if index is valid and status is 'pending'.")

    elif args.command == "process":
        if args.id:
            backend.process_task(args.id)
        else:
            pending = state.get_pending_tasks()
            for t in pending:
                backend.process_task(t.doc_id)

    elif args.command == "strategy":
        sm = StrategyManager()
        if args.compile:
            sm.compile_queue_from_plan()
            print("Queue compiled from plan.")
        if args.show:
            print("STRATEGY:", json.dumps(sm.get_strategy(), indent=2))
            print("PLAN:", json.dumps(sm.get_plan(), indent=2))

    elif args.command == "status":
        tasks = state.get_tasks()
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
