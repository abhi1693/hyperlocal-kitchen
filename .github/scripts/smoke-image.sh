#!/usr/bin/env bash
set -euo pipefail
image="${1:?image reference is required}"
case "${CI_IMAGE_COMPONENT:?component is required}" in
  backend)
    docker run --rm --entrypoint python \
      -e KITCHEN_ENVIRONMENT=test \
      -e KITCHEN_DATABASE_URL=postgresql+psycopg://ci:ci@database.invalid/kitchen_test \
      -e KITCHEN_REDIS_URL=redis://redis.invalid/15 \
      "$image" -c '
import os
import ssl
import psycopg
import cryptography
import uvloop
import httptools
from kitchen_api.main import create_app
from kitchen_admin_api.main import create_app as create_admin_app
import kitchen_worker.main
assert os.getuid() == 10001
assert create_app().openapi()["paths"]
assert create_admin_app().openapi()["paths"]
'
    ;;
  admin)
    docker run --rm --entrypoint node "$image" -e '
const fs = require("node:fs");
if (!fs.existsSync("apps/admin/server.js")) throw new Error("Standalone server missing");
if (!fs.existsSync("apps/admin/.next/static")) throw new Error("Static assets missing");
const version = require("next/package.json").version;
if (!version) throw new Error("Next.js runtime missing");
if (process.getuid() !== 1000) throw new Error("Runtime must be non-root");
if (fs.existsSync("/usr/local/lib/node_modules/npm")) throw new Error("npm in runtime");
'
    ;;
  *) echo 'Unknown component' >&2; exit 1 ;;
esac
