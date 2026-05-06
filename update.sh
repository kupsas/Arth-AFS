#!/usr/bin/env bash
# =============================================================================
# update.sh — Pull the latest Arth version and rebuild Docker containers
#
# WHAT IT DOES
#   1. Checks that git and docker are available
#   2. Fetches the latest commits from GitHub without changing anything local
#   3. If you're already on the latest version, exits cleanly
#   4. If a new version is available, asks for confirmation then:
#      a. Pulls the latest code via git pull
#      b. Rebuilds and restarts Docker containers with docker compose up --build
#
# USAGE
#   From the repo root:
#     bash update.sh
#
#   Or make it executable once and run directly:
#     chmod +x update.sh
#     ./update.sh
#
# NOTE
#   Your data (transactions, settings, Gmail connection) is stored in a Docker
#   volume and is NOT affected by this update. Only the app code changes.
# =============================================================================

set -euo pipefail

# ── Resolve repo root (works whether you run ./update.sh or bash update.sh) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours (only if the terminal supports it) ────────────────────────────────
if [ -t 1 ] && command -v tput &>/dev/null && tput colors &>/dev/null; then
    GREEN="$(tput setaf 2)"
    YELLOW="$(tput setaf 3)"
    RED="$(tput setaf 1)"
    BOLD="$(tput bold)"
    RESET="$(tput sgr0)"
else
    GREEN="" YELLOW="" RED="" BOLD="" RESET=""
fi

# ── Logging helpers ───────────────────────────────────────────────────────────
info()    { echo "${BOLD}${GREEN}✔${RESET} $*"; }
warn()    { echo "${BOLD}${YELLOW}!${RESET} $*"; }
error()   { echo "${BOLD}${RED}✘${RESET} $*" >&2; }
section() { echo; echo "${BOLD}$*${RESET}"; }

# ── Pre-flight: git ───────────────────────────────────────────────────────────
section "Checking requirements..."

if ! command -v git &>/dev/null; then
    error "git is not installed. Please install git and try again."
    exit 1
fi
info "git found"

# ── Pre-flight: docker ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Download Docker Desktop from https://docs.docker.com/get-docker/"
    exit 1
fi
info "docker found"

# Check the Docker daemon is actually running (not just installed)
if ! docker info &>/dev/null 2>&1; then
    error "Docker Desktop doesn't appear to be running. Please start it and try again."
    exit 1
fi
info "Docker daemon is running"

# ── Check for updates ─────────────────────────────────────────────────────────
section "Checking for updates..."

# Fetch quietly — this contacts GitHub but doesn't change any local files
git fetch origin main --quiet

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    info "You're already on the latest version. Nothing to do."
    echo
    exit 0
fi

# Count how many commits are incoming
COMMIT_COUNT="$(git rev-list HEAD..origin/main --count)"
warn "Your Arth is ${COMMIT_COUNT} commit(s) behind the latest version."

# Show a summary of what's new (one line per commit, newest first)
echo
echo "What's new:"
git log HEAD..origin/main --oneline --no-decorate | head -10
echo

# ── Confirm before changing anything ─────────────────────────────────────────
read -r -p "${BOLD}Update now?${RESET} Your data will not be affected. [y/N] " REPLY
echo

case "$REPLY" in
    [Yy]|[Yy][Ee][Ss]) ;;
    *)
        warn "Update cancelled. Run this script again whenever you're ready."
        exit 0
        ;;
esac

# ── Pull latest code ──────────────────────────────────────────────────────────
section "Pulling latest code..."
git pull origin main
info "Code updated"

# ── Rebuild and restart containers ────────────────────────────────────────────
section "Rebuilding Docker containers (this may take a few minutes)..."

# -d = detached (run in background so your terminal stays free)
# --build = re-read Dockerfiles to pick up code and dependency changes
docker compose up --build -d

info "Containers rebuilt and running"

# ── Done ─────────────────────────────────────────────────────────────────────
echo
echo "${BOLD}${GREEN}Arth is updated!${RESET} Open http://localhost:3000 in your browser."
echo
echo "To watch live logs: ${BOLD}docker compose logs -f${RESET}"
echo
