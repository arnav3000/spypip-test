#!/usr/bin/env python3
"""
pr_jira_commentor.py

Usage:
  python pr_jira_commentor.py --pr-number 123 --repo owner/repo --dry-run

Environment:
  GITHUB_TOKEN required to post comments
  JIRA_* optionally required to create real Jira issues

This script:
- Reads PR info from GitHub
- If the PR or patch files lack a JIRA key, it posts a comment explaining how to fix.
- Optionally creates a Jira ticket (dry-run by default).
"""
import os
import re
import sys
import json
import argparse
import requests

JIRA_RE = re.compile(r'([A-Za-z][A-Za-z0-9]+-\d+)', re.IGNORECASE)

def gh_api(url, token, method="GET", json_body=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    if method == "GET":
        r = requests.get(url, headers=headers)
    elif method == "POST":
        headers["Content-Type"] = "application/json"
        r = requests.post(url, headers=headers, json=json_body)
    else:
        raise ValueError("Unsupported method")
    r.raise_for_status()
    return r.json()

def post_pr_comment(repo, pr_number, token, body):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    print("Posting PR comment...")
    return gh_api(url, token, method="POST", json_body={"body": body})

def create_jira_issue(summary, description, project_key, issue_type, dry_run=True):
    jira_base = os.getenv("JIRA_BASE")
    jira_user = os.getenv("JIRA_USER")
    jira_token = os.getenv("JIRA_API_TOKEN")
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type}
        }
    }
    if dry_run:
        print("[DRY-RUN] Jira payload:", payload)
        return {"mock": True}
    if not jira_base or not jira_user or not jira_token:
        raise RuntimeError("Missing JIRA credentials")
    url = jira_base.rstrip("/") + "/rest/api/3/issue"
    r = requests.post(url, auth=(jira_user, jira_token), json=payload, headers={"Content-Type": "application/json"})
    r.raise_for_status()
    return r.json()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pr-number", type=int, required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("GITHUB_TOKEN required", file=sys.stderr)
        sys.exit(2)

    pr_url = f"https://api.github.com/repos/{args.repo}/pulls/{args.pr_number}"
    pr = gh_api(pr_url, gh_token)
    pr_title = pr.get("title", "")
    pr_body = pr.get("body") or ""
    # look for JIRA in title or body
    m = JIRA_RE.search(pr_title) or JIRA_RE.search(pr_body)
    if m:
        print(f"PR already references JIRA: {m.group(1)}")
        sys.exit(0)

    # search patch files for JIRA
    files_url = pr.get("url") + "/files"
    files = gh_api(files_url, gh_token)
    jira_found = None
    for f in files:
        if f.get("filename","").startswith("patches/"):
            # fetch file raw contents
            raw_url = f.get("raw_url")
            r = requests.get(raw_url)
            if r.ok:
                mm = JIRA_RE.search(r.text)
                if mm:
                    jira_found = mm.group(1)
                    break

    if jira_found:
        body = f"Found JIRA {jira_found} in patch file — please include it in PR title for traceability.\n\nSuggested title: `{jira_found}: short summary`"
        post_pr_comment(args.repo, args.pr_number, gh_token, body)
        print("Comment posted about including JIRA in PR title.")
        sys.exit(0)

    # No JIRA found anywhere — post guidance and optionally create JIRA
    guidance = (
        "This PR does not reference a JIRA ticket and contains downstream-only patches. "
        "Please create a JIRA ticket and add the ticket key in the PR title and the patch header.\n\n"
        "Patch header template (place at top of patch file):\n\n"
        "```\nJIRA: <PROJECT-123>\nUpstream: no\nTitle: Short summary\nAuthor: Name <email>\nDate: YYYY-MM-DD\nDescription:\n  Explanation of why this patch is downstream-only and whether it has been proposed upstream.\n```\n"
    )
    post_pr_comment(args.repo, args.pr_number, gh_token, guidance)
    print("Posted guidance comment to PR.")

    if not args.dry_run:
        # create a placeholder Jira ticket (requires JIRA env vars)
        summary = f"Downstream-only patches in PR #{args.pr_number}: please triage"
        description = f"Automatic ticket created for PR #{args.pr_number} in {args.repo}.\n\nPR url: {pr.get('html_url')}\n\nPlease update PR and patch files to include ticket key."
        try:
            resp = create_jira_issue(summary, description, project_key="ENG", issue_type="Task", dry_run=False)
            post_pr_comment(args.repo, args.pr_number, gh_token, f"Created Jira ticket {resp.get('key')}. Please include it in PR title and patch headers.")
        except Exception as ex:
            print("Failed to create Jira issue:", ex)

if __name__ == "__main__":
    main()
