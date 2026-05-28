import os
import subprocess
import logging

logger = logging.getLogger(__name__)

class RemoteEngine:
    """Handles remote file transfers between Server and Client (Mac)."""
    
    def __init__(self):
        self.mac_user = None
        self.mac_ip = None
        self._detect_client()

    def _detect_client(self):
        """Automatically detects the Mac's IP from the SSH_CLIENT environment variable or a local file."""
        ssh_client = os.environ.get('SSH_CLIENT')
        
        # Fallback to local file if environment is empty or to get updates from tmux re-attaches
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".ssh_client_env")
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r') as f:
                    file_val = f.read().strip()
                    if file_val:
                        ssh_client = file_val
            except: pass

        if ssh_client:
            parts = ssh_client.split()
            if len(parts) >= 1:
                self.mac_ip = parts[0]
                # Defaulting mac_user to the same as server user for now, 
                # can be overridden if needed.
                self.mac_user = os.environ.get('USER', 'dave')
                logger.info(f"Detected remote client at {self.mac_ip} (user: {self.mac_user})")
        else:
            self.mac_ip = None
            self.mac_user = None

    def refresh(self):
        """Re-scan for remote client."""
        self._detect_client()
        return self.is_available

    def push_to_mac(self, local_path, remote_dest="~/Downloads/"):
        """Pushes a file to the Mac using SCP."""
        if not self.mac_ip or not self.mac_user:
            return False, "No remote client detected. Are you connected via SSH?"
        
        filename = os.path.basename(local_path)
        dest = f"{self.mac_user}@{self.mac_ip}:{remote_dest}"
        
        try:
            # -q for quiet, -o BatchMode=yes to avoid hang on prompt
            # -r for recursive to support directories
            subprocess.run(["scp", "-r", "-q", "-o", "BatchMode=yes", local_path, dest], check=True)
            return True, f"Successfully pushed {filename} to Mac"
        except subprocess.CalledProcessError as e:
            return False, f"SCP failed: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error during push: {str(e)}"

    @property
    def is_available(self):
        return self.mac_ip is not None
