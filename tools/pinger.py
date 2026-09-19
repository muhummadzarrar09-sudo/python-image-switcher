#!/usr/bin/env python3
"""
Image Switcher - Branches Pinger V2.5
Checks GitHub for latest updates on main + ALL branches + releases vs local
Now checks branches latest ones, not just main only!

Usage:
  python tools/pinger.py
  python tools/pinger.py --branches
  python tools/pinger.py --watch --interval 60
  python tools/pinger.py --json
  python tools/pinger.py --notify (Windows toast if available)

This is the pinger you asked for - now branches aware!
"""

import argparse
import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = "muhummadzarrar09-sudo/python-image-switcher"
API_MAIN = f"https://api.github.com/repos/{REPO}/commits/main"
API_BRANCHES = f"https://api.github.com/repos/{REPO}/branches"
API_RELEASES = f"https://api.github.com/repos/{REPO}/releases/latest"
API_COMMITS = f"https://api.github.com/repos/{REPO}/commits?sha=main&per_page=5"

def run_git(args, cwd=None):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd or Path(__file__).parent.parent,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

def fetch_json(url):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "ImageSwitcher-Pinger/2.5", "Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_local_info():
    root = Path(__file__).parent.parent
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root) or "unknown"
    local_sha = run_git(["rev-parse", "HEAD"], cwd=root) or "unknown"
    local_main = run_git(["rev-parse", "origin/main"], cwd=root)
    if not local_main:
        run_git(["fetch", "origin", "main"], cwd=root)
        local_main = run_git(["rev-parse", "origin/main"], cwd=root)
    local_branches = run_git(["branch", "-a"], cwd=root) or ""
    return {
        "branch": branch,
        "local_sha": local_sha,
        "local_main_sha": local_main,
        "repo_root": str(root),
        "is_git": (root / ".git").exists(),
        "local_branches": local_branches
    }

def check_updates(json_mode=False, branches_mode=False):
    print("🔔 Image Switcher - Branches Pinger V2.5")
    print("="*60)
    local = get_local_info()
    print(f"📁 Local repo: {local['repo_root']}")
    print(f"🌿 Current Branch: {local['branch']}")
    print(f"🔖 Local HEAD: {local['local_sha'][:12]}")
    if local['local_main_sha']:
        print(f"📌 origin/main: {local['local_main_sha'][:12]}")

    # Fetch all branches - NEW V2.5
    print("\n🌿 Checking ALL branches (not just main)...")
    branches_data = fetch_json(API_BRANCHES)
    arena_branches = []
    if isinstance(branches_data, list):
        print(f"📋 Found {len(branches_data)} remote branches:")
        for b in branches_data[:15]:
            name = b.get("name", "")
            sha = b.get("commit", {}).get("sha", "")[:12]
            marker = "👉" if name==local['branch'] else "  "
            print(f"   {marker} {name:40s} {sha}")
            if "arena" in name:
                arena_branches.append({"name": name, "sha": b.get("commit", {}).get("sha", ""), "short": sha})
    else:
        print(f"❌ Failed to fetch branches: {branches_data.get('error')}")

    # Find latest arena branch by commit date
    latest_arena = None
    latest_date = ""
    if arena_branches:
        print(f"\n🔍 Checking {len(arena_branches)} arena branches for latest...")
        for br in arena_branches[:5]:
            try:
                commit_data = fetch_json(f"https://api.github.com/repos/{REPO}/commits/{br['name']}")
                date = commit_data.get("commit", {}).get("committer", {}).get("date", "")
                msg = commit_data.get("commit", {}).get("message", "")[:60]
                print(f"   {br['name'][:40]:40s} {br['short']} | {date[:10]} | {msg}")
                if date > latest_date:
                    latest_date = date
                    latest_arena = br
                    latest_arena["date"] = date
                    latest_arena["message"] = msg
            except Exception as e:
                print(f"   {br['name']} - error {e}")

        if latest_arena:
            print(f"\n🏆 Latest arena branch: {latest_arena['name']}")
            print(f"   SHA: {latest_arena['short']} | Date: {latest_arena.get('date','')}")
            print(f"   Msg: {latest_arena.get('message','')}")
            if local['branch'] != latest_arena['name']:
                print(f"\n🚨 UPDATE AVAILABLE - newer branch {latest_arena['name']} exists!")
                print(f"   You are on: {local['branch']} ({local['local_sha'][:12]})")
                print(f"   Latest is:  {latest_arena['name']} ({latest_arena['short']})")
                print(f"\n   Run: git fetch origin && git checkout {latest_arena['name']}")

    # Fetch remote main
    print("\n🌐 Checking GitHub main...")
    remote_main = fetch_json(API_MAIN)
    if "error" in remote_main and "sha" not in remote_main:
        print(f"❌ Failed to fetch main: {remote_main.get('error')}")
    else:
        remote_sha = remote_main.get("sha", "unknown")
        remote_msg = remote_main.get("commit", {}).get("message", "")[:80]
        remote_date = remote_main.get("commit", {}).get("committer", {}).get("date", "")
        print(f"☁️  Remote main: {remote_sha[:12]}")
        print(f"💬 {remote_msg}")
        print(f"📅 {remote_date}")

        if local['local_sha'] and remote_sha != "unknown":
            if local['local_sha'] == remote_sha:
                print("\n✅ You are UP TO DATE with main!")
            elif local['local_main_sha'] == remote_sha:
                print(f"\n⚠️  Your branch '{local['branch']}' is behind main.")
            else:
                print("\n🚨 UPDATE AVAILABLE - main has new commits!")
                print(f"   Local main:  {local['local_main_sha'][:12] if local['local_main_sha'] else 'unknown'}")
                print(f"   Remote main: {remote_sha[:12]}")
                print("\n   Run: git fetch origin && git merge origin/main")

    # Check releases
    print("\n🏷️  Checking latest release...")
    rel = fetch_json(API_RELEASES)
    if "tag_name" in rel:
        print(f"🎉 Latest release: {rel['tag_name']} - {rel.get('name','')}")
        print(f"📅 Published: {rel.get('published_at','')}")
        print(f"🔗 {rel.get('html_url','')}")
    else:
        print("ℹ️  No releases yet (expected)")

    # Recent commits
    print("\n📜 Recent main commits:")
    commits = fetch_json(API_COMMITS)
    if isinstance(commits, list):
        for c in commits[:5]:
            sha = c.get("sha","")[:8]
            msg = c.get("commit",{}).get("message","").split("\n")[0][:60]
            date = c.get("commit",{}).get("committer",{}).get("date","")[:10]
            print(f"   {sha} | {date} | {msg}")

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "local": local,
        "remote_main": remote_main if "sha" in remote_main else None,
        "release": rel if "tag_name" in rel else None,
        "branches": branches_data if isinstance(branches_data, list) else [],
        "latest_arena": latest_arena,
        "up_to_date": local['local_sha'] == remote_main.get("sha") if "sha" in remote_main else None
    }

    if json_mode:
        print("\n--- JSON ---")
        print(json.dumps(result, indent=2))

    return result

def watch_loop(interval):
    print(f"👀 Watching main + branches every {interval}s - Ctrl+C to stop\n")
    last_sha = None
    last_branch_sha = None
    while True:
        try:
            data = fetch_json(API_MAIN)
            sha = data.get("sha")
            branches = fetch_json(API_BRANCHES)
            latest_arena_sha = None
            latest_arena_name = None
            if isinstance(branches, list):
                arena = [b for b in branches if "arena" in b.get("name","")]
                if arena:
                    latest_arena_sha = arena[0].get("commit",{}).get("sha","")
                    latest_arena_name = arena[0].get("name","")

            if sha and sha != last_sha:
                if last_sha is not None:
                    print(f"\n🔔🔔🔔 NEW UPDATE ON MAIN! {sha[:12]}")
                    print(f"💬 {data.get('commit',{}).get('message','')[:100]}")
                else:
                    print(f"📌 Current main: {sha[:12]}")
                last_sha = sha

            if latest_arena_sha and latest_arena_sha != last_branch_sha:
                if last_branch_sha is not None:
                    print(f"\n🔔 NEW UPDATE ON BRANCH {latest_arena_name}! {latest_arena_sha[:12]}")
                last_branch_sha = latest_arena_sha
            else:
                print(".", end="", flush=True)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Stopped watching")
            break
        except Exception as e:
            print(f"\n⚠️  Error: {e}")
            time.sleep(interval)

def main():
    p = argparse.ArgumentParser(description="Image Switcher Branches Pinger V2.5")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--branches", action="store_true", help="Show all branches detailed")
    p.add_argument("--watch", action="store_true", help="Watch mode - ping continuously")
    p.add_argument("--interval", type=int, default=60, help="Watch interval seconds")
    p.add_argument("--notify", action="store_true", help="Show Windows notification if update available")
    args = p.parse_args()

    if args.watch:
        watch_loop(args.interval)
    else:
        result = check_updates(json_mode=args.json, branches_mode=args.branches)
        if args.notify and result.get("up_to_date") is False:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "Update available! Check branches + main.", "Image Switcher", 0x40)
            except:
                pass
        sys.exit(0 if result.get("up_to_date") else 1)

if __name__ == "__main__":
    main()
