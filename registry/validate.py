"""
Validate a pull request against the registry rules and write the comment.

  base  checkout of the target branch (trusted: this code runs from here)
  head  checkout of the pull request (data only: read, never executed)

Scoring and signature checks are imported from the census package
(census.charter, census.attest), so the registry never keeps its own copy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from census import attest
from census.charter import load_schema, score_charter, validate as schema_errors

from .entry import ENTRY_FILES, Entry, EntryError, check_product, load

PAGES = "https://almma-ai.github.io/charter-registry"


def tree(root: Path) -> dict[str, Path]:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # .git, and bytecode Python writes while this check runs from the base checkout
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        filenames = [f for f in filenames if not f.endswith(".pyc")]
        for name in filenames + [d for d in dirnames if (Path(dirpath) / d).is_symlink()]:
            p = Path(dirpath) / name
            out[p.relative_to(root).as_posix()] = p
    return out


def changed_files(base: Path, head: Path) -> tuple[list[str], list[str], list[str]]:
    """(added, modified, deleted) paths between two checkouts."""
    b, h = tree(base), tree(head)
    added = sorted(set(h) - set(b))
    deleted = sorted(set(b) - set(h))
    modified = []
    for k in sorted(set(b) & set(h)):
        pb, ph = b[k], h[k]
        if pb.is_symlink() or ph.is_symlink():
            if pb.is_symlink() != ph.is_symlink() or os.readlink(pb) != os.readlink(ph):
                modified.append(k)
        elif pb.read_bytes() != ph.read_bytes():
            modified.append(k)
    return added, modified, deleted


def _maintainers(base: Path) -> set[str]:
    p = base / "MAINTAINERS"
    if not p.exists():
        return set()
    return {l.strip().lstrip("@").lower() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")}


def check_status_change(base: Path, head: Path, author: str) -> list[str]:
    errs = []
    if author.lower() not in _maintainers(base):
        return [f"status/verified.yml can only be changed by an Almma maintainer (MAINTAINERS); @{author} is not one."]
    def items(root):
        p = root / "status" / "verified.yml"
        if p.is_symlink():
            raise EntryError("status/verified.yml is a symlink")
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or []) if p.exists() else []
    try:
        old, new = items(base), items(head)
    except (EntryError, yaml.YAMLError) as e:
        return [f"status/verified.yml: {e}"]
    if not isinstance(new, list) or new[:len(old)] != old:
        return ["status/verified.yml is append-only: add records at the end, never edit or remove one."]
    for s in new[len(old):]:
        if not isinstance(s, dict):
            errs.append("status/verified.yml: each record must be a mapping"); continue
        missing = [k for k in ("product_slug", "charter_hash", "status", "date", "by") if not s.get(k)]
        if missing:
            errs.append(f"status record for {s.get('product_slug')!r} is missing {', '.join(missing)}")
        if s.get("status") not in ("verified", "revoked"):
            errs.append("status must be verified or revoked")
        att = head / "entries" / str(s.get("product_slug")) / "attestation.json"
        if not att.is_file() or att.is_symlink():
            errs.append(f"no entry {s.get('product_slug')!r}")
    return errs


def check_entry(slug: str, base: Path, head: Path, schema_path: str | None) -> tuple[Entry | None, dict | None, list[str]]:
    try:
        e = load(head / "entries" / slug)
    except EntryError as ex:
        return None, None, [str(ex)]
    errs = check_product(e)
    try:
        errs += [f"charter.json {m}" for m in schema_errors(e.charter, load_schema(e.charter.get("spec"), schema_path))]
    except ValueError as ex:
        errs.append(f"charter.json: {ex}")
    # Template placeholders left in (comments in product.yml don't count, only values)
    left = [f for f, text in (("charter.json", e.charter_raw.decode("utf-8", "replace")),
                              ("product.yml", json.dumps(e.product, default=str)))
            if "REPLACE" in text]
    if left:
        errs.append(f"{' and '.join(left)} still contain{'s' if len(left) == 1 else ''} template text (REPLACE): fill in every field")
    if e.charter.get("state") != "active":
        errs.append(f"charter state is {e.charter.get('state')!r}; only active charters are registered. "
                    "Use `census check` locally while it is a draft.")
    prev = None
    if (base / "entries" / slug / "attestation.json").is_file():
        try:
            prev = load(base / "entries" / slug)
        except EntryError:
            prev = None
    pinned = prev.attestation.get("public_key") if prev else e.product.get("public_key")
    errs += attest.verify(e.attestation, e.charter_raw, pinned)
    if e.product.get("public_key") != e.attestation.get("public_key"):
        errs.append("public_key in product.yml does not match the key that signed attestation.json")
    if prev and e.product.get("public_key") != prev.product.get("public_key"):
        errs.append("the registered public_key cannot change in a pull request; open an issue to rotate a lost key")
    if e.attestation.get("product_slug") != slug:
        errs.append(f"attestation.json is for {e.attestation.get('product_slug')!r}, not {slug!r}")
    ap_p, ap_a = e.product.get("accountable_person") or {}, e.attestation.get("accountable_person") or {}
    if (ap_p.get("name"), ap_p.get("role")) != (ap_a.get("name"), ap_a.get("role")):
        errs.append("accountable_person differs between product.yml and attestation.json: sign again")
    if prev and prev.attestation.get("charter_hash") != e.attestation.get("charter_hash"):
        if e.charter.get("id") != prev.charter.get("id"):
            errs.append(f"charter id changed from {prev.charter.get('id')!r}; an entry keeps one charter id")
        pv, nv = prev.charter.get("version"), e.charter.get("version")
        if isinstance(pv, int) and isinstance(nv, int) and nv <= pv:
            errs.append(f"charter version {nv} must be higher than the registered version {pv}: every change is a new version")
    return e, score_charter(e.charter), errs


def from_pr_files(rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """(added, modified, deleted) from GitHub's list of a pull request's files
    (GET /repos/{owner}/{repo}/pulls/{n}/files). Unlike comparing whole trees,
    this counts only what the pull request changes, so a fork that is behind
    main is not blamed for changes it never made."""
    added, modified, deleted = [], [], []
    for r in rows:
        st, fn = r.get("status"), r.get("filename")
        if st == "added" or st == "copied":
            added.append(fn)
        elif st == "removed":
            deleted.append(fn)
        elif st == "renamed":
            deleted.append(r.get("previous_filename")); added.append(fn)
        else:
            modified.append(fn)
    return sorted(added), sorted(modified), sorted(deleted)


def run(base: Path, head: Path, author: str, schema_path: str | None = None,
        pr_files: list[dict] | None = None) -> tuple[bool, str]:
    added, modified, deleted = from_pr_files(pr_files) if pr_files is not None else changed_files(base, head)
    changed = added + modified + deleted
    lines = ["## Charter Registry check", ""]
    problems: list[str] = []

    entry_paths = [p for p in changed if p.startswith("entries/")]
    status_paths = [p for p in changed if p.startswith("status/")]
    other = [p for p in changed if p not in entry_paths and p not in status_paths]

    for p in deleted:
        if p.startswith("entries/"):
            problems.append(f"`{p}` was deleted. The registry is append-only: nothing is deleted or rewritten.")
    slugs = sorted({p.split("/")[1] for p in entry_paths if p.count("/") >= 2})
    for p in entry_paths:
        parts = p.split("/")
        if len(parts) != 3 or parts[2] not in ENTRY_FILES:
            problems.append(f"`{p}`: an entry folder holds only {', '.join(ENTRY_FILES)}.")
    if entry_paths and other:
        problems.append("A registration pull request may only change files in `entries/<product-slug>/`. "
                        "Also changed: " + ", ".join(f"`{p}`" for p in other[:10]))
    if status_paths:
        if status_paths != ["status/verified.yml"]:
            problems.append("only status/verified.yml may change under status/")
        problems += check_status_change(base, head, author)

    if not entry_paths and not status_paths:
        lines.append("No registry entries changed, so there is nothing to check. Code changes are reviewed by a maintainer.")
        return not problems, "\n".join(lines + [f"- {p}" for p in problems]) + "\n"

    all_ok = not problems
    for slug in slugs:
        e, scored, errs = check_entry(slug, base, head, schema_path)
        ok = not errs
        all_ok &= ok
        name = (e.product.get("product_name") if e else None) or slug
        lines.append(f"### {'Passed' if ok else 'Not yet'}: {name} (`{slug}`)")
        if scored:
            lines += ["", f"**Charter Score {scored['charter_score']}/100** · self-declared · "
                      f"charter `{e.charter.get('id')}` v{e.charter.get('version')} · spec `{e.charter.get('spec')}`", "",
                      "| # | Pillar | Points | Result | Why |", "|---|---|---|---|---|"]
            lines += [f"| {p['n']} | {p['label']} | {p['points']}/{p['max']} | {p['result']} | {p['reason']} |"
                      for p in scored["pillars"]]
        if errs:
            lines += ["", "**To fix before this can merge:**"] + [f"- {x}" for x in errs]
        else:
            lines += ["", f"After merge, this entry appears at {PAGES}/p/{slug}/ and its badge is:", "",
                      "```markdown", f"[![Delegation Charter]({PAGES}/badge/{slug}.svg)]({PAGES}/p/{slug}/)", "```"]
        lines.append("")
    if problems:
        lines += ["### Pull request", ""] + [f"- {p}" for p in problems]
    lines += ["", "<sub>Scored by census.charter.score_charter, the same function as the Agents Outrun Census. "
              "Re-run anytime with `census sign` and push again.</sub>"]
    return all_ok, "\n".join(lines) + "\n"
