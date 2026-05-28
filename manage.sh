#!/bin/bash

# Configuration
SESSION_NAME="mmpy"
PROJECT_DIR="/home/dave/.openclaw/workspace/projects/beat-manager"
PYTHON_VENV="$PROJECT_DIR/venv/bin/activate"

# Function to check if session exists
session_exists() {
    tmux has-session -t "$SESSION_NAME" 2>/dev/null
}

# Function to update SSH environment inside tmux
update_ssh_env() {
    if [ -n "$SSH_CLIENT" ]; then
        tmux set-environment -t "$SESSION_NAME" SSH_CLIENT "$SSH_CLIENT"
        # We also write it to a file the TUI can poll, since os.environ is static
        echo "$SSH_CLIENT" > "$PROJECT_DIR/.ssh_client_env"
    fi
}

case "$1" in
    start)
        if session_exists; then
            echo "Session '$SESSION_NAME' is already running. Use '$0 attach' to view."
        else
            echo "Starting Beat Manager in tmux session: $SESSION_NAME..."
            tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_DIR"
            update_ssh_env
            tmux send-keys -t "$SESSION_NAME" "source $PYTHON_VENV" C-m
            tmux send-keys -t "$SESSION_NAME" "python3 tui.py" C-m
            echo "Started. Use '$0 attach' to join."
        fi
        ;;
    attach|"" ) # Default action if no arg or 'attach'
        if ! session_exists; then
            $0 start
            sleep 1
        fi
        update_ssh_env
        tmux attach-session -t "$SESSION_NAME"
        ;;
    stop)
        if session_exists; then
            echo "Stopping '$SESSION_NAME'..."
            tmux kill-session -t "$SESSION_NAME"
            echo "Stopped."
        else
            echo "Session '$SESSION_NAME' is not running."
        fi
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    status)
        if session_exists; then
            echo "Beat Manager is RUNNING (tmux session: $SESSION_NAME)"
        else
            echo "Beat Manager is STOPPED"
        fi
        ;;
    *)
        echo "Usage: $0 {start|attach|stop|restart|status}"
        exit 1
        ;;
esac
