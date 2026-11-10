"""End-to-end: a founder signs an entry, the pull request check runs, the site builds.
Offline: the schema comes from tests/fixtures."""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from census import attest

from registry import publish
from registry.validate import run

FIX = Path(__file__).parent / "fixtures"
SCHEMA = str(FIX / "charter-0.1.2.schema.json")
CHARTER = json.loads((FIX / "estimate-intake.charter.json").read_text())


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "base"
        (self.base / "entries").mkdir(parents=True)
        (self.base / "status").mkdir()
        (self.base / "MAINTAINERS").write_text("Lucas-almma\n")
        self.keyfile = self.tmp / "k.pem"
        self.pub = attest.generate_key(self.keyfile)
        self.key = attest.load_key(self.keyfile)
        self.product = {"product_slug": "estimate-intake", "product_name": "Estimate Intake",
                        "organization": "Northwind Moving", "website": "https://northwind.example",
                        "accountable_person": {"name": "Ana Ruiz", "role": "Operations manager"},
                        "public_key": self.pub, "visibility": "public"}

    def write_entry(self, root, charter=None, product=None, key=None, sign=True):
        d = root / "entries" / (product or self.product)["product_slug"]
        d.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(charter or CHARTER, indent=2) + "\n").encode()
        (d / "charter.json").write_bytes(raw)
        (d / "product.yml").write_text(yaml.safe_dump(product or self.product, sort_keys=False))
        if sign:
            att = attest.build(raw, product or self.product, key or self.key)
            (d / "attestation.json").write_text(json.dumps(att, indent=2) + "\n")
        return d

    def head(self):
        h = self.tmp / "head"
        if h.exists():
            shutil.rmtree(h)
        shutil.copytree(self.base, h, symlinks=True)
        return h

    def check(self, head, author="founder"):
        return run(self.base, head, author, SCHEMA)

    # -------------------------------------------------------------- passes
    def test_new_entry_passes_and_comment_shows_score(self):
        h = self.head(); self.write_entry(h)
        ok, md = self.check(h)
        self.assertTrue(ok, md)
        self.assertIn("Charter Score 100/100", md)
        self.assertIn("badge/estimate-intake.svg", md)

    def test_update_with_higher_version_passes(self):
        self.write_entry(self.base)
        h = self.head(); c = copy.deepcopy(CHARTER); c["version"] = 4; c["scope"]["will_do"].append("Log the call")
        self.write_entry(h, charter=c)
        ok, md = self.check(h)
        self.assertTrue(ok, md)

    def test_bytecode_in_base_is_ignored(self):
        h = self.head(); self.write_entry(h)
        (self.base / "registry" / "__pycache__").mkdir(parents=True); (self.base / "registry" / "__pycache__" / "x.pyc").write_bytes(b"x")
        ok, md = self.check(h)
        self.assertTrue(ok, md)

    def test_template_comment_does_not_count_as_placeholder(self):
        h = self.head(); d = self.write_entry(h)
        (d / "product.yml").write_text("# replace every REPLACE\n" + (d / "product.yml").read_text())
        ok, md = self.check(h)
        self.assertTrue(ok, md)

    def test_fork_behind_main_is_judged_on_its_own_files(self):
        h = self.head(); self.write_entry(h)
        (self.base / "README.md").write_text("main moved on after the fork")
        files = [{"status": "added", "filename": f"entries/estimate-intake/{f}"} for f in ("product.yml", "charter.json", "attestation.json")]
        ok, md = run(self.base, h, "founder", SCHEMA, files)
        self.assertTrue(ok, md)
        ok, md = run(self.base, h, "founder", SCHEMA, files + [{"status": "removed", "filename": "entries/other/charter.json"}])
        self.assertFalse(ok); self.assertIn("append-only", md)

    def test_code_only_change_is_not_an_entry(self):
        h = self.head(); (h / "README.md").write_text("x")
        ok, md = self.check(h)
        self.assertTrue(ok); self.assertIn("nothing to check", md)

    # -------------------------------------------------------------- refusals
    def assertRefused(self, head, needle, author="founder"):
        ok, md = self.check(head, author)
        self.assertFalse(ok, md)
        self.assertIn(needle, md)

    def test_edited_score_is_refused(self):
        h = self.head(); d = self.write_entry(h)
        att = json.loads((d / "attestation.json").read_text()); att["charter_score"] = 100 - 1
        (d / "attestation.json").write_text(json.dumps(att))
        self.assertRefused(h, "recomputed")

    def test_charter_changed_after_signing_is_refused(self):
        h = self.head(); d = self.write_entry(h)
        (d / "charter.json").write_text((d / "charter.json").read_text().replace("Estimate intake", "Estimate Intake"))
        self.assertRefused(h, "charter_hash")

    def test_schema_invalid_is_refused(self):
        h = self.head(); c = copy.deepcopy(CHARTER); c["scope"]["never_do"] = []
        self.write_entry(h, charter=c)
        self.assertRefused(h, "never_do")

    def test_unfilled_template_is_refused(self):
        root = Path(__file__).resolve().parent.parent / "templates"
        c = json.loads((root / "charter.json").read_text()); c["state"] = "active"
        h = self.head(); self.write_entry(h, charter=c)
        self.assertRefused(h, "template text")

    def test_draft_is_refused(self):
        h = self.head(); c = copy.deepcopy(CHARTER); c["state"] = "draft"
        self.write_entry(h, charter=c)
        self.assertRefused(h, "only active charters")

    def test_contact_in_product_yml_is_refused(self):
        h = self.head(); p = dict(self.product, contact="ana@northwind.example")
        self.write_entry(h, product=p)
        self.assertRefused(h, "contact details")

    def test_private_visibility_is_refused(self):
        h = self.head(); self.write_entry(h, product=dict(self.product, visibility="private"))
        self.assertRefused(h, "visibility must be public")

    def test_slug_must_match_folder(self):
        h = self.head(); d = self.write_entry(h)
        os.rename(d, d.parent / "other-name")
        self.assertRefused(h, "must match the folder name")

    def test_update_signed_by_another_key_is_refused(self):
        self.write_entry(self.base)
        h = self.head(); other = self.tmp / "o.pem"; opub = attest.generate_key(other)
        c = copy.deepcopy(CHARTER); c["version"] = 4
        self.write_entry(h, charter=c, product=dict(self.product, public_key=opub), key=attest.load_key(other))
        ok, md = self.check(h)
        self.assertFalse(ok)
        self.assertIn("different key", md)
        self.assertIn("cannot change", md)

    def test_update_without_new_version_is_refused(self):
        self.write_entry(self.base)
        h = self.head(); c = copy.deepcopy(CHARTER); c["scope"]["will_do"].append("Log the call")
        self.write_entry(h, charter=c)
        self.assertRefused(h, "must be higher")

    def test_deleting_an_entry_is_refused(self):
        self.write_entry(self.base)
        h = self.head(); shutil.rmtree(h / "entries" / "estimate-intake")
        self.assertRefused(h, "append-only")

    def test_symlink_is_refused_before_reading(self):
        h = self.head(); d = self.write_entry(h)
        (d / "charter.json").unlink(); (d / "charter.json").symlink_to("/etc/passwd")
        ok, md = self.check(h)
        self.assertFalse(ok); self.assertIn("symlink", md); self.assertNotIn("root:", md)

    def test_extra_file_in_entry_is_refused(self):
        h = self.head(); d = self.write_entry(h); (d / "notes.txt").write_text("x")
        self.assertRefused(h, "holds only")

    def test_mixing_entry_and_code_is_refused(self):
        h = self.head(); self.write_entry(h); (h / "registry.py").write_text("x")
        self.assertRefused(h, "may only change files in")

    def test_status_change_by_non_maintainer_is_refused(self):
        self.write_entry(self.base)
        h = self.head()
        (h / "status" / "verified.yml").write_text(yaml.safe_dump([{"product_slug": "estimate-intake",
            "charter_hash": "sha256:x", "status": "verified", "date": "2026-12-01", "by": "me"}]))
        self.assertRefused(h, "maintainer", author="founder")
        ok, md = self.check(h, author="Lucas-almma")
        self.assertTrue(ok, md)

    def test_status_is_append_only(self):
        self.write_entry(self.base)
        rec = {"product_slug": "estimate-intake", "charter_hash": "sha256:x", "status": "verified", "date": "2026-12-01", "by": "L"}
        (self.base / "status" / "verified.yml").write_text(yaml.safe_dump([rec]))
        h = self.head(); (h / "status" / "verified.yml").write_text(yaml.safe_dump([dict(rec, by="someone else")]))
        self.assertRefused(h, "append-only", author="Lucas-almma")


class Site(unittest.TestCase):
    def test_site_from_git_history(self):
        t = Registry("test_new_entry_passes_and_comment_shows_score"); t.setUp()
        repo = t.base
        git(repo, "init", "-q", "-b", "main")
        t.write_entry(repo); git(repo, "add", "-A"); git(repo, "commit", "-qm", "register")
        c = copy.deepcopy(CHARTER); c["version"] = 4; c["escalation_recipient"].pop("backup")
        t.write_entry(repo, charter=c); git(repo, "add", "-A"); git(repo, "commit", "-qm", "update")
        h = attest.build((repo / "entries/estimate-intake/charter.json").read_bytes(), t.product, t.key)["charter_hash"]
        (repo / "status" / "verified.yml").write_text(yaml.safe_dump([{"product_slug": "estimate-intake",
            "charter_hash": h, "status": "verified", "date": "2026-12-02", "by": "Lucas E. Wall"}]))
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "verify")
        out = t.tmp / "site"
        recs = publish.build_site(repo, out)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["entry_number"], "001")
        self.assertEqual([x["charter_score"] for x in r["history"]], [100, 96])
        self.assertEqual(r["status"], "verified")
        for f in ["index.html", "registry.json", "badge/estimate-intake.svg",
                  "p/estimate-intake/index.html", "p/estimate-intake/charter.json"]:
            self.assertTrue((out / f).is_file(), f)
        self.assertEqual((out / "p/estimate-intake/charter.json").read_bytes(),
                         (repo / "entries/estimate-intake/charter.json").read_bytes())
        svg = (out / "badge/estimate-intake.svg").read_text()
        self.assertIn("96 · verified", svg)
        reg = json.loads((out / "registry.json").read_text())
        self.assertNotIn("contact", json.dumps(reg))
        self.assertNotIn("_charter_raw", json.dumps(reg))


if __name__ == "__main__":
    unittest.main()
