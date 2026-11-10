# Charter Registry

A public record of AI products that have written down a
[Delegation Charter](https://github.com/almma-ai/delegation-charter) for their agents:
what each agent will never do, when it stops, and who answers for it. Each entry
gets a Charter Score, a page and a badge.

**The registry:** https://almma-ai.github.io/charter-registry

Registering takes three steps: run the check on your own machine, open a pull
request, appear on the list. Nothing runs on a server, and your code and
prompts never leave your machine. Only your charter, a short product file and
a signed score are submitted.

## Register a charter

About 30 minutes if your charter is written. You need Python 3.10 or later, git
and a GitHub account.

### 1. Install the check

```bash
pip install "agents-outrun-census @ git+https://github.com/almma-ai/agents-outrun-census@v0.2.0"
census --help
```

This is the same package that scores the
[Agents Outrun Census](https://almma-ai.github.io/agents-outrun-census/), so a score
means the same thing in the census, here and on your badge.

### 2. Fork this repository and make your folder

Fork `almma-ai/charter-registry` on GitHub, clone your fork, and pick a slug: lowercase
letters, digits and hyphens, used in your URLs. It can't change later.

```bash
git clone https://github.com/<you>/charter-registry && cd charter-registry
mkdir -p entries/your-product
cp templates/product.yml templates/charter.json entries/your-product/
cd entries/your-product
```

### 3. Write your charter and check it

Edit `charter.json` and replace every `REPLACE`. The template shows every field; [SPEC.md](https://github.com/almma-ai/delegation-charter/blob/main/SPEC.md)
says what each one means. In short: name one person as owner, list every tool with its
access (read, write or irreversible), write a never-do list, and say what happens in the
four cases where the agent must stop. When it is ready, set `"state": "active"`.

Check it as often as you like; nothing is sent anywhere:

```bash
census check charter.json
```

```
Schema: valid
Charter Score: 91/100
  1. Owner                    20/20 pass    Owner is a named person.
  2. Escalation recipient      6/10 partial Recipient named; no backup.
  ...
```

Each line says why the pillar got its points. To keep your charter private, simply
stop here. The check runs only on your machine, and nothing is published until
you open a pull request.

### 4. Fill in `product.yml`

Replace every `REPLACE`: slug, name, organization, website, and the accountable person's name and role. Everything
in this file is published. **Don't add an email or phone number:** this repository is
public, and the check refuses contact details. We'll reach you through the
GitHub account that opens the pull request.

### 5. Make your signing key

```bash
census keygen --product product.yml
```

It prints a line `public_key: ed25519:...`; put it in place of the `public_key` line in `product.yml`. The private key
stays in `~/.config/charter-registry/keys/`. Keep it: every future update to this entry
must be signed with the same key.

### 6. Sign

```bash
census sign --product product.yml
```

This writes `attestation.json`: your charter's SHA-256, its score and per-pillar results,
the accountable person, the time and your signature.

### 7. Open the pull request

```bash
cd ../..
git add entries/your-product
git commit -m "Register Your Product"
git push
```

Open a pull request from your fork. Within a couple of minutes the registry check
comments the result: your score, each pillar, and anything to fix. Fix the issue, run
`census sign` again, and push. The check re-runs on every push. When it passes, a
maintainer merges, and your entry appears on the list.

### 8. Add the badge

The check's comment includes your badge snippet:

```markdown
[![Delegation Charter](https://almma-ai.github.io/charter-registry/badge/your-product.svg)](https://almma-ai.github.io/charter-registry/p/your-product/)
```

Paste it into your README or website. For HTML:
`<a href="https://almma-ai.github.io/charter-registry/p/your-product/"><img src="https://almma-ai.github.io/charter-registry/badge/your-product.svg" alt="Delegation Charter"></a>`.
The badge updates itself when your entry changes.

## Update a charter

Edit `charter.json`, raise `version` by one, run `census sign` with the same key, and
open a pull request. The history is append-only: your page keeps every earlier
version's hash and score, and nothing is deleted or rewritten.

## What the check refuses

- A charter that fails the [JSON Schema](https://github.com/almma-ai/delegation-charter/tree/main/schema) for its spec version, or that is not `active`.
- An attestation whose signature, charter hash, score or pillar results don't hold.
- An update signed by a different key from the one first registered, or one that changes the charter without raising its version.
- Anything outside your `entries/<slug>/` folder, any deleted file, symlinks, files over 256 KB.
- Contact details, `visibility` other than `public`, or template text left in (`REPLACE`).

## Self-declared and verified

Every entry starts **self-declared**. That means you signed the charter and its score,
and the registry checked the signature and recomputed the score. **Verified** is set only by
Almma.AI after a review of that exact charter (`status/verified.yml`). If you change the
charter afterward, the entry returns to self-declared until it is reviewed again.

## Where each field lives

| Field | Where |
| --- | --- |
| product_slug, product_name, organization, website | `product.yml` |
| accountable_person (name, role) | `product.yml`, signed into `attestation.json` |
| charter_version (spec), charter_hash, charter_score, pillar_results | `attestation.json`, recomputed by the check |
| status (self-declared or verified) | `status/verified.yml`, set by Almma.AI only |
| visibility | `product.yml`; always public here, since private work stays on your machine |
| registered_at, updated_at, history | git history of the entry: first merge, last change, every attestation merged |
| contact | not stored: the pull request author's GitHub account |

The whole registry is also at [registry.json](https://almma-ai.github.io/charter-registry/registry.json).

## For maintainers

- **Settings.** Protect `main`: require a pull request, require the `registry check / check` status,
  and block force pushes and deletions. The append-only history depends on this. Pages: source "GitHub Actions".
- **Merging.** Merge an entry when the check passes and the names and website look legitimate. Use squash
  merges so each update is one commit in the history.
- **Verifying.** Append a record to `status/verified.yml` with the exact `charter_hash` reviewed.
  Only logins in `MAINTAINERS` may change it, and records are never edited or removed; append a `revoked` record instead.
- **Scoring changes.** The score comes from `census.charter.score_charter`, pinned in `requirements.txt`.
  Raising the pin to a census release with a new scorer id makes existing owners re-sign on their next update.
  Published pages always show the current scorer's result.
- **The check.** `.github/workflows/check.yml` uses `pull_request_target` so it can comment on pull
  requests from forks. It runs only this repository's code and reads the pull request as data. Don't change it to
  install, import or run anything from the pull request.

Run locally:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
python -m registry.cli publish --out site        # build the site from this checkout
python -m registry.cli validate --base <main-checkout> --head <pr-checkout> --author <login>
```

## License

Code: Apache-2.0 ([LICENSE](LICENSE)). Registry data (entries, status, the published
site and registry.json): CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)), credit "Charter Registry, Almma.AI".
The specification it uses is CC BY 4.0: "Delegation Charter Specification, Lucas E. Wall, Almma.AI".
