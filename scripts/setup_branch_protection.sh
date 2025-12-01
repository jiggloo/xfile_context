#!/bin/bash
# Copyright (c) 2025 Henru Wang
# All rights reserved.

# Setup branch protection rules for the main branch
#
# Usage:
#   ./scripts/setup_branch_protection.sh
#
# Prerequisites:
#   - gh CLI installed and authenticated (run: gh auth login)
#   - Repository admin permissions
#
# This script configures GitHub branch protection to enforce:
# - Pull request workflow (no direct commits)
# - Required approvals (at least 1)
# - Required status checks from CI workflows
# - Branches must be up-to-date before merging
# - Rules enforced for administrators

set -e

REPO="jiggloo/xfile_context"
BRANCH="main"

echo "Configuring branch protection for $REPO branch: $BRANCH"

# Configure branch protection using GitHub API
# Using --input to provide JSON payload with correct types
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/$REPO/branches/$BRANCH/protection" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Code Formatting",
      "Linting",
      "Type Checking",
      "Fast Unit Tests",
      "Test (Python 3.8)",
      "Test (Python 3.9)",
      "Test (Python 3.10)",
      "Test (Python 3.11)",
      "Test (Python 3.12)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF

echo ""
echo "✓ Branch protection rules configured successfully!"
echo ""
echo "Protection summary:"
echo "  - Pull requests required (no direct commits)"
echo "  - At least 1 approval required"
echo "  - Required status checks: 9 checks (formatting, linting, type checking, tests)"
echo "  - Branches must be up-to-date before merging"
echo "  - Rules enforced for administrators"
