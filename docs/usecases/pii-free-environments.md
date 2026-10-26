---
title: PII-Free Staging and Test Environments
description: Fill staging, QA and demo databases from the production DDL alone, with no production row ever read, and hand reviewers a provenance statement, an attestation and a byte-for-byte reproduction as proof.
---

# PII-free lower environments

Copying production into staging and masking it is the usual answer, and
the usual audit finding: the masking misses a column, a free-text note
keeps a name, a join re-identifies someone. The data never has to be
masked if it never came from production. Here the only input is the
schema.

**Who:** teams in healthcare, finance and the public sector, and anyone a
security review asks "where did this data come from?"
**Time:** about a second for 12,000 rows.

## The input

`schema.sql` is the production DDL. Names, emails, dates of birth and
postcodes are columns in it, never values:

```sql
CREATE TABLE patients (
  patient_id SERIAL PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  email VARCHAR(200) NOT NULL UNIQUE,
  phone VARCHAR(30),
  date_of_birth DATE NOT NULL,
  postcode VARCHAR(10) NOT NULL,
  sex CHAR(1) NOT NULL CHECK (sex IN ('F', 'M', 'X'))
);
CREATE TABLE appointments (
  appointment_id SERIAL PRIMARY KEY,
  patient_id INT NOT NULL REFERENCES patients(patient_id),
  clinic VARCHAR(40) NOT NULL CHECK (clinic IN ('cardiology', 'dermatology', 'oncology', 'orthopaedics', 'general')),
  booked_at TIMESTAMP NOT NULL,
  seen_at TIMESTAMP,
  CHECK (seen_at IS NULL OR seen_at >= booked_at)
);
CREATE TABLE prescriptions (
  prescription_id SERIAL PRIMARY KEY,
  appointment_id INT NOT NULL REFERENCES appointments(appointment_id),
  drug_code VARCHAR(12) NOT NULL,
  quantity INT NOT NULL CHECK (quantity > 0 AND quantity <= 180)
);
```

## Generate the environment

```bash
pip install "misata[duckdb]"
misata generate -c schema.sql -o staging -n 4000 --seed 2024 --attest
```

The rows look like a clinic's: names and matching email addresses, dates of
birth between 1940 and 2007, drug codes such as `DRG952339`, and no
appointment seen before it was booked, because the DDL's
`CHECK (seen_at IS NULL OR seen_at >= booked_at)` is honoured. Load the
same command into the staging database with `--db-url` and `--db-create`.

## The claim, and the proof

```bash
misata provenance staging
```

```text
Made from (attestation.intoto.json)
  producer: pkg:pypi/misata@0.9.8
  schema:   schema.sql sha256 25d030334f317e7b89b5aa1620e3b9778ce3259ac4e993c7bb5e9e7cbc655dea
  seed:     2024
  result:   PASSED, 23 of 23 invariant(s) held
```

The statement it prints above that block says what a reviewer needs to
know: generation from a schema reads no rows, needs no network, and gives
the same bytes for the same version, schema and seed. The last part is
what turns the claim into evidence. Anyone can regenerate the folder from
the DDL and the seed and compare hashes:

```bash
misata generate -c schema.sql -o again -n 4000 --seed 2024
misata provenance again
```

```text
 File               sha256             Rows
 appointments.csv   d747932d492e92b1  4,000
 patients.csv       186cc55131663baf  4,000
 prescriptions.csv  74e37add660ea431  4,000
```

Identical hashes mean the schema and the seed were the whole input:
nothing else, production included, could have shaped a byte.

## What to hand the reviewer

| Artifact | What it shows |
|---|---|
| `schema.sql` and its sha256 | the only input |
| `staging/attestation.intoto.json` | Misata version, seed and the schema hash, plus 23 checks that passed: keys, uniques, NOT NULL, the clinic list, and the appointment ordering |
| `misata provenance staging --json` | the statement, the attested inputs and every file's hash, as one JSON record |
| a regeneration with matching hashes | that nothing else went in |

Never use `misata mimic` for this. It fits to real rows, its output is not
anonymous, and `misata provenance` says so for any folder it wrote.

## The check

```bash
python staging/verify.py
misata audit staging
```

```text
ok    3 file(s) match their attested sha256
ok    23 of 23 invariant(s) hold
✓ Coherence: clean, no reader-visible contradictions.
```

`misata realism staging` still warns twice: appointments are spread evenly
over the week, and optional columns are never empty. DDL cannot say a
clinic is closed at weekends or how often a phone number is missing; a
`misata.yaml` with `weekday_weights` and `missingness` can.

## Related

- [SQL DDL to schema](../guides/from-ddl.md): every DDL rule Misata reads, including null-guarded CHECKs
- [Seed a live database](../guides/seed-a-live-database.md): `--db-url` and `--db-create` in detail
- [CLI reference](../cli.md#misata-provenance): `misata provenance` and its `--json` record
- [Security model](../security.md): what Misata reads, writes and sends
- [Mimic](../guides/mimic.md): the one path that reads real rows, and why it is not anonymous

## Files

The recipe folder runs as it is. Its files on GitHub:

- [`schema.sql`](https://github.com/rasinmuhammed/misata/blob/main/examples/usecases/pii-free-environments/schema.sql)
