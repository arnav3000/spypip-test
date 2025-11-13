#!/usr/bin/env python3
"""
validate_patch.py

Usage:
  python validate_patch.py path/to/patch1.patch [path/to/patch2.patch ...]

If no args given, scans the "patches/" directory for *.patch and *.diff files.

Exit code 0 on success, non-zero on validation failures.
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

JIRA_RE = re.compile(r"([A-Za-z][A-Za-z0-9]+-\d+)")
REQUIRED_KEYS = ["JIRA", "Upstream", "Title", "Author", "Date", "Description"]

def parse_header(lines: List[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    Parse the header until the first blank line followed by a line that looks like a diff (starts with diff/+++/---/@@)
    Returns (fields, remaining_lines)
    """
    fields = {}
    desc_lines = []
    i = 0
    # skip leading comments/pound-lines but accept header keys anywhere at top
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if line.strip() == "":
            # blank line - but continue scanning until we hit diff lines
            i += 1
            # if next lines start with diff, break
            if i < len(lines) and re.match(r'^(diff |\+\+\+ |--- |@@ )', lines[i]):
                break
            continue
        # header keys
        m = re.match(r'^([A-Za-z]+):\s*(.*)$', line)
        if m:
            key, value = m.group(1), m.group(2)
            key = key.strip()
            if key == "Description":
                # collect indented following lines as description until blank or diff
                j = i + 1
                if value:
                    desc_lines.append(value)
                while j < len(lines):
                    ln = lines[j]
                    if re.match(r'^(diff |\+\+\+ |--- |@@ )', ln) or ln.strip() == "":
                        break
                    desc_lines.append(ln.rstrip("\n"))
                    j += 1
                fields["Description"] = "\n".join([l.strip() for l in desc_lines]).strip()
                i = j
                continue
            else:
                fields[key] = value.strip()
        else:
            # ignore comments and other lines until diff
            if re.match(r'^(diff |\+\+\+ |--- |@@ )', line):
                break
        i += 1
    remaining = lines[i:]
    return fields, remaining

def validate_patch_file(path: Path) -> List[str]:
    errors = []
    with path.open('r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    if not lines:
        errors.append("Empty file")
        return errors
    fields, _ = parse_header(lines)
    # check required keys
    for key in REQUIRED_KEYS:
        if key not in fields or not fields[key].strip():
            errors.append(f"Missing or empty required header field: {key}")
    # JIRA validation
    jira = fields.get("JIRA", "")
    if jira:
        if not JIRA_RE.search(jira):
            errors.append(f"JIRA field does not contain a valid ticket key: '{jira}'")
    # Upstream
    upstream = fields.get("Upstream", "").lower()
    if upstream not in ("yes", "no"):
        errors.append(f"Upstream field must be 'yes' or 'no', got: '{fields.get('Upstream')}'")
    # Description length
    desc = fields.get("Description", "")
    if len(desc.strip()) < 20:
        errors.append("Description must be at least 20 characters and explain the rationale and upstream status.")
    return errors

def main(argv):
    if len(argv) > 1:
        files = [Path(p) for p in argv[1:]]
    else:
        p = Path("patches")
        if not p.exists():
            print("No patches/ folder found and no paths given.", file=sys.stderr)
            return 1
        files = list(p.glob("*.patch")) + list(p.glob("*.diff"))
    if not files:
        print("No patch files found.", file=sys.stderr)
        return 1

    overall_failed = False
    for f in files:
        print(f"Validating {f} ...")
        errs = validate_patch_file(f)
        if errs:
            overall_failed = True
            print(f"  ✖ {len(errs)} error(s) in {f}:")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"  ✓ {f} OK")
    return 1 if overall_failed else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
