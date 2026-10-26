---
title: "Publish a Verified Synthetic Dataset to Hugging Face"
description: "Upload an attested Misata dataset or evalpack to the Hugging Face Hub with its spec, its certificate, a generated dataset card and a standalone verifier, after re-checking every invariant locally."
---

# Publish a verified dataset to Hugging Face

`misata publish` uploads a dataset to the Hugging Face Hub together with
everything needed to check it: the spec that generated it, the attestation
that pins every file, and `verify.py`. Anyone who downloads it can confirm
every declared invariant with DuckDB, without installing Misata.

Nothing leaves your machine until the same check passes locally. Every
file's SHA-256 must match the attestation, and every invariant must hold on
the files as they are now.

```diagram
# Verify first, then upload
 out/  (tables + attestation.intoto.json + verify.py)
   │
   ▼
 misata publish out --hf owner/name
   │
   ├─ attestation present?                      no ─▶ exit 2
   ├─ spec present, digest matches?             no ─▶ exit 2
   ├─ fitted.json (mimic output) without
   │  --allow-fitted?                          yes ─▶ exit 2
   ├─ every sha256 matches, every invariant
   │  holds on the files as they are now?       no ─▶ exit 1, nothing uploaded
   │
   ▼
 DATASET_CARD.md generated from the attestation
   │
   ├─ --dry-run ─▶ stop here: read the card, list the files
   │
   ▼
 one commit to the Hub: tables, spec, attestation,
 DSSE envelope, verify.py, README.md (the card)
```

## Publish a dataset

```bash
pip install "misata[hf]"
hf auth login                       # or export HF_TOKEN=...

misata generate -c misata.yaml -o out --format parquet --attest
misata publish out --hf acme/shop-orders --schema misata.yaml --dry-run
misata publish out --hf acme/shop-orders --schema misata.yaml
```

`--dry-run` verifies, writes `out/DATASET_CARD.md` and lists the files it
would upload. Read the card, then run it again without the flag.

`--schema` names the spec the attestation pins. Leave it out when the spec
is already in the folder. A spec whose digest does not match is refused, so
the published spec is always the one that made the data.

The upload is one commit:

| File | What it is |
|---|---|
| `orders.parquet`, ... | the tables, one Hub viewer config each |
| `misata.yaml` | the spec |
| `attestation.intoto.json` | the in-toto Statement: file digests and every invariant |
| `attestation.dsse.json` | the same Statement in an unsigned DSSE envelope, ready for `cosign` |
| `verify.py` | the standalone verifier |
| `README.md` | the dataset card |

## The dataset card

The card is generated from the attestation, not written by hand:

- Hub metadata: the licence (`--license`, default `cc-by-4.0`), the tags
  `misata`, `synthetic` and `verified-synthetic`, the size category and
  one config per table;
- the spec's description, the Misata version and the seed;
- the invariant table, with each expected and observed value;
- how to re-verify (`python verify.py`) and how to regenerate.

A **verified by Misata** badge links to the
[certificate predicate](../attestation/certificate-v1.md).

## Publish an evalpack

```bash
misata evalpack -c misata.yaml -o pack --rotations 3
misata publish pack --hf acme/retail-answer-key
```

The gold SQL of every question is re-run on every database before the
upload. Each table becomes a config and each rotation a split (`seed_42`,
`seed_43`, ...), so the Hub viewer shows every database. The card states the
pass rule, a query is correct only when it matches on every rotation, and
includes the near-miss numbers measured when the pack was built.

## What is refused

| Situation | Exit |
|---|---|
| No `attestation.intoto.json` in the folder | 2 |
| The spec the attestation pins is missing or different | 2 |
| Output of `misata mimic` without `--allow-fitted` | 2 |
| A file changed since it was attested, or an invariant no longer holds | 1 |
| The Hub refuses the upload (no login, no write access) | 1 |

`misata mimic` writes `fitted.json` beside its output, because a twin fitted
to real rows reuses the source's category values and quantiles and is not
anonymous. With `--allow-fitted`, the card says so in its first lines, and
the "No source data was used" line is left out.

The token is read by `huggingface_hub` from `HF_TOKEN` or the cached login.
It is never a command-line option, and Misata never logs or writes it.

## From Python

```python
import misata

release = misata.prepare_hub_release("out", "acme/shop-orders", schema_path="misata.yaml")
release.write_card()                  # out/DATASET_CARD.md
url = misata.publish_to_hub(release, private=True)
```

`prepare_hub_release` raises `misata.publish.PublishRefused` for everything
in the table above. `verification_failed` is True when the data no longer
holds what its attestation says.

## See it end to end

- [An eval database with a correct answer key](../usecases/eval-database.md)
  builds the kind of rotated pack that publishes as one split per rotation.
- [A warehouse before the product has users](../usecases/warehouse-before-users.md)
  writes an attested Parquet folder that publishes as it is.
- [Attest a dataset](attest.md) explains what the card's invariant table
  is made of.
