#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp}"' EXIT

mkdir -p "${tmp}/bin"
cat >"${tmp}/bin/ssh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
count_file="${FAKE_SSH_COUNT_FILE:?}"
count="$(cat "${count_file}" 2>/dev/null || echo 0)"
printf '%s\n' "$((count + 1))" >"${count_file}"
if [[ "${count}" == "0" ]]; then
  [[ "${FAKE_REMOTE_PREPARE_EXISTS:-0}" == "1" ]] && exit 0
  exit 1
fi
if [[ "${count}" == "1" ]]; then
  while [[ "$#" -gt 0 && "$1" != "bash" ]]; do shift; done
  [[ "$#" -gt 0 ]] || { echo "missing remote bash command" >&2; exit 1; }
  shift
  exec /bin/bash "$@"
fi
cat >/dev/null
SH
chmod +x "${tmp}/bin/ssh"

cat >"${tmp}/deploy.env" <<EOF
DEPLOY_PROFILE=test-git-source
REMOTE_HOST=fake-host
REMOTE_USER=test
REMOTE_DIR=${tmp}/remote
ALLOWED_HOSTS=fake-host
ENV_MODE=preserve
GIT_REPO_URL=${REPO_DIR}
GIT_REF=refs/heads/main
RUN_VERIFY=0
BLUE_GREEN=0
EXPECT_INSTANCE_ID=test
EXPECT_PUBLIC_BASE_URL=https://example.invalid
EOF

head_sha="$(git -C "${REPO_DIR}" rev-parse HEAD)"
FAKE_SSH_COUNT_FILE="${tmp}/ssh-count" PATH="${tmp}/bin:${PATH}" \
  "${REPO_DIR}/deploy/deploy.sh" "${tmp}/deploy.env" >"${tmp}/deploy.out"

test "$(cat "${tmp}/remote/releases/${head_sha}/.ma3-release-commit")" = "${head_sha}"
grep -q 'source=git' "${tmp}/deploy.out"
grep -q 'remote fetch refs/heads/main' "${tmp}/deploy.out"
test "$(cat "${tmp}/ssh-count")" = 3

mkdir -p "${tmp}/remote/current/deploy/common"
cp "${REPO_DIR}/deploy/common/prepare_git_release.sh" \
  "${tmp}/remote/current/deploy/common/prepare_git_release.sh"
chmod +x "${tmp}/remote/current/deploy/common/prepare_git_release.sh"
printf '0\n' >"${tmp}/ssh-count"
FAKE_REMOTE_PREPARE_EXISTS=1 FAKE_SSH_COUNT_FILE="${tmp}/ssh-count" \
  PATH="${tmp}/bin:${PATH}" \
  "${REPO_DIR}/deploy/deploy.sh" "${tmp}/deploy.env" >"${tmp}/deploy-reuse.out"
grep -q 'reuse release' "${tmp}/deploy-reuse.out"
test "$(cat "${tmp}/ssh-count")" = 3

echo "deploy git source tests passed"
