"""
Registry records, derived from git history and status/verified.yml.

Nothing here is written by a bot. The record of an entry is what git already
holds: when its attestation was first merged (registered_at, entry number),
every later attestation (history), and the last change (updated_at). With force
pushes blocked on main, that record is append-only by construction.

Runs only on the trusted main branch (publish), never on pull request content.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from .entry import ENTRY_FILES


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _commits(repo: Path, path: str) -> list[tuple[str, str]]:
    """(sha, ISO date) of every commit touching path, oldest first."""
    out = _git(repo, "log", "--reverse", "--format=%H%x09%cI", "--", path)
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if line.strip()]


def entry_history(repo: Path, slug: str) -> list[dict]:
    """One item per distinct charter_hash ever merged for this entry, oldest first."""
    items: list[dict] = []
    for sha, date in _commits(repo, f"entries/{slug}/attestation.json"):
        try:
            att = json.loads(_git(repo, "show", f"{sha}:entries/{slug}/attestation.json"))
        except (subprocess.CalledProcessError, ValueError):
            continue
        if items and items[-1]["charter_hash"] == att.get("charter_hash"):
            continue
        items.append({
            "charter_hash": att.get("charter_hash"),
            "charter_version": att.get("charter_version"),
            "charter_score": att.get("charter_score"),
            "signed_at": att.get("signed_at"),
            "recorded_at": date[:10],
            "commit": sha,
        })
    return items


def last_change(repo: Path, slug: str) -> str | None:
    dates = [d for f in ENTRY_FILES for _, d in _commits(repo, f"entries/{slug}/{f}")]
    return max(dates)[:10] if dates else None


def load_status(repo: Path) -> list[dict]:
    p = repo / "status" / "verified.yml"
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def status_for(statuses: list[dict], slug: str, charter_hash: str) -> dict:
    """Verified applies to the exact charter Almma reviewed. Any later change to the
    charter returns the entry to self-declared until it is reviewed again."""
    hit = None
    for s in statuses:
        if s.get("product_slug") == slug and s.get("charter_hash") == charter_hash:
            hit = s
    if hit and hit.get("status") == "verified":
        return {"status": "verified", "verified_at": str(hit.get("date")), "verified_by": hit.get("by")}
    return {"status": "self-declared"}
