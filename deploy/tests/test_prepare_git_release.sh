#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREPARE="${SCRIPT_DIR}/../common/prepare_git_release.sh"
tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp}"' EXIT

work="${tmp}/work"
origin="${tmp}/origin.git"
remote="${tmp}/remote"
mkdir -p "${work}"
git -C "${work}" init -b main >/dev/null
git -C "${work}" config user.name "ma3 deploy test"
git -C "${work}" config user.email "deploy-test@example.invalid"
printf 'one\n' >"${work}/version.txt"
git -C "${work}" add version.txt
git -C "${work}" commit -m one >/dev/null
first="$(git -C "${work}" rev-parse HEAD)"
git clone --bare "${work}" "${origin}" >/dev/null 2>&1

bash "${PREPARE}" "${remote}" "${origin}" refs/heads/main "${first}"
test "$(cat "${remote}/releases/${first}/version.txt")" = one
test "$(cat "${remote}/releases/${first}/.ma3-release-commit")" = "${first}"
bash "${PREPARE}" "${remote}" "${origin}" refs/heads/main "${first}" >/dev/null

printf 'two\n' >"${work}/version.txt"
git -C "${work}" add version.txt
git -C "${work}" commit -m two >/dev/null
second="$(git -C "${work}" rev-parse HEAD)"
git -C "${work}" push "${origin}" main >/dev/null

bash "${PREPARE}" "${remote}" "${origin}" refs/heads/main "${second}"
test "$(cat "${remote}/releases/${second}/version.txt")" = two
test "$(cat "${remote}/releases/${first}/version.txt")" = one

git -C "${work}" switch --orphan side >/dev/null
printf 'side\n' >"${work}/version.txt"
git -C "${work}" add version.txt
git -C "${work}" commit -m side >/dev/null
side="$(git -C "${work}" rev-parse HEAD)"
git -C "${work}" push "${origin}" side >/dev/null
if bash "${PREPARE}" "${remote}" "${origin}" refs/heads/main "${side}" >/dev/null 2>&1; then
  echo "commit outside configured ref unexpectedly accepted" >&2
  exit 1
fi

if bash "${PREPARE}" "${remote}" "${origin}" refs/heads/main deadbeef >/dev/null 2>&1; then
  echo "short SHA unexpectedly accepted" >&2
  exit 1
fi

echo "prepare_git_release tests passed"
