"""
Build the public site from entries/, git history and status/verified.yml:

  site/index.html               one row per entry
  site/p/<slug>/index.html      per-pillar results, accountable person, history
  site/p/<slug>/charter.json    the registered charter, byte for byte
  site/badge/<slug>.svg         the badge, at a stable URL
  site/registry.json            every public record, machine-readable (CC BY 4.0)

Same look as the Agents Outrun Review page (almma-ai/agents-outrun-census).
Contact details are never in the repository, so they cannot reach the site.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from census.charter import score_charter

from .entry import EntryError, load
from .history import entry_history, last_change, load_status, status_for

PAGES = "https://almma-ai.github.io/charter-registry"
REPO = "https://github.com/almma-ai/charter-registry"

CSS = """:root{--ink:#141414;--mute:#6b6b6b;--line:#e6e6e6;--acc:#b3261e;--ok:#1f6f43;--bg:#fff}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 Georgia,"Times New Roman",serif;color:var(--ink);background:var(--bg)}
main{max-width:960px;margin:0 auto;padding:48px 20px 80px}
header{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--ink);padding-bottom:8px;gap:12px;flex-wrap:wrap}
header h1{font-size:18px;letter-spacing:.08em;text-transform:uppercase;margin:0;font-weight:600}header h1 a{color:inherit;text-decoration:none}
header span{color:var(--mute);font-size:14px}
.hero{padding:48px 0 16px}.hero .num{font-size:clamp(88px,18vw,180px);line-height:.9;font-weight:700;letter-spacing:-.04em}
.hero .num small{font-size:.3em;letter-spacing:0;color:var(--mute)}.hero p.lede{font-size:22px;max-width:46ch;margin:18px 0 0}
.kv{display:flex;gap:28px;flex-wrap:wrap;margin:20px 0 0;color:var(--mute);font-size:15px}.kv b{color:var(--ink);font-family:ui-monospace,Menlo,monospace;font-weight:500}
h2{font-size:14px;letter-spacing:.08em;text-transform:uppercase;margin:48px 0 12px;color:var(--mute);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:15px}th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:600;font-size:13px;color:var(--mute)}td.n,th.n{text-align:right}td.n{font-family:ui-monospace,Menlo,monospace}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:13px}.muted{color:var(--mute)}
.bars{display:grid;gap:10px}.bar{display:grid;grid-template-columns:200px 1fr 64px 70px;align-items:center;gap:12px;font-size:15px}
.bar .track{height:10px;background:var(--line)}.bar .track i{display:block;height:10px;background:var(--ink)}
.bar b{font-family:ui-monospace,Menlo,monospace;font-weight:500;text-align:right}.why{grid-column:1/-1;color:var(--mute);font-size:14px;margin:-6px 0 4px}
.pass{color:var(--ok)}.fail{color:var(--acc)}.partial{color:var(--ink)}
code,pre{font-family:ui-monospace,Menlo,monospace;font-size:13px;background:#f5f5f5}code{padding:1px 5px}pre{padding:12px;white-space:pre-wrap;word-break:break-all}
a{color:var(--ink)}footer{margin-top:64px;border-top:1px solid var(--line);padding-top:16px;color:var(--mute);font-size:14px}
@media(max-width:640px){.bar{grid-template-columns:1fr 64px 70px}.bar .track{grid-column:1/-1;order:5}td.hide,th.hide{display:none}}"""

FOOTER = (f'<footer>The Charter Registry is kept by Almma.AI. Registry data is CC BY 4.0; code is Apache-2.0. '
          f'Entries are append-only: an update adds to the history and nothing is deleted. '
          f'Scores use the same function as the <a href="https://almma-ai.github.io/agents-outrun-census/">Agents Outrun Census</a>. '
          f'<a href="{REPO}">Register a charter</a> · <a href="{PAGES}/registry.json">registry.json</a></footer>')


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _text_width(s: str) -> int:
    # Approximate Verdana 11px advance widths, as shields.io-style badges do.
    narrow, wide = set("ilj.,:;|!' ·"), set("mwMW@%")
    return int(sum(3.5 if c in narrow else 9.5 if c in wide else 6.8 for c in s)) + 12


def badge_svg(score: int, status: str) -> str:
    left, right = "delegation charter", f"{score} · {status}"
    lw, rw = _text_width(left), _text_width(right)
    color = "#1f6f43" if status == "verified" else "#555555"
    w = lw + rw
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{_e(left)}: {_e(right)}">
<title>{_e(left)}: {_e(right)}</title>
<rect width="{lw}" height="20" fill="#141414"/><rect x="{lw}" width="{rw}" height="20" fill="{color}"/>
<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2:.1f}" y="14">{_e(left)}</text><text x="{lw + rw / 2:.1f}" y="14">{_e(right)}</text></g></svg>
"""


def collect(repo: Path) -> list[dict]:
    """Every entry on this branch as a public record, oldest registration first."""
    statuses = load_status(repo)
    records = []
    for d in sorted((repo / "entries").glob("*/")):
        try:
            e = load(d)
        except EntryError:
            continue
        hist = entry_history(repo, e.slug)
        scored = score_charter(e.charter)
        att = e.attestation
        records.append({
            "product_slug": e.slug,
            "product_name": e.product.get("product_name"),
            "organization": e.product.get("organization"),
            "website": e.product.get("website"),
            "accountable_person": e.product.get("accountable_person"),
            "charter_spec": e.charter.get("spec"),
            "charter_id": e.charter.get("id"),
            "charter_version": e.charter.get("version"),
            "charter_hash": att.get("charter_hash"),
            "charter_score": scored["charter_score"],
            "pillar_results": scored["pillars"],
            **status_for(statuses, e.slug, att.get("charter_hash")),
            "visibility": "public",
            "registered_at": hist[0]["recorded_at"] if hist else None,
            "updated_at": last_change(repo, e.slug),
            "public_key": att.get("public_key"),
            "signed_at": att.get("signed_at"),
            "history": hist,
            "_charter_raw": e.charter_raw,
        })
    records.sort(key=lambda r: (r["registered_at"] or "9999", r["product_slug"]))
    for i, r in enumerate(records, 1):
        r["entry_number"] = f"{i:03d}"
    return records


def _page(title: str, sub: str, body: str, depth: int) -> str:
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{CSS}</style></head><body><main>
<header><h1><a href="{up or './'}">Charter Registry</a></h1><span>{sub}</span></header>
{body}
{FOOTER}
</main></body></html>
"""


def index_html(records: list[dict]) -> str:
    rows = "".join(
        f'<tr><td class="n">{r["entry_number"]}</td>'
        f'<td><a href="p/{_e(r["product_slug"])}/">{_e(r["product_name"])}</a></td>'
        f'<td>{_e(r["organization"])}</td><td class="n">{r["charter_score"]}</td><td>{_e(r["status"])}</td>'
        f'<td class="mono hide">{_e((r["charter_spec"] or "").split("/")[-1])} · v{_e(r["charter_version"])}</td>'
        f'<td class="mono hide">{_e(r["registered_at"])}</td>'
        f'<td class="hide"><img src="badge/{_e(r["product_slug"])}.svg" alt="Charter Score {r["charter_score"]}, {_e(r["status"])}" height="20"></td></tr>'
        for r in records)
    table = (f'<table><thead><tr><th class="n">No.</th><th>Product</th><th>Organization</th><th class="n">Score</th>'
             f'<th>Status</th><th class="hide">Spec · charter</th><th class="hide">Registered</th><th class="hide">Badge</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>') if records else '<p class="muted">No entries yet.</p>'
    body = f"""<section class="hero"><div class="num">{len(records)}<small> registered</small></div>
<p class="lede">AI products that have written down what their agents will never do, when they stop, and who answers for them.</p></section>
<h2>Entries</h2>
{table}
<h2>What the score means</h2>
<p>Each charter follows the <a href="https://github.com/almma-ai/delegation-charter">Delegation Charter Specification</a> and is scored on its eight pillars, 0 to 100, with the same weights as the Agents Outrun Census: owner 20, escalation recipient 10, approval authority 15, never-do list 15, systems 10, inputs 5, escalation rules 15, constraints 10. A score says what is written down, not how the agent behaves.</p>
<p><b>Self-declared</b> means the owner signed the charter and its score on their own machine, and this registry checked the signature and recomputed the score. <b>Verified</b> means Almma.AI also reviewed that exact charter; any later change returns it to self-declared until it is reviewed again.</p>
<h2>Register yours</h2>
<p>Run the check, open a pull request, appear here. The walkthrough is in the <a href="{REPO}#register-a-charter">README</a>; it takes under 30 minutes and no meeting.</p>"""
    return _page("Charter Registry", "Delegation charters · public record", body, 0)


def product_html(r: dict) -> str:
    slug = _e(r["product_slug"])
    bars = "".join(
        f'<div class="bar"><span>{p["n"]}. {_e(p["label"])}</span><span class="track"><i style="width:{100 * p["points"] / p["max"]:.0f}%"></i></span>'
        f'<b>{p["points"]}/{p["max"]}</b><span class="{p["result"]}">{p["result"]}</span></div><div class="why">{_e(p["reason"])}</div>'
        for p in r["pillar_results"])
    hist = "".join(
        f'<tr><td class="mono">{_e(h["recorded_at"])}</td><td class="n">v{_e(h["charter_version"])}</td>'
        f'<td class="n">{_e(h["charter_score"])}</td><td class="mono hide">{_e((h["charter_hash"] or "")[:23])}…</td></tr>'
        for h in reversed(r["history"]))
    ap = r["accountable_person"] or {}
    verified = (f' · verified {_e(r.get("verified_at"))} by {_e(r.get("verified_by"))}' if r["status"] == "verified" else "")
    body = f"""<section class="hero"><div class="num">{r["charter_score"]}<small>/100</small></div>
<p class="lede">{_e(r["product_name"])} · {_e(r["organization"])}</p>
<div class="kv"><span>entry <b>{r["entry_number"]}</b></span><span>status <b>{_e(r["status"])}</b>{verified}</span>
<span>accountable <b>{_e(ap.get("name"))}</b>, {_e(ap.get("role"))}</span>
<span>charter <b>{_e(r["charter_id"])} v{_e(r["charter_version"])}</b></span><span>spec <b>{_e(r["charter_spec"])}</b></span>
<span>registered <b>{_e(r["registered_at"])}</b></span><span>updated <b>{_e(r["updated_at"])}</b></span></div></section>
<p><a href="{_e(r["website"])}" rel="nofollow">{_e(r["website"])}</a> · <a href="charter.json">Read the charter</a> · <a href="{REPO}/tree/main/entries/{slug}">Source and signature</a></p>
<h2>The eight pillars</h2>
<div class="bars">{bars}</div>
<h2>History · append-only</h2>
<table><thead><tr><th>Recorded</th><th class="n">Charter</th><th class="n">Score</th><th class="hide">SHA-256</th></tr></thead><tbody>{hist}</tbody></table>
<h2>Badge</h2>
<p><img src="../../badge/{slug}.svg" alt="badge" height="20"></p>
<pre>[![Delegation Charter]({PAGES}/badge/{slug}.svg)]({PAGES}/p/{slug}/)</pre>
<h2>Check it yourself</h2>
<p>The charter's SHA-256 is <code>{_e(r["charter_hash"])}</code>. The attestation was signed {_e(r["signed_at"])} with <code>{_e(r["public_key"])}</code>. Recompute the score with <code>census check charter.json</code> from <a href="https://github.com/almma-ai/agents-outrun-census">agents-outrun-census</a>.</p>"""
    return _page(f"{r['product_name']} · Charter Registry", f"Entry {r['entry_number']}", body, 2)


def build_site(repo: Path, out: Path) -> list[dict]:
    records = collect(repo)
    if out.exists():
        shutil.rmtree(out)
    (out / "badge").mkdir(parents=True)
    (out / "index.html").write_text(index_html(records), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    public = []
    for r in records:
        d = out / "p" / r["product_slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(product_html(r), encoding="utf-8")
        (d / "charter.json").write_bytes(r["_charter_raw"])
        (out / "badge" / f"{r['product_slug']}.svg").write_text(badge_svg(r["charter_score"], r["status"]), encoding="utf-8")
        public.append({k: v for k, v in r.items() if not k.startswith("_")})
    (out / "registry.json").write_text(json.dumps(
        {"license": "CC BY 4.0", "source": REPO, "entries": public}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return records
