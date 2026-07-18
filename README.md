# wg-scripts

Raspberry Pi services for MQTT, GPIO, DHT22, and system stats.

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
```

Install [prek](https://github.com/j178/prek) hooks:

```bash
uv tool install prek
prek install
```

Common just recipes:

```bash
just setup              # sync all dependency groups
just run mqtt_gpio      # run a service locally
just sync               # runtime deps only (Pi deploy)
just update             # switch to main, ff-only pull, sync, restart
just deploy 1.3.1       # dirty-check, checkout tag (detached), sync, restart
```

Linting and typechecking are enforced via prek (ruff + basedpyright). Commits
should follow [Conventional Commits](https://www.conventionalcommits.org/);
releases are cut by python-semantic-release on `main`.
