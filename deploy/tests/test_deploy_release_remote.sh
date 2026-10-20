#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "${tmp}"' EXIT

remote="${tmp}/remote"
release="${remote}/releases/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
mkdir -p "${release}"
cat >"${remote}/ma3.env" <<'EOF'
MA3_DEV_AUTH=0
MA3_INSTANCE_ID=test
MA3_PUBLIC_BASE_URL=https://example.invalid
EOF
printf '%s\n' bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb >"${release}/.ma3-release-commit"

set +e
output="$(bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
  "${remote}" "${release}" git aaaaaaa aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  8000 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
  "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1)"
status=$?
set -e

test "${status}" -ne 0
grep -q 'release marker does not match' <<<"${output}"

# Dependency install must use the release venv's CPU-only helper, and a failed
# install must not move `current` or persist the deployed commit.
full_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
printf '%s\n' "${full_sha}" >"${release}/.ma3-release-commit"
mkdir -p "${release}/code/server/scripts" "${tmp}/bin"
cp "${REPO_DIR}/code/server/scripts/pip_install_requirements.sh" \
  "${release}/code/server/scripts/pip_install_requirements.sh"
cat >"${tmp}/bin/python3" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
log="${FAKE_PYTHON_LOG:?}"
if [[ "$0" == */* ]]; then
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
else
  self="$(command -v "$0")"
fi
printf '%s %s\n' "${self}" "$*" >>"${log}"
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  dest="${3:?}"
  mkdir -p "${dest}/bin"
  cp "${self}" "${dest}/bin/python"
  chmod +x "${dest}/bin/python"
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "pip" ]]; then
  # Stop before process restart / cutover. Never invoke a real installer.
  if [[ "$*" == *"-r requirements.txt"* ]]; then
    exit 1
  fi
  exit 0
fi
if [[ "${1:-}" == "-c" ]]; then
  if [[ "${2:-}" == *"sys.implementation.name"* ]]; then
    printf '%s\n' 'cpython 3 12'
  fi
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "uvicorn" ]]; then
  exit 1
fi
echo "unexpected python invocation: $*" >&2
exit 1
EOF
chmod +x "${tmp}/bin/python3"

python_log="${tmp}/python.log"
: >"${python_log}"
set +e
output="$(
  FAKE_PYTHON_LOG="${python_log}" PIP_NO_INDEX=1 PATH="${tmp}/bin:${PATH}" \
    bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
    "${remote}" "${release}" git aaaaaaa "${full_sha}" \
    59991 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
    "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1
)"
status=$?
set -e
test "${status}" -ne 0
release_venv="${release}/code/server/.venv/bin/python"
upgrade_line=""
cpu_line=""
req_line=""
line_no=0
while IFS= read -r line; do
  line_no=$((line_no + 1))
  case "${line}" in
    "${release_venv} -m pip install --upgrade pip")
      upgrade_line="${line_no}"
      ;;
    "${release_venv} -m pip install --index-url https://download.pytorch.org/whl/cpu torch>=2.2,<3")
      cpu_line="${line_no}"
      ;;
    "${release_venv} -m pip install -r requirements.txt")
      req_line="${line_no}"
      ;;
    *" -m pip "*)
      echo "pip ran outside the new release venv: ${line}" >&2
      exit 1
      ;;
  esac
done <"${python_log}"
test -n "${upgrade_line}"
test -n "${cpu_line}"
test -n "${req_line}"
test "${upgrade_line}" -lt "${cpu_line}"
test "${cpu_line}" -lt "${req_line}"
test ! -e "${remote}/current"
test ! -e "${remote}/previous"
test ! -e "${remote}/data/deployed_commit"
if grep -q '^MA3_GIT_COMMIT=' "${remote}/ma3.env"; then
  echo "MA3_GIT_COMMIT persisted before cutover" >&2
  exit 1
fi
grep -q 'activated release' <<<"${output}" && {
  echo "release activated after failed dependency install" >&2
  exit 1
}

# Production invariant failures must still abort before any venv or install.
cat >"${remote}/ma3.env" <<'EOF'
MA3_DEV_AUTH=1
MA3_INSTANCE_ID=test
MA3_PUBLIC_BASE_URL=https://example.invalid
EOF
rm -f "${python_log}"
set +e
output="$(
  FAKE_PYTHON_LOG="${python_log}" PIP_NO_INDEX=1 PATH="${tmp}/bin:${PATH}" \
    bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
    "${remote}" "${release}" git aaaaaaa "${full_sha}" \
    59991 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
    "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1
)"
status=$?
set -e
test "${status}" -ne 0
grep -q 'ASSERT FAIL: MA3_DEV_AUTH=1' <<<"${output}"
test ! -e "${python_log}"
test ! -e "${remote}/current"

# A compatible current release is reused without pip; its owning release must
# remain in place because the new release's venv is a symlink to it.
cat >"${remote}/ma3.env" <<'EOF'
MA3_DEV_AUTH=0
MA3_INSTANCE_ID=test
MA3_PUBLIC_BASE_URL=https://example.invalid
EOF
donor="${remote}/releases/cccccccccccccccccccccccccccccccccccccccc"
reuse_release="${remote}/releases/dddddddddddddddddddddddddddddddddddddddd"
mkdir -p "${donor}/code/server/.venv/bin" "${reuse_release}/code/server"
cp "${tmp}/bin/python3" "${donor}/code/server/.venv/bin/python"
cp "${REPO_DIR}/code/server/requirements.txt" "${donor}/code/server/requirements.txt"
cp "${REPO_DIR}/code/server/requirements.txt" "${reuse_release}/code/server/requirements.txt"
printf '%s\n' dddddddddddddddddddddddddddddddddddddddd >"${reuse_release}/.ma3-release-commit"
ln -s "${donor}" "${remote}/current"
: >"${python_log}"
set +e
output="$(
  FAKE_PYTHON_LOG="${python_log}" PATH="${tmp}/bin:${PATH}" \
    bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
    "${remote}" "${reuse_release}" git ddddddd dddddddddddddddddddddddddddddddddddddddd \
    59991 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
    "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1
)"
status=$?
set -e
test "${status}" -ne 0  # fake uvicorn cannot pass healthz
grep -q 'reuse venv' <<<"${output}"
test -L "${reuse_release}/code/server/.venv"
test "$(readlink -f "${reuse_release}/code/server/.venv")" = \
  "$(readlink -f "${donor}/code/server/.venv")"
if grep -q -- ' -m pip ' "${python_log}"; then
  echo "pip ran on a reused venv" >&2
  exit 1
fi
test -d "${donor}/code/server/.venv"
test "$(readlink -f "${remote}/current")" = "$(readlink -f "${donor}")"

# A changed requirements file must build a separate environment, not install
# into the live release's venv.
mismatch_release="${remote}/releases/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
mkdir -p "${mismatch_release}/code/server/scripts"
cp "${REPO_DIR}/code/server/requirements.txt" "${mismatch_release}/code/server/requirements.txt"
printf '%s\n' '# different dependencies' >>"${mismatch_release}/code/server/requirements.txt"
cp "${REPO_DIR}/code/server/scripts/pip_install_requirements.sh" \
  "${mismatch_release}/code/server/scripts/pip_install_requirements.sh"
printf '%s\n' eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee >"${mismatch_release}/.ma3-release-commit"
: >"${python_log}"
set +e
output="$(
  FAKE_PYTHON_LOG="${python_log}" PATH="${tmp}/bin:${PATH}" \
    bash "${REPO_DIR}/deploy/common/deploy_release_remote.sh" \
    "${remote}" "${mismatch_release}" git eeeeeee eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
    59992 127.0.0.1 1 1 test https://example.invalid 1 1 0 8000 8001 0 \
    "${remote}/data/upstream.caddy" Y2FkZHkgcmVsb2Fk "" 2>&1
)"
status=$?
set -e
test "${status}" -ne 0
test -d "${mismatch_release}/code/server/.venv"
test ! -L "${mismatch_release}/code/server/.venv"
grep -q -- ' -m pip install -r requirements.txt' "${python_log}"
test "$(readlink -f "${remote}/current")" = "$(readlink -f "${donor}")"

echo "deploy release guard tests passed"
