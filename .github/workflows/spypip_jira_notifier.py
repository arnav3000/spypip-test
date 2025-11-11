#!/usr/bin/env python3
import os
import subprocess
import json
import requests
import sys
import argparse


def run_cmd(cmd):
    """Run a shell command and return its output."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_changed_files(base, head):
    """Return list of changed files between two refs."""
    diff_cmd = ["git", "diff", "--name-only", f"{base}..{head}"]
    output = run_cmd(diff_cmd)
    return [line for line in output.splitlines() if line.strip()]


def get_commits(base, head):
    """Return commit messages between two refs."""
    log_cmd = ["git", "log", "--pretty=format:%h %s", f"{base}..{head}"]
    output = run_cmd(log_cmd)
    return [line.strip() for line in output.splitlines()]


def create_jira_issue(jira_base, jira_user, jira_token, project, issue_type, summary, description, dry_run=False):
    """Create or mock-create a Jira issue."""
    url = f"{jira_base}/rest/api/2/issue"
    payload = {
        "fields": {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
    }

    if dry_run:
        print(f"[DRY-RUN] Would create Jira issue: {json.dumps(payload, indent=2)}")
        return

    auth = (jira_user, jira_token)
    resp = requests.post(url, auth=auth, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Failed to create Jira issue: {resp.status_code} {resp.text}")
    else:
        key = resp.json().get("key", "?")
        print(f"Created Jira issue {key}")


def main():
    parser = argparse.ArgumentParser(description="Compare commits and create Jira issues")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base-tag", required=True)
    parser.add_argument("--head-tag", required=True)
    parser.add_argument("--jira-project", default="MOCK")
    parser.add_argument("--jira-issuetype", default="Bug")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"🔍 Comparing {args.repo}: {args.base_tag} → {args.head_tag}")

    changed_files = get_changed_files(args.base_tag, args.head_tag)
    commits = get_commits(args.base_tag, args.head_tag)

    if not changed_files:
        print("✅ No changes detected.")
        return

    print(f"📂 Changed files ({len(changed_files)}):")
    for f in changed_files:
        print("  -", f)

    print(f"📝 Commits ({len(commits)}):")
    for c in commits:
        print("  -", c)

    jira_base = os.getenv("JIRA_BASE", "")
    jira_user = os.getenv("JIRA_USER", "")
    jira_token = os.getenv("JIRA_API_TOKEN", "")

    # Create one issue per changed file (you can adjust this logic)
    for f in changed_files:
        summary = f"Change detected in {f}"
        description = "Commits:\n" + "\n".join(commits)
        create_jira_issue(
            jira_base,
            jira_user,
            jira_token,
            args.jira_project,
            args.jira_issuetype,
            summary,
            description,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
