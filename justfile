set dotenv-load

# List available recipes
default:
    @just --list

# Sync runtime dependencies into .venv
sync:
    uv sync --frozen --no-dev

# Sync all dependency groups (local/dev)
sync-dev:
    uv sync --frozen --all-groups

# Create/refresh the local environment with all groups
setup:
    uv sync --all-groups

# Run a service: just run mqtt_gpio
run service:
    PYTHONPATH=src uv run python src/services/{{ service }}/main.py

# Install a systemd unit for a service
install service:
    #!/usr/bin/env bash
    set -euo pipefail
    source_unit="src/services/{{ service }}/{{ service }}.service"
    destination_unit="/etc/systemd/system/{{ service }}.service"
    service_user="${SUDO_USER:-$(id -un)}"
    repo_dir="$(pwd -P)"

    if [[ "$repo_dir" == *[!A-Za-z0-9_./-]* ]]; then
        echo "Unsupported repository path for systemd units: $repo_dir" >&2
        echo "Use a path containing only letters, numbers, '.', '_', '-', and '/'." >&2
        exit 1
    fi

    rendered_unit="$(mktemp)"
    trap 'rm -f "$rendered_unit"' EXIT

    escaped_user="$(printf '%s' "$service_user" | sed 's/[\\&|]/\\&/g')"
    escaped_repo_dir="$(printf '%s' "$repo_dir" | sed 's/[\\&|]/\\&/g')"
    sed \
        -e "s|@SERVICE_USER@|$escaped_user|g" \
        -e "s|@REPO_DIR@|$escaped_repo_dir|g" \
        "$source_unit" > "$rendered_unit"

    sudo install -m 0644 "$rendered_unit" "$destination_unit"
    sudo systemctl daemon-reload

# Enable a systemd service
enable service:
    sudo systemctl enable {{ service }}.service

# Disable a systemd service
disable service:
    sudo systemctl disable {{ service }}.service

# Start a systemd service
start service:
    sudo systemctl start {{ service }}.service

# Stop a systemd service
stop service:
    sudo systemctl stop {{ service }}.service

# Restart a systemd service
restart service:
    sudo systemctl restart {{ service }}.service

# Show systemd status for a service
status service:
    sudo systemctl status {{ service }}.service

# Tail journal logs for a service
tail service lines="50":
    clear && sudo journalctl -u {{ service }}.service -f -n {{ lines }}

# Install, enable, and restart a service
setup-service service:
    just install {{ service }}
    just enable {{ service }}
    just restart {{ service }}

[private]
_services:
    #!/usr/bin/env bash
    set -euo pipefail
    find src/services -mindepth 1 -maxdepth 1 -type d ! -name '__pycache__' -exec basename {} \;

# Stop all installed services
stop-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for service in $(just _services); do
        # Prefer a direct unit-file check over `list-unit-files | grep -q`.
        # Under pipefail, an early grep match SIGPIPEs systemctl and treats
        # installed units as missing.
        if [[ -f "/etc/systemd/system/${service}.service" ]]; then
            echo "Stopping ${service}.service"
            just stop "${service}"
        else
            echo "${service}.service is not installed"
        fi
    done

# Status of all services
status-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for service in $(just _services); do
        if [[ -f "/etc/systemd/system/${service}.service" ]]; then
            echo "${service}.service is $(systemctl is-active ${service}.service) and $(systemctl is-enabled ${service}.service)"
        else
            echo "${service}.service is not installed"
        fi
    done

# Reinstall all installed systemd units
reinstall-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for service in $(just _services); do
        if [[ -f "/etc/systemd/system/${service}.service" ]]; then
            echo "Reinstalling ${service}.service"
            just install "${service}"
        else
            echo "${service}.service is not installed"
        fi
    done

# Restart all installed services
restart-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for service in $(just _services); do
        if [[ -f "/etc/systemd/system/${service}.service" ]]; then
            echo "Restarting ${service}.service"
            just restart "${service}"
        else
            echo "${service}.service is not installed"
        fi
    done

# Pull latest main, sync runtime deps, and restart installed services.
# After `just deploy <tag>` (detached HEAD), this switches back to main first.
update:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! git diff --quiet || ! git diff --cached --quiet \
        || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
        echo "Working tree is dirty; commit or stash changes before updating." >&2
        exit 1
    fi
    git fetch --prune origin
    git switch main
    git pull --ff-only origin main
    just sync
    just restart-all

# Install Tailscale (if needed) and join the tailnet using this host's short
# MagicDNS hostname. Create a reusable auth key at
# https://login.tailscale.com/admin/settings/keys then:
#   just setup-tailscale tskey-auth-XXXX
setup-tailscale auth_key:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{ auth_key }}" ]]; then
        echo "Usage: just setup-tailscale tskey-auth-XXXX" >&2
        exit 1
    fi
    if ! command -v tailscale >/dev/null 2>&1; then
        echo "Installing Tailscale…"
        curl -fsSL https://tailscale.com/install.sh | sh
    else
        echo "Tailscale already installed: $(tailscale version | head -n1)"
    fi

    node_hostname="$(hostname -s)"
    echo "Bringing Tailscale up as ${node_hostname}…"
    sudo tailscale up \
        --hostname="${node_hostname}" \
        --accept-dns=true \
        --auth-key="{{ auth_key }}"
    echo
    sudo tailscale status
    echo
    echo "MagicDNS name should match WG_SCRIPTS_HOSTS (e.g. ${node_hostname})."

# Install the shared CI deploy SSH public key into ~/.ssh/authorized_keys.
# Pass a .pub file path or the key line itself (same key on every Pi):
#   just setup-deploy-key ./wg-scripts-deploy.pub
#   just setup-deploy-key 'ssh-ed25519 AAAA... deploy'
setup-deploy-key key:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{ key }}" ]]; then
        echo "Usage: just setup-deploy-key <pubkey-file-or-line>" >&2
        exit 1
    fi

    if [[ -f "{{ key }}" ]]; then
        pubkey="$(tr -d '\n' < "{{ key }}")"
    else
        pubkey="{{ key }}"
    fi

    mkdir -p "${HOME}/.ssh"
    chmod 700 "${HOME}/.ssh"
    touch "${HOME}/.ssh/authorized_keys"
    chmod 600 "${HOME}/.ssh/authorized_keys"

    if grep -qxF "${pubkey}" "${HOME}/.ssh/authorized_keys"; then
        echo "Deploy key already present in ~/.ssh/authorized_keys"
    else
        printf '%s\n' "${pubkey}" >> "${HOME}/.ssh/authorized_keys"
        echo "Installed deploy key into ~/.ssh/authorized_keys"
    fi

# Checkout a release tag (detached), sync runtime deps, and restart services.
# Rejects a dirty tree. Use `just update` later to return to main and pull.
deploy tag:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! git diff --quiet || ! git diff --cached --quiet \
        || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
        echo "Working tree is dirty; commit or stash changes before deploying." >&2
        exit 1
    fi
    git fetch --tags origin
    git switch --detach "{{ tag }}"
    just sync
    just restart-all
