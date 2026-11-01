#!/usr/bin/env bash
# Update the bot to a tested commit of origin/main and restart it, or put back what worked.
#
# CI runs this over SSH, and it is the only thing the deploy key may run: the key's
# authorized_keys entry forces this script (see deploy/README.md). The commit CI tested
# arrives in SSH_ORIGINAL_COMMAND and is accepted only as a full sha that is on origin/main
# and not behind what is deployed, so a leaked key cannot pin the box to an old tree.
#
# It never touches .env or the data volume: `git reset --hard` leaves ignored files alone.

set -Eeuo pipefail

APP_DIR="${APP_DIR:-/srv/t212-cash-interest-bot}"
CONTAINER="${CONTAINER:-t212-cash-interest-bot}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"

log() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "FAILED: $*"; exit 1; }

health_of() {
	docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
		"$CONTAINER" 2>/dev/null || echo "missing"
}

wait_for_health() {
	local deadline=$(( SECONDS + HEALTH_TIMEOUT ))
	while (( SECONDS < deadline )); do
		case "$(health_of)" in
			healthy) return 0 ;;
			unhealthy) return 1 ;;
		esac
		sleep 5
	done
	log "still '$(health_of)' after ${HEALTH_TIMEOUT}s"
	return 1
}

cd "$APP_DIR" || die "no $APP_DIR"
[[ -f .env ]] || die ".env is missing; see deploy/README.md"

# A hand-run deploy and a CI one must not interleave a reset with a build.
exec {lock}> "$APP_DIR/.deploy.lock"
flock --wait 600 "$lock" || die "another deploy has held the lock for ten minutes"

was_healthy=false
[[ "$(health_of)" == "healthy" ]] && was_healthy=true

previous="$(git rev-parse HEAD)"
git fetch --prune --quiet origin
target="$(git rev-parse origin/main)"
asked="${SSH_ORIGINAL_COMMAND:-}"
if [[ -n "$asked" ]]; then
	if [[ ! "$asked" =~ ^[0-9a-f]{40}$ ]]; then
		log "ignoring a target that is not a full sha; deploying ${target:0:8}"
	elif ! git merge-base --is-ancestor "$asked" "$target" 2>/dev/null; then
		log "ignoring $asked: not on origin/main; deploying ${target:0:8}"
	elif ! git merge-base --is-ancestor "$previous" "$asked" 2>/dev/null; then
		log "ignoring $asked: behind the deployed ${previous:0:8}; deploying ${target:0:8}"
	else
		target="$asked"
	fi
fi

if [[ "$previous" == "$target" ]]; then
	log "already at ${target:0:8}; rebuilding anyway"
else
	log "deploying ${previous:0:8} -> ${target:0:8}"
	git log --oneline --no-decorate "$previous..$target" | sed 's/^/    /'
fi
git reset --hard --quiet "$target"

# Build before touching the running container: a broken build must change nothing.
if ! GIT_SHA="$target" docker compose build --quiet; then
	git reset --hard --quiet "$previous"
	die "build failed; the running version was left alone"
fi

started=true
GIT_SHA="$target" docker compose up -d --remove-orphans || started=false

if $started && wait_for_health; then
	docker image prune --force --filter "dangling=true" >/dev/null 2>&1 || true
	log "deployed ${target:0:8}, container is healthy"
	exit 0
fi

if ! $was_healthy; then
	log "not healthy, but it was not healthy before this deploy either; leaving ${target:0:8}"
	log "check 'docker logs $CONTAINER'"
	exit 1
fi

log "unhealthy after the deploy; rolling back to ${previous:0:8}"
git reset --hard --quiet "$previous"
GIT_SHA="$previous" docker compose up -d --build --remove-orphans
wait_for_health && die "rolled back to ${previous:0:8}, which is healthy again"
die "rolled back to ${previous:0:8} and it is STILL unhealthy"
