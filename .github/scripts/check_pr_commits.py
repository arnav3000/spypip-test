#!/usr/bin/env python3
"""
check_pr_commits.py

Usage (in GitHub Actions):
  env:
    GITHUB_REPOSITORY: owner/repo
    GITHUB_EVENT_PATH: path to event json (built-in)
    GITHUB_TOKEN: token
  python .github/scripts/check_pr_commits.py

This script:
- If running on a pull_request event, fetches the commits of the PR and ensures each commit message contains a JIRA key.
- If running on push, checks commits in push payload similarly (optional).
"""
import os
import re
import sys
import json
import requests

JIRA_RE = re.compile(r'([A-Za-z][A-Za-z0-9]+-\d+)', re.IGNORECASE)

def get_event():
    evp = os.environ.get("GITHUB_EVENT_PATH")
    if not evp or not os.path.exists(evp):
        print("GITHUB_EVENT_PATH not found", file=sys.stderr)
        sys.exit(1)
    with open(evp, 'r', encoding='utf-8') as f:
        return json.load(f)

def github_api_get(url, token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN missing", file=sys.stderr)
        sys.exit(2)

    event = get_event()
    if "pull_request" in event:
        pr = event["pull_request"]
        repo = event["repository"]["full_name"]
        pr_number = pr["number"]
        commits_url = pr["commits_url"]
        commits = github_api_get(commits_url, token)
        # Extract JIRA key candidate from PR title
        pr_title = pr.get("title", "")
        prs = JIRA_RE.search(pr_title)
        header_jira = prs.group(1).upper() if prs else None
        errs = []
        for c in commits:
            msg = c.get("commit", {}).get("message", "")
            m = JIRA_RE.search(msg)
            if not m:
                errs.append(f"Commit {c.get('sha')[:7]} missing JIRA key in message.")
            else:
                # optional: ensure commit JIRA equals PR JIRA if PR contains one
                if header_jira and m.group(1).upper() != header_jira.upper():
                    errs.append(f"Commit {c.get('sha')[:7]} JIRA {m.group(1)} does not match PR JIRA {header_jira}.")
        if errs:
            print("Commit JIRA checks failed:")
            for e in errs:
                print(" -", e)
            sys.exit(1)
        print("All commits reference JIRA key.")
        sys.exit(0)
    else:
        print("Event is not pull_request. Skipping commit JIRA checks.")
        sys.exit(0)

if __name__ == "__main__":
    main()
