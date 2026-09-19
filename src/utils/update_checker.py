"""
Update Checker V2.5 - Branches Aware
Checks GitHub main + ALL branches + releases and shows banner if update available
"""

import json
import threading
import urllib.request
from datetime import datetime

REPO = "muhummadzarrar09-sudo/python-image-switcher"
API_MAIN = f"https://api.github.com/repos/{REPO}/commits/main"
API_BRANCHES = f"https://api.github.com/repos/{REPO}/branches"
API_RELEASE = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSION_FILE = "pyproject.toml"

def get_local_version():
    try:
        import pathlib
        root = pathlib.Path(__file__).parent.parent.parent
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            import re
            m = re.search(r'version\s*=\s*"([^"]+)"', text)
            if m:
                return m.group(1)
    except:
        pass
    return "1.0.0"

def get_local_branch():
    try:
        import subprocess
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return "main"

def fetch_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "ImageSwitcher-App/2.5",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def check_for_updates_async(callback):
    """Run in background thread, callback(result_dict) - NOW CHECKS ALL BRANCHES"""
    def _run():
        local_ver = get_local_version()
        local_branch = get_local_branch()
        
        # Fetch main
        remote = fetch_json(API_MAIN)
        release = fetch_json(API_RELEASE)
        # Fetch all branches - NEW V2.5
        branches_data = fetch_json(API_BRANCHES)

        result = {
            "local_version": local_ver,
            "local_branch": local_branch,
            "checked_at": datetime.utcnow().isoformat(),
            "has_update": False,
            "remote_sha": remote.get("sha","")[:12] if "sha" in remote else None,
            "remote_message": remote.get("commit",{}).get("message","")[:120] if "commit" in remote else None,
            "release_tag": release.get("tag_name") if "tag_name" in release else None,
            "release_url": release.get("html_url") if "html_url" in release else None,
            "branches": [],
            "latest_branch": None,
            "branch_updates": []
        }

        # Process branches
        if isinstance(branches_data, list):
            for b in branches_data[:20]:  # Check up to 20 branches
                name = b.get("name", "")
                sha = b.get("commit", {}).get("sha", "")[:12]
                if name and sha:
                    result["branches"].append({"name": name, "sha": sha})
                    # Check if this is arena branch or feature branch with newer commits
                    if "arena" in name or "feature" in name or "dev" in name:
                        result["branch_updates"].append({"name": name, "sha": sha})
            
            # Find latest arena branch
            arena_branches = [br for br in result["branches"] if "arena" in br["name"]]
            if arena_branches:
                # Sort by name or assume last is latest - actually fetch commit date would be better
                # For now, get the one with latest commit by checking each
                latest = None
                latest_date = ""
                for br in arena_branches[:5]:
                    try:
                        commit_data = fetch_json(f"https://api.github.com/repos/{REPO}/commits/{br['name']}")
                        date = commit_data.get("commit", {}).get("committer", {}).get("date", "")
                        if date > latest_date:
                            latest_date = date
                            latest = br
                            latest["message"] = commit_data.get("commit", {}).get("message", "")[:80]
                            latest["date"] = date
                    except:
                        pass
                if latest:
                    result["latest_branch"] = latest
                    # If local is on arena branch but not latest, mark update
                    if local_branch in [b["name"] for b in arena_branches] and latest["name"] != local_branch:
                        result["has_update"] = True
                        result["update_type"] = "branch"
                        result["update_branch"] = latest["name"]

        # Simple heuristic: if release tag newer than local, or main commit recent
        if result["release_tag"]:
            try:
                rt = result["release_tag"].lstrip("v")
                if rt != local_ver:
                    result["has_update"] = True
                    result["update_type"] = "release"
            except:
                pass

        # Always show main activity if we fetched it
        if result["remote_sha"]:
            result["main_active"] = True

        # If latest arena branch exists and is different from local, prioritize it
        if result.get("latest_branch") and result["latest_branch"]["name"] != local_branch:
            if not result["has_update"]:
                result["has_update"] = True
                result["update_type"] = "branch"
                result["update_branch"] = result["latest_branch"]["name"]

        try:
            callback(result)
        except:
            pass

    threading.Thread(target=_run, daemon=True).start()

def check_branches_sync():
    """Check all branches for latest - for Tools tab"""
    def _fetch():
        branches = fetch_json(API_BRANCHES)
        if isinstance(branches, list):
            return [{"name": b.get("name"), "sha": b.get("commit", {}).get("sha", "")[:12]} for b in branches[:20]]
        return []
    return _fetch

