#!/usr/bin/env bash
# Prototype: prove a creds-free sandbox container can drive an ISOLATED nested
# Docker-in-Docker daemon — no host docker.sock, no host credentials.
#
#   host docker (colima/CI runner)
#   ├── dind          (privileged, isolated, tcp://0.0.0.0:2375 on a private net)
#   └── sandbox       (no creds, DOCKER_HOST=tcp://dind:2375)
#         └── launches its task containers INSIDE dind
set -uo pipefail

NET=cube-slowcheck-net
DIND=slowcheck-dind
SANDBOX_IMG=python:3.12-slim

cleanup() {
  echo "--- teardown ---"
  docker rm -f "$DIND" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup  # clean any prior run

echo "--- 1. private network ---"
docker network create "$NET" >/dev/null

echo "--- 2. start DinD (privileged, isolated, no TLS, tcp:2375) ---"
docker run -d --privileged --name "$DIND" \
  --network "$NET" --network-alias dind \
  -e DOCKER_TLS_CERTDIR= \
  docker:27-dind dockerd --host=tcp://0.0.0.0:2375 >/dev/null

echo "--- 3. wait for DinD ready ---"
for i in $(seq 1 30); do
  if docker exec "$DIND" docker -H tcp://localhost:2375 info >/dev/null 2>&1; then
    echo "   DinD ready after ${i}s"; break
  fi
  sleep 1
done

echo "--- 4. sandbox (NO creds, NO host socket) drives DinD via py SDK ---"
docker run --rm --network "$NET" \
  -e DOCKER_HOST=tcp://dind:2375 \
  --memory 4g --cpus 2 --pids-limit 512 \
  --cap-drop NET_ADMIN --cap-drop SYS_PTRACE --cap-drop SYS_ADMIN \
  --security-opt no-new-privileges \
  "$SANDBOX_IMG" \
  bash -c "pip install --quiet docker && python -c \"
import docker
c = docker.DockerClient(base_url='tcp://dind:2375')
out = c.containers.run('alpine', 'echo HELLO_FROM_DIND', remove=True)
print('sandbox→dind launched container, output:', out.decode().strip())
print('dind containers seen by sandbox:', [i.short_id for i in c.images.list()][:3])
\""
RC=$?
echo "--- sandbox exit: $RC ---"
exit $RC
