#!/usr/bin/env bash
# Merge upstream into SYNC_BRANCH: drop excluded paths, keep fork-owned paths,
# and settle remaining conflicts on the fork side so a PR can always open.
set -euo pipefail

: "${SYNC_BRANCH:?SYNC_BRANCH is required}"
: "${UPSTREAM_BRANCH:?UPSTREAM_BRANCH is required}"
DROP_PATHS="${DROP_PATHS:-}"
KEEP_PATHS="${KEEP_PATHS:-}"

notes="${RUNNER_TEMP:-/tmp}/sync-notes.md"
: > "$notes"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if ! git remote get-url upstream >/dev/null 2>&1; then
  git remote add upstream "${UPSTREAM_URL:-https://github.com/${UPSTREAM_REPO}.git}"
fi
git fetch --no-tags upstream "$UPSTREAM_BRANCH"
upstream="upstream/$UPSTREAM_BRANCH"

git switch -C "$SYNC_BRANCH"

count="$(git rev-list --count "HEAD..$upstream")"
{
  printf 'Sync `%s@%s`: **%s** new upstream commit(s).\n\n' \
    "${UPSTREAM_REPO:-upstream}" "$UPSTREAM_BRANCH" "$count"
  if [ "$count" -gt 0 ]; then
    printf '<details><summary>Upstream commits</summary>\n\n'
    git log -n 50 --format='- `%h` %s' "HEAD..$upstream"
    printf '\n</details>\n\n'
  fi
} > "$notes"

# A conflict here is expected; the fork rules below settle it.
git merge --no-commit --no-ff "$upstream" || true

if [ "$count" -gt 0 ] && ! git rev-parse -q --verify MERGE_HEAD >/dev/null; then
  echo "Merge of $upstream did not start; refusing to report success." >&2
  exit 1
fi

for path in $KEEP_PATHS; do
  if git cat-file -e "origin/main:$path" 2>/dev/null; then
    git checkout origin/main -- "$path"
  fi
done

for path in $DROP_PATHS; do
  git rm -r --cached --ignore-unmatch -- "$path" >/dev/null 2>&1 || true
  rm -rf -- "$path"
done

conflicts="$(git diff --name-only --diff-filter=U || true)"
if [ -n "$conflicts" ]; then
  {
    printf '### Conflicts kept on the fork side\n\n'
    printf 'Upstream changes to these files were not applied. Review them before merging.\n\n'
    while IFS= read -r file; do
      printf -- '- `%s`\n' "$file"
    done <<< "$conflicts"
    printf '\n'
  } >> "$notes"

  while IFS= read -r file; do
    if git cat-file -e "HEAD:$file" 2>/dev/null; then
      git checkout --ours -- "$file"
      git add -- "$file"
    else
      git rm -q -f -- "$file"
    fi
  done <<< "$conflicts"
fi

git add -A

# Upstream ships Windows binaries; the fork does not. Anything matching these
# extensions and still staged after the drop step is a path the list misses.
binaries="$(git diff --cached --name-only --diff-filter=AM |
  grep -Ei '\.(exe|dll|jar|zip|pak|node)$' || true)"
if [ -n "$binaries" ]; then
  {
    printf '### Binaries outside the drop list\n\n'
    printf 'Add these paths to DROP_PATHS or delete them on the fork side.\n\n'
    while IFS= read -r file; do
      printf -- '- `%s`\n' "$file"
    done <<< "$binaries"
    printf '\n'
  } >> "$notes"
  echo "Binaries left after the merge:" >&2
  echo "$binaries" >&2
  exit 1
fi

lfs_pointers="$(git grep --cached -lE '^version https://git-lfs\.github\.com/spec/v1' || true)"
if [ -n "$lfs_pointers" ]; then
  {
    printf '### LFS pointers are not allowed\n\n'
    while IFS= read -r file; do
      printf -- '- `%s`\n' "$file"
    done <<< "$lfs_pointers"
    printf '\nFetch the LFS content or add these paths to the drop list.\n'
  } >> "$notes"
  echo "LFS pointers left after the merge:" >&2
  echo "$lfs_pointers" >&2
  exit 1
fi

if git diff --cached --quiet; then
  git merge --abort >/dev/null 2>&1 || true
  printf 'Nothing to merge: the fork already has every upstream change.\n' >> "$notes"
  echo "changed=false" >> "${GITHUB_OUTPUT:-/dev/null}"
else
  git commit -q -m "chore: sync fork $(date -u +%Y-%m-%d)"
  git push --force origin "$SYNC_BRANCH"
  echo "changed=true" >> "${GITHUB_OUTPUT:-/dev/null}"
fi

cat "$notes" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
