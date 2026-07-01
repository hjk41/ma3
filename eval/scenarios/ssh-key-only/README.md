# ssh-key-only

Harden sshd inside the scenario container: disable password auth, allow key-only login.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=ssh-key-only`.
2. Fix `workspace/sshd_config` (copied from `broken/`).
3. Ensure `workspace/authorized_keys` contains the scenario public key.
4. `ssh -i workspace/id_ed25519 eval@127.0.0.1 -p 18022 true` must succeed.
5. Password authentication must be disabled.
6. Report reusable knowledge to ma3 if applicable.
