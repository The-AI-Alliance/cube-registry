#!/usr/bin/env bash
# Long-term slow-check runner prototype.
#   debug_run.sh <pip_target> <cube_id> <offline|docker>
# Runs the canonical `cube test <cube_id>` inside a creds-free sandbox.
# offline: plain sandbox. docker: sandbox wired to an isolated DinD daemon.
set -uo pipefail

PIP_TARGET="$1"; CUBE_ID="$2"; MODE="${3:-offline}"
NET=cube-slowcheck-net; DIND=slowcheck-dind; SANDBOX_IMG=python:3.12-slim
DOCKER_HOST_ARGS=()

cleanup() {
  docker rm -f "$DIND" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

if [ "$MODE" = "docker" ]; then
  echo "--- start isolated DinD ---"
  docker network create "$NET" >/dev/null
  docker run -d --privileged --name "$DIND" --network "$NET" --network-alias dind \
    -e DOCKER_TLS_CERTDIR= docker:27-dind dockerd --host=tcp://0.0.0.0:2375 >/dev/null
  for i in $(seq 1 30); do
    docker exec "$DIND" docker -H tcp://localhost:2375 info >/dev/null 2>&1 && { echo "   DinD ready (${i}s)"; break; }
    sleep 1
  done
  DOCKER_HOST_ARGS=(--network "$NET" -e DOCKER_HOST=tcp://dind:2375)
fi

# In docker mode the sandbox needs the `docker` CLI on PATH so the cube's
# LocalInfraConfig.capabilities() detects docker (shutil.which) and shells
# `docker pull` to the DinD daemon. Static client binary only (no daemon).
CLI_PREP=":"
if [ "$MODE" = "docker" ]; then
  CLI_PREP="apt-get install -y -qq --no-install-recommends curl >/dev/null && \
    curl -fsSL https://download.docker.com/linux/static/stable/\$(uname -m)/docker-27.5.1.tgz \
    | tar xz -C /usr/local/bin --strip-components=1 docker/docker && docker --version"
fi

echo "--- run cube test '$CUBE_ID' in sandbox (mode=$MODE, NO host creds) ---"
docker run --rm ${DOCKER_HOST_ARGS[@]+"${DOCKER_HOST_ARGS[@]}"} \
  --memory 6g --cpus 4 --pids-limit 1024 \
  --cap-drop SYS_PTRACE --cap-drop SYS_ADMIN --security-opt no-new-privileges \
  "$SANDBOX_IMG" \
  bash -c "set -e
    apt-get update -qq && apt-get install -y -qq --no-install-recommends git ca-certificates >/dev/null
    $CLI_PREP
    pip install --quiet '$PIP_TARGET'
    echo '=== cube test ==='
    cube test '$CUBE_ID'"
echo "--- runner exit: $? ---"
