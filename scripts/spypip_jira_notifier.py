#!/usr/bin/env python3
"""
spypip_jira_notifier.py

Detect packaging-related changes between two refs/tags in a GitHub repo and create Jira issues for them.

Requirements:
    pip install requests python-dotenv

Usage:
    export GITHUB_TOKEN=ghp_xxx
    export JIRA_BASE=https://yourcompany.atlassian.net
    export JIRA_USER=you@example.com
    export JIRA_API_TOKEN=atlassian_api_token
    python spypip_jira_notifier.py --repo owner/repo --base-tag v1.2.0 --head-tag v1.3.0 \
        --jira-project PROJ --jira-issuetype Bug --dry-run

Notes:
    - This script calls the GitHub compare API to fetch aggregated file changes.
    - Jira API uses basic auth with email:api_token (Atlassian Cloud).
"""
import os
import sys
import argparse
import requests
import fnmatch
import base64
import textwrap
from typing import List, Dict

DEFAULT_PATTERNS = [
    "requirements.txt",
    "requirements/*.txt",
    "pyproject.toml",
    "setup.py",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "environment.yml",
    "Dockerfile",
    "Dockerfile.*",
    "*.in",
    "setup.cfg",
    "MANIFEST.in",
]

GITHUB_API = "https://api.github.com"

def get_github_headers(token: str):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

def compare_refs(owner_repo: str, base: str, head: str, token: str) -> Dict:
    owner, repo = owner_repo.split("/")
    url = f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base}...{head}"
    r = requests.get(url, headers=get_github_headers(token))
    r.raise_for_status()
    return r.json()

def commit_details(owner_repo: str, sha: str, token: str) -> Dict:
    owner, repo = owner_repo.split("/")
    url = f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}"
    r = requests.get(url, headers=get_github_headers(token))
    r.raise_for_status()
    return r.json()

def matches_patterns(path: str, patterns: List[str]) -> bool:
    for p in patterns:
        if fnmatch.fnmatch(path, p):
            return True
    return False

def find_packaging_commits(compare_json: Dict, patterns: List[str]) -> List[Dict]:
    """
    Use the 'files' array from the compare endpoint if available (overall diff),
    otherwise fall back to checking each commit's files.
    Returns a list of dicts: { 'sha', 'html_url', 'author', 'commit_message', 'files_changed': [ ... ] }
    """
    owner_repo = compare_json.get("url", "")
    commits = compare_json.get("commits", [])
    results = []

    # Try to use compare_json['files'] if available (some compare responses include files aggregated)
    # But to be robust, query each commit for its files
    for c in commits:
        sha = c.get("sha")
        # fetch commit details to get files and patches
        try:
            detail = commit_details_from_compare(c)
        except Exception:
            detail = None

        # commit_details_from_compare returns a dict with files if commit payload includes them,
        # otherwise we call the GitHub API commit endpoint.
        if detail and "files" in detail:
            files = detail["files"]
        else:
            # fallback - some compare JSON entries may include 'files' already attached; if not, use commit endpoint
            files = []
            if sha:
                # The caller could pass a token and do commit_details; but here we'll set files empty if not present
                pass

        matched_files = []
        for f in files:
            filename = f.get("filename") or f.get("file") or ""
            if matches_patterns(filename, patterns):
                matched_files.append({
                    "filename": filename,
                    "status": f.get("status"),
                    "patch": f.get("patch")
                })

        if matched_files:
            results.append({
                "sha": sha,
                "html_url": c.get("html_url") or (compare_json.get("html_url") + f"/commit/{sha}" if compare_json.get("html_url") else None),
                "author": c.get("commit", {}).get("author", {}).get("name"),
                "commit_message": c.get("commit", {}).get("message"),
                "files_changed": matched_files,
            })

    return results

def commit_details_from_compare(commit_entry: Dict) -> Dict:
    """
    Some GitHub compare responses embed a commit payload with 'files' already.
    If commit_entry itself has 'files', return it; else return None (caller can fetch via API).
    """
    if "files" in commit_entry:
        return commit_entry
    # else None -> caller should call commit endpoint if needed
    return None

def create_jira_issue(jira_base: str, jira_user: str, jira_api_token: str,
                      project_key: str, issue_type: str, summary: str,
                      description: str, assignee: str = None, labels: List[str] = None,
                      dry_run: bool = True) -> Dict:
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
    }
    if labels:
        payload["fields"]["labels"] = labels
    if assignee:
        payload["fields"]["assignee"] = {"name": assignee}

    if dry_run:
        print("[DRY-RUN] Would create Jira issue with payload:")
        print(payload)
        return {"mock": True, "payload": payload}

    url = jira_base.rstrip("/") + "/rest/api/2/issue"
    auth = (jira_user, jira_api_token)
    headers = {"Content-Type": "application/json"}
    r = requests.post(url, auth=auth, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()

def build_issue_description(repo: str, base: str, head: str, commit_info: Dict) -> str:
    lines = []
    lines.append(f"h3. Packaging-related changes detected in repo *{repo}* between {base} → {head}")
    lines.append("")
    lines.append(f"*Commit:* [{commit_info.get('sha')}|{commit_info.get('html_url')}]")
    lines.append(f"*Author:* {commit_info.get('author')}")
    lines.append(f"*Message:* {commit_info.get('commit_message')}")
    lines.append("")
    lines.append("Files changed:")
    for f in commit_info.get("files_changed", []):
        lines.append(f"* `{f['filename']}` — {f.get('status')}")
        if f.get("patch"):
            # Jira markup for code block
            patch = textwrap.indent(f["patch"], "    ")
            lines.append("{code}")
            lines.append(f["patch"])
            lines.append("{code}")
    lines.append("")
    lines.append("Please investigate whether these packaging changes require release-note, CI, or security review.")
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser(description="Detect packaging changes and create Jira issues.")
    p.add_argument("--repo", required=True, help="owner/repo (e.g. psf/requests)")
    p.add_argument("--base-tag", required=True, dest="base", help="base ref (tag/sha)")
    p.add_argument("--head-tag", required=True, dest="head", help="head ref (tag/sha)")
    p.add_argument("--patterns", nargs="*", default=DEFAULT_PATTERNS, help="file patterns to match")
    p.add_argument("--dry-run", action="store_true", help="do not create Jira issues, just print payloads")
    p.add_argument("--jira-project", required=True, help="Jira project key")
    p.add_argument("--jira-issuetype", default="Bug", help="Jira issue type (default: Bug)")
    p.add_argument("--jira-assignee", default=None, help="Assignee username (optional)")
    p.add_argument("--jira-labels", nargs="*", default=None, help="Labels to add on created Jira issues")
    args = p.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")
    jira_base = os.environ.get("JIRA_BASE")
    jira_user = os.environ.get("JIRA_USER")
    jira_api_token = os.environ.get("JIRA_API_TOKEN")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(2)
    if not jira_base or not jira_user or not jira_api_token:
        print("Error: JIRA_BASE, JIRA_USER and JIRA_API_TOKEN environment variables are required.", file=sys.stderr)
        sys.exit(2)

    print(f"Comparing {args.repo}: {args.base} -> {args.head} ...")
    compare_json = compare_refs(args.repo, args.base, args.head, github_token)

    # attempt to use aggregated 'files' if present (GitHub compare may provide them)
    packaging_commits = []
    # First try to get aggregated files from compare_json (some repos/compare calls include 'files')
    if "files" in compare_json and compare_json["files"]:
        # if aggregated files present, map files -> commits is harder, so instead fallback to scanning commits individually
        pass

    # We'll inspect each commit entry for packaging files by fetching commit details.
    for c in compare_json.get("commits", []):
        sha = c.get("sha")
        commit_detail = None
        try:
            commit_detail = commit_details(args.repo, sha, github_token)
        except Exception as e:
            print(f"Warning: failed to fetch commit {sha}: {e}", file=sys.stderr)
            continue

        files = commit_detail.get("files", [])
        matched = []
        for f in files:
            filename = f.get("filename", "")
            if matches_patterns(filename, args.patterns):
                matched.append({
                    "filename": filename,
                    "status": f.get("status"),
                    "patch": f.get("patch")
                })
        if matched:
            packaging_commits.append({
                "sha": sha,
                "html_url": commit_detail.get("html_url"),
                "author": commit_detail.get("commit", {}).get("author", {}).get("name"),
                "commit_message": commit_detail.get("commit", {}).get("message"),
                "files_changed": matched
            })

    if not packaging_commits:
        print("No packaging-related changes found between the specified refs.")
        return

    print(f"Found {len(packaging_commits)} commits touching packaging files.")
    for ci in packaging_commits:
        summary = f"[packaging] {args.repo} {ci['sha'][:7]} - {ci['commit_message'].splitlines()[0]}"
        description = build_issue_description(args.repo, args.base, args.head, ci)
        resp = create_jira_issue(
            jira_base=jira_base,
            jira_user=jira_user,
            jira_api_token=jira_api_token,
            project_key=args.jira_project,
            issue_type=args.jira_issuetype,
            summary=summary,
            description=description,
            assignee=args.jira_assignee,
            labels=args.jira_labels,
            dry_run=args.dry_run,
        )
        print("Created/Planned Jira issue:", resp.get("key") if isinstance(resp, dict) else resp)

if __name__ == "__main__":
    main()
