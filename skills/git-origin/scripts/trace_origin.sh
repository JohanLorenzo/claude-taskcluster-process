#!/usr/bin/env bash

set -euo pipefail

error() {
    echo "ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $0 FILE[:LINE] [SEARCH_STRING]

Examples:
  $0 src/main.rs:42           # Trace specific line
  $0 src/main.rs "fn main"    # Find and trace line containing string
  $0 src/main.rs              # Show blame for file (use with caution)
EOF
    exit 1
}

[[ $# -eq 0 ]] && usage

INPUT="$1"
SEARCH_STRING="${2:-}"

if [[ "$INPUT" =~ ^(.+):([0-9]+)$ ]]; then
    FILE="${BASH_REMATCH[1]}"
    LINE="${BASH_REMATCH[2]}"
elif [[ -n "$SEARCH_STRING" ]]; then
    FILE="$INPUT"
    LINE=$(grep -n -F "$SEARCH_STRING" "$FILE" | head -1 | cut -d: -f1)
    [[ -z "$LINE" ]] && error "Search string not found: $SEARCH_STRING"
    echo "Found at line $LINE" >&2
else
    FILE="$INPUT"
    LINE=""
fi

[[ ! -f "$FILE" ]] && error "File not found: $FILE"

git rev-parse --git-dir &>/dev/null || error "Not in a git repository"

if [[ -z "$LINE" ]]; then
    echo "No line specified, showing full blame..." >&2
    git blame -w -M -C -C -C "$FILE"
    exit 0
fi

echo "Tracing line $LINE in $FILE..." >&2
echo

CURRENT_FILE="$FILE"
CURRENT_LINE="$LINE"
ORIGINAL_COMMIT=""
BUG_NUMBER=""
HISTORY=()

trace_line() {
    local file="$1"
    local line="$2"
    local deep="${3:-false}"

    local blame_flags="-w -M -C"
    if [[ "$deep" == "true" ]]; then
        blame_flags="-w -M -C -C -C"
        echo "Using deep copy detection (slow on large repos)..." >&2
    fi

    local blame_output
    blame_output=$(git blame $blame_flags -l --line-porcelain -L "$line,$line" "$file" 2>/dev/null || true)

    [[ -z "$blame_output" ]] && return 1

    local commit
    commit=$(echo "$blame_output" | head -1 | awk '{print $1}')

    [[ "$commit" == "0000000000000000000000000000000000000000" ]] && {
        echo "Line exists in uncommitted changes" >&2
        return 1
    }

    echo "$commit"
}

is_meaningful_change() {
    local commit="$1"
    local file="$2"
    local line_content="$3"

    local parent
    parent=$(git rev-parse "$commit^" 2>/dev/null || echo "")

    [[ -z "$parent" ]] && return 0

    local diff_output
    diff_output=$(git diff -w -U0 "$parent" "$commit" -- "$file" 2>/dev/null || echo "")

    if grep -qF -- "$line_content" <<< "$diff_output"; then
        return 0
    fi

    local file_existed_in_parent
    file_existed_in_parent=$(git ls-tree "$parent" -- "$file" 2>/dev/null || echo "")
    [[ -z "$file_existed_in_parent" ]] && return 0

    return 1
}

extract_bug_number() {
    local commit="$1"
    local message
    message=$(git log -1 --format=%s "$commit")

    if [[ "$message" =~ [Bb]ug[[:space:]=#]*([0-9]+) ]]; then
        echo "${BASH_REMATCH[1]}"
        return 0
    fi

    return 1
}

MAX_ITERATIONS=50
iteration=0

while [[ $iteration -lt $MAX_ITERATIONS ]]; do
    commit=$(trace_line "$CURRENT_FILE" "$CURRENT_LINE" "false")

    [[ -z "$commit" ]] && break

    HISTORY+=("$commit")

    BUG_NUMBER=$(extract_bug_number "$commit" || echo "")

    if [[ -n "$BUG_NUMBER" ]]; then
        ORIGINAL_COMMIT="$commit"
        echo "Found commit with bug number, stopping trace" >&2
        break
    fi

    line_content=$(git show "$commit:$CURRENT_FILE" 2>/dev/null | sed -n "${CURRENT_LINE}p" || echo "")

    if is_meaningful_change "$commit" "$CURRENT_FILE" "$line_content"; then
        ORIGINAL_COMMIT="$commit"
        echo "Found meaningful change, stopping trace" >&2
        break
    fi

    parent=$(git rev-parse "$commit^" 2>/dev/null || echo "")
    [[ -z "$parent" ]] && {
        ORIGINAL_COMMIT="$commit"
        echo "Reached root commit" >&2
        break
    }

    prev_file=$(git log --pretty="" --name-only --diff-filter=R --follow "$commit^..$commit" -- "$CURRENT_FILE" | head -1 || echo "")
    if [[ -n "$prev_file" && "$prev_file" != "$CURRENT_FILE" ]]; then
        echo "File was renamed from: $prev_file" >&2
        CURRENT_FILE="$prev_file"
    fi

    iteration=$((iteration + 1))
done

[[ $iteration -eq $MAX_ITERATIONS ]] && echo "WARNING: Reached maximum trace depth" >&2

if [[ -z "$ORIGINAL_COMMIT" ]]; then
    error "Could not trace line origin"
fi

echo "=== ORIGINAL COMMIT ==="
git log -1 --format="Commit:  %H%nAuthor:  %an <%ae>%nDate:    %ad%nSubject: %s%n" "$ORIGINAL_COMMIT"

[[ -n "$BUG_NUMBER" ]] && echo "Bug Number: $BUG_NUMBER" || echo "Bug Number: Not found in commit message"

echo
echo "=== FILE HISTORY ==="
git log --follow --format="%h %ad %s" --date=short "$ORIGINAL_COMMIT" -- "$FILE" | head -10

echo
echo "=== BLAME CHAIN ==="
echo "Traced through ${#HISTORY[@]} commit(s):"
for c in "${HISTORY[@]}"; do
    git log -1 --format="%h %ad %s" --date=short "$c"
done
