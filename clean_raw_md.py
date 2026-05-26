import os
import yaml
import re

md_dir = "assets/library/md"

def clean_raw_md():
    count = 0
    for f in os.listdir(md_dir):
        if not f.endswith(".md") or f.endswith("_notes.md"):
            continue
        path = os.path.join(md_dir, f)
        
        with open(path, "r") as mf:
            content = mf.read()
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if match:
                try:
                    meta = yaml.safe_load(match.group(1)) or {}
                    if str(meta.get("type", "")).lower() == "raw":
                        os.remove(path)
                        count += 1
                except: pass
    print(f"Deleted {count} RAW md files.")

if __name__ == "__main__":
    clean_raw_md()
