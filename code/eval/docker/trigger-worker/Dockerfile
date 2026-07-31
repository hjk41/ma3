# Trigger matrix agent worker: reuse agent-client-sync CLIs, allow non-root (Claude).
FROM agent-client-sync-runner:latest

USER root

# Runtime uses --user host-uid (Claude forbids root + --dangerously-skip-permissions).
# cursor-agent is installed under /root (mode 700) — relocate for non-root exec.
RUN mkdir -p /opt/cursor \
  && cp -a /root/.local/share/cursor-agent /opt/cursor/ \
  && VER="$(ls /opt/cursor/cursor-agent/versions | head -1)" \
  && ln -sf "/opt/cursor/cursor-agent/versions/${VER}/cursor-agent" /usr/local/bin/cursor-agent \
  && ln -sf "/opt/cursor/cursor-agent/versions/${VER}/cursor-agent" /usr/local/bin/agent \
  && chmod -R a+rX /opt/cursor \
  && test -x /usr/local/bin/cursor-agent

ENV PATH=/opt/npm-global/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /repo

ENTRYPOINT ["bash"]
