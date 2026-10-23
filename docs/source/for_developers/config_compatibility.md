# config.json Compatibility

`Case.configure_forcings()` writes `<inputdir>/extract_forcings/config.json`.
`process_forcings()`, `crocodash process` and `crocodash dump` read it back,
often with a newer CrocoDash than the one that wrote it. This page explains
how to change a configurator without breaking the cases that already exist.

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
- **Output missing from the entry:** it stays `None`.
- **Key the class no longer declares:** it is ignored.
- **Entry that fails `validate_args`:** `ReconfigureRequired` is raised.

So you can usually add an input (give it a default) or an output without
touching the version. Only `validate_args` should reject bad inputs. A check
that only matters when a step runs, such as "this input file exists", belongs
in `configure()` (as a warning) or in the process step. `validate_args` also
runs when config.json is read back, possibly on another machine.

## When to bump the version

Bump the MINOR of `CONFIG_SCHEMA_VERSION` when tolerant reading would
*misread* an old file. Renaming a param is the usual case: the old value would
be ignored, and the new param would silently take its default. In the same PR:

1. Add a migration to `CONFIG_MIGRATIONS`, keyed by the version it upgrades
   from (`"1.0"`), that rewrites the old layout.
2. Add a config.json from a real case to `tests/forcing/golden_configs/` if
   none of the existing ones covers the change.

The golden configs in `tests/forcing/golden_configs/` are config.json files
real cases wrote, with personal paths replaced. Every one must keep loading.
