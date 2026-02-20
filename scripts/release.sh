#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <version> [notes]"
  exit 1
fi

VER="$1"
NOTES="${2:-}"

# Ensure we are on main and up to date
git fetch origin
git checkout main
git pull origin main

# Commit any local changes (if any)
if ! git diff --quiet || ! git diff --staged --quiet; then
  git add -A
  git commit -m "${NOTES:-Release $VER}" || true
fi

# Create and push tag
if git rev-parse "$VER" >/dev/null 2>&1; then
  echo "Tag $VER already exists locally"
else
  git tag -a "$VER" -m "$VER"
fi

git push origin main
git push origin "$VER"

# Create zip from main
ZIPNAME="chatobot-${VER}.zip"
git archive --format=zip -o "$ZIPNAME" main

# Create release using gh
if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Please install and authenticate (gh auth login)."
  exit 1
fi

gh release create "$VER" --title "$VER" --notes "${NOTES:-$VER}" "$ZIPNAME" --target main

# Move zip into dist/ and commit
mkdir -p dist
mv -f "$ZIPNAME" "dist/$ZIPNAME"

# Force add in case dist was previously ignored
git add -f "dist/$ZIPNAME"
git commit -m "Add release $VER zip to dist/" || true
git push origin main

echo "Release $VER created and dist/$ZIPNAME added to repository."
