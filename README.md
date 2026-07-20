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
just setup-tailscale KEY  # install Tailscale and join the tailnet
just setup-deploy-key FILE_OR_LINE  # install CI deploy SSH public key
```

Linting and typechecking are enforced via prek (ruff + basedpyright). Commits
should follow [Conventional Commits](https://www.conventionalcommits.org/);
releases are cut by python-semantic-release on `main`.

## Auto-deploy on release

After a successful semantic-release tag (or a manual workflow run with
`publish-tag`), GitHub Actions joins Tailscale as an ephemeral `tag:ci` node
and SSHs to each Pi’s MagicDNS name to run `just deploy <tag>`.

Unreachable hosts are warned and skipped (partial failure does not fail the
job). If every host fails, the job fails so systemic issues (bad key, Tailscale,
missing tag) surface. Redeploy an existing tag via **Actions → Semantic
Release → Run workflow** with `publish-tag` set (for example `2.0.0`) — that
skips cutting a new release.

### One-time Pi setup

On each Pi (LAN SSH is fine for bootstrap). Create a reusable auth key in the
[Tailscale admin console](https://login.tailscale.com/admin/settings/keys), then:

```bash
just setup-tailscale tskey-auth-XXXX
just setup-deploy-key ./wg-scripts-deploy.pub
```

`setup-deploy-key` accepts a `.pub` file path or the key line itself (same key on
every Pi; CI uses one `DEPLOY_SSH_PRIVATE_KEY`). Keep the repo at
`/home/pi/wg-scripts` with `just` / `uv` / `git`, and allow `tag:ci` to SSH
these nodes in the Tailscale ACL (same client as backplane CI).

### `production-deploy` environment

| Kind | Name | Notes |
|------|------|--------|
| Var | `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID (`tag:ci`) |
| Secret | `TS_OAUTH_SECRET` | Matching OAuth client secret |
| Secret | `DEPLOY_SSH_PRIVATE_KEY` | Private key matching the shared deploy key on each Pi |
| Var | `DEPLOY_SSH_USER` | `pi` (install path `/home/pi/wg-scripts`) |
| Var | `WG_SCRIPTS_HOSTS` | Comma-separated MagicDNS hostnames, e.g. `crtpi,growpi,mtrxpi,octopi,rtropi,vsmppi` |
