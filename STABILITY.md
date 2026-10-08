# Stability policy

> **Status: adopted, October 2026.** Release cadence, the Output changes
> changelog section and the deprecation window apply from 0.9.7. Semantic
> versioning and the cross-version guarantees below apply from 1.0; until
> then a MINOR bump (0.9 to 0.10) may break, and is announced as Breaking in
> the changelog.

A test-data library is something people pin in CI and regenerate fixtures
from months later. That only works if what changes between versions is
predictable. This page says what Misata guarantees across versions, what it
does not, and how changes are announced.

## Versioning

From 1.0, versions are `MAJOR.MINOR.PATCH`, as in
[Semantic Versioning](https://semver.org):

| Bump | May contain | Never contains |
|---|---|---|
| PATCH (1.4.**2**) | bug fixes that do not change generated rows for a valid schema | new features, changed output bytes, removed or renamed API |
| MINOR (1.**5**.0) | new declarations, new defaults, realism improvements, changed output bytes (announced) | removed or renamed public API, a valid schema becoming invalid |
| MAJOR (**2**.0.0) | removals and breaking changes, each listed with a migration note | changes without a migration note |

The four-part pre-1.0 versions (`0.9.6.60`) end at 1.0.

## Release cadence

Releases are batched: at most one MINOR a fortnight, and a PATCH only when a
fix is worth shipping on its own. Several fixes a day go into one release, not
several. A release that changes generated output says so in a dedicated
**Output changes** section of the changelog, naming the columns or
declarations affected.

## What holds across versions

These hold for any schema that was valid in the version it was written for,
across every MINOR and PATCH release of the same MAJOR:

- **Declared outcomes.** A declared curve total, rate, share, retention,
  roll-up, lifecycle, ledger identity or event-log correspondence comes out
  exactly as declared, and the story audit and `misata.conformance` check it
  from the rows, independently of the generator.
- **Integrity.** Zero foreign-key orphans; unique columns are unique;
  declared widths, ranges and choices hold.
- **The schema language.** A valid YAML or dict schema stays valid. A
  declaration that has to change is deprecated first (below), never silently
  reinterpreted.
- **The public API.** Names in `misata.__all__` and documented CLI commands
  and flags keep working.

## What may change

- **Individual rows.** The same schema and seed produce byte-identical output
  within one MINOR series (all 1.5.x). A MINOR release may change rows: new
  realism defaults, better priors, fixed bugs. Pin the MINOR version
  (`misata~=1.5.0`) when exact bytes matter; record the version with any
  fixture you check in. `misata.fingerprint(tables)` gives one canonical
  hash per table and for the whole dataset (independent of file format and
  dtype); check it into your fixtures to detect any change. Misata's own CI
  regenerates a set of story, dict and DDL schemas on Linux, macOS and
  Windows and requires the same fingerprints on all three
  (`python -m benchmarks.golden`).
- **Undeclared defaults.** Anything you did not declare (a distribution
  Misata chose, a time-of-day rhythm, popularity weighting) is a default, and
  defaults improve. Declare it to make it a guarantee.
- **Warnings and messages.** Wording is not API.

## Deprecation

A public name, CLI flag or schema key that is going away first emits a
`DeprecationWarning` naming its replacement, for at least two MINOR releases,
and is removed only in the next MAJOR. The changelog lists every deprecation
under **Deprecated**.

## Checklist before 1.0

- [x] Adopt this page.
- [x] Three-part versions (0.9.7) and batched releases.
- [x] Changelog notes carry **Output changes** and **Breaking** sections.
- [x] Duplicate exports removed from `misata.__all__`.
- [ ] Decide which of the ~160 names in `misata.__all__` are public at 1.0;
      deprecate the rest with a warning first.
- [ ] Re-check the `Development Status` classifier against this policy at 1.0.
