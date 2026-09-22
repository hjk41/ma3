#!/usr/bin/env bash
# Prepare an immutable source release from a Git remote.
#
# Usage (normally streamed over SSH by deploy/deploy.sh):
#   bash -s -- REMOTE_DIR GIT_REPO_URL GIT_REF FULL_COMMIT [GIT_DEPLOY_KEY]
#
# The script keeps a bare cache under REMOTE_DIR/repo.git and materializes
# REMOTE_DIR/releases/<full-commit>. It never touches REMOTE_DIR/data or ma3.env.
set -euo pipefail

if [[ "$#" -lt 4 || "$#" -gt 5 ]]; then
  echo "usage: $0 REMOTE_DIR GIT_REPO_URL GIT_REF FULL_COMMIT [GIT_DEPLOY_KEY]" >&2
  exit 2
fi

REMOTE_DIR="$1"
GIT_REPO_URL="$2"
GIT_REF="$3"
DEPLOY_GIT_COMMIT="$4"
GIT_DEPLOY_KEY="${5:-}"

[[ "${DEPLOY_GIT_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "FATAL: deployment commit must be a full lowercase 40-character SHA" >&2
  exit 2
}
git check-ref-format "${GIT_REF}" >/dev/null 2>&1 || {
  echo "FATAL: invalid GIT_REF=${GIT_REF}" >&2
  exit 2
}

if [[ -n "${GIT_DEPLOY_KEY}" ]]; then
  [[ -f "${GIT_DEPLOY_KEY}" ]] || {
    echo "FATAL: GIT_DEPLOY_KEY does not exist: ${GIT_DEPLOY_KEY}" >&2
    exit 1
  }
  printf -v deploy_key_q '%q' "${GIT_DEPLOY_KEY}"
  export GIT_SSH_COMMAND="ssh -i ${deploy_key_q} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
fi

repo_dir="${REMOTE_DIR}/repo.git"
releases_dir="${REMOTE_DIR}/releases"
release_dir="${releases_dir}/${DEPLOY_GIT_COMMIT}"
fetched_ref="refs/remotes/origin/ma3-deploy"

mkdir -p "${REMOTE_DIR}" "${releases_dir}"
if [[ ! -d "${repo_dir}" ]]; then
  git init --bare "${repo_dir}" >/dev/null
fi

if git --git-dir="${repo_dir}" remote get-url origin >/dev/null 2>&1; then
  git --git-dir="${repo_dir}" remote set-url origin "${GIT_REPO_URL}"
else
  git --git-dir="${repo_dir}" remote add origin "${GIT_REPO_URL}"
fi

echo "==> fetch ${GIT_REPO_URL} ${GIT_REF}"
git --git-dir="${repo_dir}" fetch --force --prune origin \
  "+${GIT_REF}:${fetched_ref}"

resolved="$(git --git-dir="${repo_dir}" rev-parse "${DEPLOY_GIT_COMMIT}^{commit}" 2>/dev/null || true)"
[[ "${resolved}" == "${DEPLOY_GIT_COMMIT}" ]] || {
  echo "FATAL: commit ${DEPLOY_GIT_COMMIT} was not fetched from ${GIT_REF}" >&2
  exit 1
}
git --git-dir="${repo_dir}" merge-base --is-ancestor \
  "${DEPLOY_GIT_COMMIT}" "${fetched_ref}" || {
  echo "FATAL: commit ${DEPLOY_GIT_COMMIT} is not reachable from ${GIT_REF}" >&2
  exit 1
}

if [[ -d "${release_dir}" ]]; then
  marker="$(tr -d '[:space:]' <"${release_dir}/.ma3-release-commit" 2>/dev/null || true)"
  [[ "${marker}" == "${DEPLOY_GIT_COMMIT}" ]] || {
    echo "FATAL: existing release directory has no matching commit marker: ${release_dir}" >&2
    exit 1
  }
  echo "==> reuse release ${release_dir}"
else
  tmp_dir="${release_dir}.tmp.$$"
  trap 'rm -rf -- "${tmp_dir}"' EXIT
  mkdir -p "${tmp_dir}"
  git --git-dir="${repo_dir}" archive "${DEPLOY_GIT_COMMIT}" | tar -x -C "${tmp_dir}"
  printf '%s\n' "${DEPLOY_GIT_COMMIT}" >"${tmp_dir}/.ma3-release-commit"
  mv "${tmp_dir}" "${release_dir}"
  trap - EXIT
  echo "==> prepared release ${release_dir}"
fi

printf '%s\n' "${release_dir}"
