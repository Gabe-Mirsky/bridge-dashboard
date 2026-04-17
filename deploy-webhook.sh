#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/bridge-dashboard}"
APP_BRANCH="${APP_BRANCH:-main}"
APP_SERVICE="${APP_SERVICE:-bridge-dashboard}"

cd "${APP_DIR}"

git fetch origin "${APP_BRANCH}"
git checkout "${APP_BRANCH}"
git pull --ff-only origin "${APP_BRANCH}"
sudo systemctl restart "${APP_SERVICE}"
