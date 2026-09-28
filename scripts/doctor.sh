#!/usr/bin/env bash
# KVYT diagnostics. Prints one OK/FAIL line per check and, for every FAIL,
# one line on what to do. Exits non-zero if anything failed.

set -u
cd "$(dirname "$0")/.."

SERVICES=(postgres identity catalog booking gateway web)
HTTP_SERVICES=(identity catalog booking gateway web)
failures=0

row() {  # row OK|FAIL "check" "details" ["hint"]
  printf '%-4s  %-32s %s\n' "$1" "$2" "$3"
  if [ "$1" = "FAIL" ]; then
    failures=$((failures + 1))
    [ -n "${4:-}" ] && printf '      %-32s -> %s\n' "" "$4"
  fi
}

# GET a URL from inside a service container; prints "<status> <body>".
http_in() {  # http_in <service> <url>
  docker compose exec -T "$1" python - "$2" 2>/dev/null <<'PY'
import sys, urllib.request, urllib.error
try:
    r = urllib.request.urlopen(sys.argv[1], timeout=3)
    print(r.status, r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
except Exception as e:
    print(0, type(e).__name__)
PY
}

echo "KVYT doctor"
echo

# --- Docker ---------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  row FAIL "Docker" "daemon is not reachable" "Start Docker Desktop and wait until it says 'Engine running', then retry."
  echo; echo "Cannot continue without Docker."; exit 1
fi
row OK "Docker" "$(docker version --format '{{.Server.Version}}')"

compose_version=$(docker compose version --short 2>/dev/null || true)
case "$compose_version" in
  2.*|3.*|4.*) row OK "Docker Compose" "$compose_version" ;;
  "") row FAIL "Docker Compose" "not found" "Install Docker Desktop, it ships Compose v2 ('docker compose')." ;;
  *) row FAIL "Docker Compose" "$compose_version" "Compose v2 or newer is required. Update Docker Desktop." ;;
esac

# --- Ports ----------------------------------------------------------------
check_port() {  # check_port <service> <host port>
  local published holder=""
  published=$(docker compose port "$1" 8000 2>/dev/null | sed 's/.*://')
  if [ "$published" = "$2" ]; then
    row OK "Port $2" "used by KVYT $1"
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    holder=$(lsof -nP -iTCP:"$2" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (PID " $2 ")"}')
  elif command -v nc >/dev/null 2>&1 && nc -z localhost "$2" 2>/dev/null; then
    holder="another process"
  fi
  if [ -n "$holder" ]; then
    row FAIL "Port $2" "taken by $holder" "Stop that process or change the $1 port, see README 'Якщо порт зайнятий'."
  else
    row OK "Port $2" "free"
  fi
}
check_port gateway 8080
check_port web 3000

# --- Containers -----------------------------------------------------------
ps_out=$(docker compose ps -a --format '{{.Service}}|{{.State}}|{{.Health}}|{{.ExitCode}}' 2>/dev/null)
for svc in "${SERVICES[@]}"; do
  line=$(printf '%s\n' "$ps_out" | grep "^$svc|" || true)
  IFS='|' read -r _ state health _ <<<"$line"
  if [ -z "$line" ]; then
    row FAIL "Container $svc" "not created" "Run 'make up'."
  elif [ "$state" = "running" ] && [ "$health" = "healthy" ]; then
    row OK "Container $svc" "running, healthy"
  else
    row FAIL "Container $svc" "${state}${health:+, $health}" "See why: docker compose logs $svc | tail -30"
  fi
done

line=$(printf '%s\n' "$ps_out" | grep "^seed|" || true)
IFS='|' read -r _ state _ exit_code <<<"$line"
if [ -z "$line" ]; then
  row FAIL "Container seed" "not created" "Run 'make up'."
elif [ "$state" = "exited" ] && [ "$exit_code" = "0" ]; then
  row OK "Container seed" "finished"
elif [ "$state" = "running" ]; then
  row FAIL "Container seed" "still running" "Wait a few seconds and run 'make doctor' again."
else
  row FAIL "Container seed" "$state, exit code $exit_code" "See why: docker compose logs seed"
fi

# --- Readiness ------------------------------------------------------------
for svc in "${HTTP_SERVICES[@]}"; do
  read -r code body <<<"$(http_in "$svc" http://localhost:8000/health/ready)"
  if [ "${code:-0}" = "200" ]; then
    row OK "Ready $svc" "$body"
  elif [ "${code:-0}" = "0" ]; then
    row FAIL "Ready $svc" "no response" "The container is not running or not answering: docker compose logs $svc | tail -30"
  else
    row FAIL "Ready $svc" "HTTP $code $body" "A dependency marked 'fail' above is down; fix it first."
  fi
done

# --- catalog <-> booking --------------------------------------------------
for pair in "catalog booking" "booking catalog"; do
  set -- $pair
  read -r code _ <<<"$(http_in "$1" "http://$2:8000/health")"
  if [ "${code:-0}" = "200" ]; then
    row OK "$1 -> $2" "reachable"
  elif [ -z "${code:-}" ]; then
    row FAIL "$1 -> $2" "cannot check, $1 is not running" "Fix the '$1' container first."
  else
    row FAIL "$1 -> $2" "not reachable" "Seats and bookings will fail. Restart both: docker compose restart catalog booking"
  fi
done

# --- Seed data ------------------------------------------------------------
events=$(docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d catalog -Atc "SELECT count(*) FROM events"' 2>/dev/null | tr -d '[:space:]')
if [ -n "$events" ] && [ "$events" -gt 0 ] 2>/dev/null; then
  row OK "Seed data" "$events events"
else
  row FAIL "Seed data" "${events:-unknown} events" "Load reference data: docker compose run --rm seed (or 'make reset' for a clean state)."
fi

# --- BUG_SCENARIO ---------------------------------------------------------
active=""
for svc in "${HTTP_SERVICES[@]}"; do
  read -r code body <<<"$(http_in "$svc" http://localhost:8000/health)"
  [ "${code:-0}" = "200" ] || continue
  names=$(printf '%s' "$body" | python3 -c 'import sys,json; print(",".join(json.load(sys.stdin).get("scenarios", [])))' 2>/dev/null)
  [ -n "$names" ] && active="${active}${active:+; }$svc: $names"
done
row OK "BUG_SCENARIO" "${active:-none active}"

echo
if [ "$failures" -eq 0 ]; then
  echo "All checks passed. Web: http://localhost:3000  Gateway: http://localhost:8080"
else
  echo "$failures check(s) failed. Fix the first FAIL first; later ones often follow from it."
  exit 1
fi
