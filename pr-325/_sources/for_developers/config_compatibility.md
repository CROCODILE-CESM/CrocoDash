# config.json Compatibility

`Case.configure_forcings()` writes `<inputdir>/extract_forcings/config.json`.
`process_forcings()`, `crocodash process` and `crocodash dump` read it back,
often with a newer CrocoDash than the one that wrote it. This page explains
how to change a configurator without breaking the cases that already exist.

This is about cases this CrocoDash can read at all. Reading a case starts with
its `_crocodash_state.json`, and a case whose state file is older than this
CrocoDash supports is refused before its config.json is read: it has to be
recreated. Tolerant reading keeps the cases it accepts working as configurators
gain inputs and outputs.

## Reading and writing

Always go through `read_config(path)` and `write_config(path, config)` in
`CrocoDash/forcing/base.py`. Never call `json.load` on config.json directly.
`read_config` does two things:

- it upgrades the file through `CONFIG_MIGRATIONS`;
- it checks its `schema_version` against `CONFIG_SCHEMA_VERSION`. MAJOR.MINOR
  must match, and a file written before versioning counts as `1.0.0`.

A test fails if a module builds a config.json path on its own.

## Tolerant reading

`BaseConfigurator.deserialize` reads each configurator's entry tolerantly:

- **Input missing from the entry:** it takes the constructor's default. If the
  input has no default, `ReconfigureRequired` is raised.
- **Input missing from the entry whose default is `None`:** `None` is often a
  placeholder that `configure_forcings()` fills in from the case, the run dates
  or the product (a calendar, a start date). Unless the input is declared
  `optional=True`, reading it raises `ReconfigureRequired`.
- **Output missing from the entry:** reading it raises `ReconfigureRequired`.
- **Key the class no longer declares:** it is ignored.
- **Entry the constructor rejects** (`ValueError` or `TypeError` from
  `validate_args`), **or an entry for a configurator that no longer exists:**
  `ReconfigureRequired` is raised.

The entry still loads in the two "reading it raises" cases, so the steps that
don't need the missing value still run, and the one that does asks for
`configure_forcings()` again instead of failing on a `None`.

So you can usually add an input or an output without touching the version:

- give a new input a default;
- declare it `optional=True` only if the configurator really works with it
  left `None` (e.g. CICE's `cice_product_name`: `None` means no restoring).

Only `validate_args` should reject bad inputs, and it runs again whenever
config.json is read back, possibly on another machine. So it doesn't check that
input files exist. `BaseConfigurator.configure()` warns about every
`InputFileParam` whose file is missing, and processing raises when a step needs
one.

## When to bump the version

Bump the MINOR of `CONFIG_SCHEMA_VERSION` when tolerant reading would
*misread* an old file. Renaming a param is the usual case: the old value would
be ignored, and the new param would silently take its default. In the same PR:

Add a migration to `CONFIG_MIGRATIONS`, keyed by the version it upgrades from
(`"1.0"`), that rewrites the old layout and sets `schema_version` to the new
version. `read_config` raises if a migration leaves the version unchanged.
