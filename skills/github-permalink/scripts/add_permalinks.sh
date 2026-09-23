#!/usr/bin/env bash

set -euo pipefail

error() {
    echo "ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $0 FILE

Convert local file:line references to GitHub permalinks using main/master SHA.

Example:
  $0 document.md
EOF
    exit 1
}

[[ $# -eq 0 ]] && usage

FILE="$1"
[[ ! -f "$FILE" ]] && error "File not found: $FILE"

git rev-parse --git-dir &>/dev/null || error "Not in a git repository"

command -v gh &>/dev/null || error "gh CLI not installed"

echo "Detecting remote..." >&2
if git remote | grep -q "^upstream$"; then
    REMOTE="upstream"
    echo "Using upstream remote" >&2
else
    REMOTE="origin"
    echo "Using origin remote (upstream not found)" >&2
fi

echo "Detecting default branch..." >&2
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/$REMOTE/HEAD 2>/dev/null | sed "s@^refs/remotes/$REMOTE/@@" || echo "")

if [[ -z "$DEFAULT_BRANCH" ]]; then
    if git show-ref --verify --quiet refs/remotes/$REMOTE/main; then
        DEFAULT_BRANCH="main"
    elif git show-ref --verify --quiet refs/remotes/$REMOTE/master; then
        DEFAULT_BRANCH="master"
    else
        error "Could not detect default branch (main or master)"
    fi
fi

echo "Default branch: $DEFAULT_BRANCH" >&2

CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH" >&2

echo "Fetching latest from $REMOTE..." >&2
git fetch $REMOTE "$DEFAULT_BRANCH" --quiet || error "Failed to fetch $DEFAULT_BRANCH"

echo "Getting SHA from $REMOTE/$DEFAULT_BRANCH..." >&2
SHA=$(git rev-parse "$REMOTE/$DEFAULT_BRANCH")
echo "SHA: $SHA" >&2

echo "Getting repository info..." >&2
REPO_INFO=$(gh repo view --json owner,name)
OWNER=$(echo "$REPO_INFO" | grep -o '"owner"[[:space:]]*:[[:space:]]*{[^}]*"login"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"login"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
REPO=$(echo "$REPO_INFO" | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)

[[ -z "$OWNER" || -z "$REPO" ]] && error "Could not get repository owner/name"

echo "Repository: $OWNER/$REPO" >&2

TEMP_FILE=$(mktemp)
cp "$FILE" "$TEMP_FILE"

COUNT=0

while IFS= read -r line; do
    modified_line="$line"

    while [[ "$modified_line" =~ ([a-zA-Z0-9_/.-]+):([0-9]+) ]]; do
        file_ref="${BASH_REMATCH[1]}"
        line_num="${BASH_REMATCH[2]}"

        if [[ -f "$file_ref" ]]; then
            permalink="https://github.com/$OWNER/$REPO/blob/$SHA/$file_ref#L$line_num"
            modified_line="${modified_line//${file_ref}:${line_num}/$permalink}"
            COUNT=$((COUNT + 1))
        else
            break
        fi
    done

    echo "$modified_line"
done < "$TEMP_FILE" > "$FILE"

rm "$TEMP_FILE"

echo "Converted $COUNT file reference(s) to permalinks in $FILE" >&2
