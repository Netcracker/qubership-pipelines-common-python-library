#!/bin/bash
set -e

MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
MC_SHA256=01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891
curl -fsSL -o ./mc "https://github.com/minio/mc/releases/download/${MC_RELEASE}/mc.linux-amd64.${MC_RELEASE}"
echo "${MC_SHA256}  ./mc" | sha256sum -c -
chmod +x ./mc
./mc alias set minio http://127.0.0.1:9000 "$MINIO_USER" "$MINIO_PASSWORD"
./mc mb --ignore-existing minio/integration-test-bucket
