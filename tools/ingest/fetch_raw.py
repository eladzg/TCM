"""Download a registered source's raw file into data/raw/<source_id>/<date>/ with a sha256 manifest.

Raw files are immutable inputs: parsers read from here, never from the network.

Usage:
    python3 tools/ingest/fetch_raw.py GUT-SHANGHAN https://www.gutenberg.org/cache/epub/24272/pg24272.txt
    python3 tools/ingest/fetch_raw.py WS-JINGUI "https://zh.wikisource.org/w/index.php?title=金匱要略&action=raw" --name jingui.wiki
"""

import argparse
import datetime
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
# Wikimedia and archive.org refuse anonymous library user agents.
USER_AGENT = "TCM-KB-builder/0.1 (internal clinic knowledge base; https://github.com/eladzg/TCM)"


def fetch(source_id, url, today=None, name=None):
    sources = {s["source_id"]: s for s in yaml.safe_load((ROOT / "kb" / "sources.yaml").read_text("utf-8"))}
    if source_id not in sources:
        raise SystemExit(f"{source_id} is not in kb/sources.yaml; register it first")
    if sources[source_id]["license_class"] == "prohibited":
        raise SystemExit(f"{source_id} is prohibited; its content may not be stored")

    parts = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path),
                                                 query=urllib.parse.quote(parts.query, safe="=&")))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as resp:
        data = resp.read()
    day = (today or datetime.date.today()).isoformat()
    folder = ROOT / "data" / "raw" / source_id / day
    folder.mkdir(parents=True, exist_ok=True)
    name = name or parts.path.rstrip("/").rsplit("/", 1)[-1] or "index"
    (folder / name).write_bytes(data)
    manifest = {"source_id": source_id, "url": url, "file": name, "retrieved_at": day,
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    # One manifest per day folder, one entry per file (a book can span several files).
    path = folder / "manifest.json"
    entries = json.loads(path.read_text("utf-8")) if path.exists() else []
    entries = [e for e in entries if e["file"] != name] + [manifest]
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return folder / name, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_id")
    parser.add_argument("url")
    parser.add_argument("--name", help="file name to save as (default: last part of the URL path)")
    args = parser.parse_args()
    path, manifest = fetch(args.source_id, args.url, name=args.name)
    print(f"saved {path} ({manifest['bytes']} bytes, sha256 {manifest['sha256'][:12]})")


if __name__ == "__main__":
    sys.exit(main())
