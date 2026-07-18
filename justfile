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
    uv run python src/services/{{ service }}/main.py

# Install a systemd unit for a service
install service:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo cp "src/services/{{ service }}/{{ service }}.service" /etc/systemd/system/
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
    ls -d src/services/*/ | cut -f3 -d'/'

# Stop all installed services
stop-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for service in $(just _services); do
        if sudo systemctl list-unit-files | grep -q "${service}.service"; then
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
        if sudo systemctl list-unit-files | grep -q "${service}.service"; then
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
        if sudo systemctl list-unit-files | grep -q "${service}.service"; then
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
        if sudo systemctl list-unit-files | grep -q "${service}.service"; then
            echo "Restarting ${service}.service"
            just restart "${service}"
        else
            echo "${service}.service is not installed"
        fi
    done

# Pull latest, sync runtime deps, and restart installed services
update:
    #!/usr/bin/env bash
    set -euo pipefail
    git add .
    git stash push -m "Stash before update @ $(date)" || true
    git pull --prune
    just sync
    just restart-all

# Checkout a tag, sync runtime deps, and restart installed services
deploy tag:
    git fetch --tags origin
    git reset --hard {{ tag }}
    just sync
    just restart-all
