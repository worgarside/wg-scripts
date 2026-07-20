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

On each Pi (over LAN SSH is fine for bootstrap):

1. Ensure the hostname is the short MagicDNS name you want (`crtpi`, `growpi`,
   `mtrxpi`, `octopi`, `rtropi`, `vsmppi`):

   ```bash
   sudo hostnamectl set-hostname crtpi
   ```

2. Join the tailnet (create a reusable auth key in the
   [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)):

   ```bash
   just setup-tailscale tskey-auth-XXXX
   ```

3. Install the shared deploy SSH public key into `~pi/.ssh/authorized_keys`
   (CI uses one `DEPLOY_SSH_PRIVATE_KEY`, not per-host personal keys).

4. Repo at `/home/pi/wg-scripts` with `just`, `uv`, and `git` already set up.

Also ensure the Tailscale ACL allows `tag:ci` to SSH to these nodes (same
client used by backplane CI).

### `production-deploy` environment

| Kind | Name | Notes |
|------|------|--------|
| Secret | `TS_OAUTH_CLIENT_ID` | Same Tailscale OAuth client as backplane CI |
| Secret | `TS_OAUTH_SECRET` | Same |
| Secret | `DEPLOY_SSH_PRIVATE_KEY` | Private key matching the shared deploy key on each Pi |
| Var | `DEPLOY_SSH_USER` | `pi` (install path `/home/pi/wg-scripts`) |
| Var | `WG_SCRIPTS_HOSTS` | Comma-separated MagicDNS hostnames, e.g. `crtpi,growpi,mtrxpi,octopi,rtropi,vsmppi` |
