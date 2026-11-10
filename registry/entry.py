"""
One registry entry: entries/<product_slug>/{product.yml, charter.json, attestation.json}.

Files in a pull request are read as data only. Nothing from a pull request is
executed, imported or followed: symlinks are refused before any read, files
are size-capped, YAML is parsed with safe_load.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENTRY_FILES = ("product.yml", "charter.json", "attestation.json")
MAX_BYTES = 256 * 1024
SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$")
PRODUCT_REQUIRED = ("product_slug", "product_name", "organization", "website", "accountable_person",
                    "public_key", "visibility")
PRODUCT_ALLOWED = set(PRODUCT_REQUIRED)
# Contact details are private. The repository is public, so they are refused here
# rather than published; the pull request author's GitHub account is the contact.
PRODUCT_PRIVATE = {"contact", "email", "phone", "contact_email", "contact_phone"}


class EntryError(Exception):
    pass


def read_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise EntryError(f"{path.name} is a symlink; entries must be plain files")
    if not path.is_file():
        raise EntryError(f"{path.name} is missing")
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise EntryError(f"{path.name} is {size} bytes; the limit is {MAX_BYTES}")
    return path.read_bytes()


@dataclass
class Entry:
    slug: str
    product: dict
    charter_raw: bytes
    charter: dict
    attestation: dict
    problems: list[str] = field(default_factory=list)


def load(entry_dir: Path) -> Entry:
    """Load an entry; raise EntryError if a file cannot be read at all."""
    slug = entry_dir.name
    if entry_dir.is_symlink():
        raise EntryError("the entry folder is a symlink")
    try:
        product = yaml.safe_load(read_bytes(entry_dir / "product.yml").decode("utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as e:
        raise EntryError(f"product.yml is not valid YAML: {e}")
    charter_raw = read_bytes(entry_dir / "charter.json")
    try:
        charter = json.loads(charter_raw)
        attestation = json.loads(read_bytes(entry_dir / "attestation.json"))
    except (ValueError, UnicodeDecodeError) as e:
        raise EntryError(f"not valid JSON: {e}")
    if not isinstance(product, dict) or not isinstance(charter, dict) or not isinstance(attestation, dict):
        raise EntryError("product.yml, charter.json and attestation.json must each hold an object")
    return Entry(slug, product, charter_raw, charter, attestation)


def check_product(e: Entry) -> list[str]:
    p = e.product
    errs = []
    if not SLUG.match(e.slug):
        errs.append(f"folder name {e.slug!r} is not a valid slug (lowercase letters, digits, hyphens; 1-50 chars)")
    private = sorted(PRODUCT_PRIVATE & set(p))
    if private:
        errs.append(f"product.yml has {', '.join(private)}: this repository is public, so contact details "
                    "must not be committed. Remove them; we reach you through your GitHub account.")
    unknown = sorted(set(p) - PRODUCT_ALLOWED - PRODUCT_PRIVATE)
    if unknown:
        errs.append(f"product.yml has unknown fields: {', '.join(unknown)}")
    for k in PRODUCT_REQUIRED:
        if p.get(k) in (None, "", {}):
            errs.append(f"product.yml: {k} is required")
    if p.get("product_slug") and p.get("product_slug") != e.slug:
        errs.append(f"product_slug {p.get('product_slug')!r} must match the folder name {e.slug!r}")
    if p.get("website") and not re.match(r"^https://[^\s/]+\.[^\s]+$", str(p["website"])):
        errs.append("website must be an https:// URL")
    ap = p.get("accountable_person")
    if ap is not None and not (isinstance(ap, dict) and ap.get("name") and ap.get("role")):
        errs.append("accountable_person needs a name and a role")
    if p.get("visibility") not in (None, "public"):
        errs.append("visibility must be public: everything in this repository is published. "
                    "To keep a charter private, run `census check` and `census sign` locally and submit when ready.")
    for k in ("product_name", "organization"):
        if p.get(k) is not None and (not isinstance(p[k], str) or len(p[k]) > 120):
            errs.append(f"{k} must be text of at most 120 characters")
    return errs
