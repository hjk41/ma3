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

echo "deploy release guard tests passed"
