# Attestation format `charter-attestation/0`

Made by `census sign` on the owner's machine; checked by this registry with
`census.attest.verify`. Version 0 stands in until the Delegation Charter v1.0
signed attestation format is published, and will be aligned with it.

| Field | Contents |
| --- | --- |
| `format` | `charter-attestation/0` |
| `product_slug` | The entry this attestation is for. |
| `charter_spec`, `charter_id`, `charter_version` | Copied from charter.json. |
| `charter_hash` | `sha256:` + SHA-256 of charter.json exactly as committed. |
| `charter_score` | 0-100, from `census.charter.score_charter`. |
| `pillar_results` | Eight items: `n`, `key`, `points`, `max`, `result` (pass, partial, fail). |
| `scorer` | `id` of the scoring rules (`census.charter.score_charter/1`), package and version. |
| `accountable_person` | `name` and `role`, as in product.yml. |
| `signed_at` | UTC, ISO 8601. |
| `public_key` | `ed25519:` + base64 of the 32-byte public key. |
| `signature` | Base64 Ed25519 signature over the canonical JSON of every other field (keys sorted, no whitespace, UTF-8). |

## What the registry checks

1. The signature verifies against `public_key`.
2. `public_key` matches product.yml and, for an update, the key that signed the
   entry's first registration (the key is pinned).
3. `charter_hash` matches charter.json.
4. The score and pillar results equal a fresh run of the same scorer.
5. The scorer id is the one the registry runs; after a scoring change, owners re-sign.

## What a signature means

It shows that whoever holds the key stood behind this charter and this score,
and that neither changed after signing. It does not show that the agent behaves
as the charter says. That is what a review for "verified" status looks at.

## Keys

`census keygen` writes the private key to `~/.config/charter-registry/keys/<slug>.pem`
(mode 0600). Keep it with your other credentials. A lost key cannot be replaced
by a pull request; open an issue and a maintainer will confirm the change with
the accountable person.
