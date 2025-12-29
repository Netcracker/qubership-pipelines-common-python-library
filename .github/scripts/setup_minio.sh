#!/bin/bash
set -e
wget -q https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x ./mc
./mc alias set minio http://127.0.0.1:9000 "$MINIO_USER" "$MINIO_PASSWORD"
./mc mb --ignore-existing minio/integration-test-bucket
