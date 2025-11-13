# Patch header - REQUIRED FORMAT
#
# Place this header at the very top of the patch file before any git diff/patch content.
# Fields are case-sensitive keys followed by ":" and the value on the same line.
#
# Example:
# JIRA: PROJECT-123
# Upstream: no
# Title: Fix packaging for internal deployment
# Author: Jane Developer <jane@example.com>
# Date: 2025-11-13
# Description:
#   Short paragraph explaining why this patch exists, what problem it solves,
#   and whether this has been proposed upstream. Must be at least 20 chars.
#
# Then a blank line and the patch (diff) content.
#
# Mandatory fields:
#   JIRA         -> a ticket id in the form ABC-123 (case-insensitive allowed, validated)
#   Upstream     -> "yes" or "no"
#   Title        -> Short summary
#   Author       -> Name and optional email
#   Date         -> ISO date recommended, free text allowed
#   Description  -> multi-line; must be present and non-trivial
#
# After the header, start your patch (git-format-patch or unified diff).
#
