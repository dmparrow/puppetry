#!/usr/bin/env bash
set -euo pipefail

PAGE_URL="https://quaternius.com/packs/rpgcharacters.html"
DEST="${1:-assets/quaternius-rpg}"
ZIP_PATH="${2:-}"
mkdir -p "$DEST"

if [[ -n "$ZIP_PATH" ]]; then
  cp "$ZIP_PATH" "$DEST/pack.zip"
else
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  page="$tmp/page.html"
  curl -fsSL "$PAGE_URL" -o "$page"

  url="$(python3 - "$page" <<'PY'
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
import sys

BASE = "https://quaternius.com/packs/rpgcharacters.html"

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag != "a": return
        d=dict(attrs)
        href=d.get("href")
        if href:
            self.links.append((href, d))

p=Parser(); p.feed(Path(sys.argv[1]).read_text(errors="ignore"))
candidates=[]
for href, attrs in p.links:
    u=urljoin(BASE, href)
    lo=u.lower()
    score=0
    if lo.endswith(".zip"): score += 100
    if "download" in lo: score += 40
    if "drive.google" in lo or "dropbox" in lo: score += 30
    if "itch.io" in lo: score += 10
    if "patreon" in lo or "discord" in lo: score -= 50
    if score > 0:
        candidates.append((score,u))
if not candidates:
    raise SystemExit(2)
print(sorted(candidates, reverse=True)[0][1])
PY
  )" || true

  if [[ -z "${url:-}" ]]; then
    echo "Could not discover the download URL automatically."
    echo "Open: $PAGE_URL"
    echo "Download the RPG Character Pack ZIP, then rerun:"
    echo "  $0 '$DEST' /path/to/downloaded.zip"
    exit 2
  fi

  if [[ "$url" != *.zip* ]]; then
    echo "The official page resolved to a non-direct download: $url"
    echo "Open it, download the ZIP, then rerun:"
    echo "  $0 '$DEST' /path/to/downloaded.zip"
    exit 2
  fi

  echo "Downloading $url"
  curl -fL "$url" -o "$DEST/pack.zip"
fi

rm -rf "$DEST/extracted"
mkdir -p "$DEST/extracted"
unzip -q "$DEST/pack.zip" -d "$DEST/extracted"

echo "Extracted Quaternius RPG Character Pack to: $DEST/extracted"
echo "Build the Blender scene with:"
echo "  blender --background --python blender_test/setup_quaternius_scene.py -- --pack-dir '$DEST/extracted' --output mocap_four_actor_test.blend"
