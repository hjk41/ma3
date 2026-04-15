#!/usr/bin/env python3
"""
ma3 一键安装脚本
用法: python install_ma3.py [--api-key YOUR_KEY] [--base-url http://...]

做三件事:
  1. 在 ~/.claude/settings.json 里加入 git clone 权限，让 Claude 以后能自主安装/更新
  2. 把 ma3 客户端插件 clone 到 ~/plugins/ma3
  3. 写入 .env 配置文件
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

# ── 默认值 ────────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL  = "http://10.100.193.54:8000"
DEFAULT_API_KEY   = ""           # 留空则安装时提示输入
PLUGIN_REPO       = "https://codeup.aliyun.com/finalsystems/ma3.git"
PLUGIN_DIR        = pathlib.Path.home() / "plugins" / "ma3"
SETTINGS_FILE     = pathlib.Path.home() / ".claude" / "settings.json"

# Claude Code 需要预批准的 Bash 命令前缀
ALLOW_RULES = [
    "Bash(git clone https://codeup.aliyun.com/finalsystems/ma3*)",
    "Bash(git -C * pull*)",                        # 允许后续 self-update
    f"Bash(python */ma3/skills/ma3/scripts/ma3_client.py*)",  # 允许调用客户端
]


def merge_settings(allow_rules: list[str]) -> None:
    """将 allow 规则合并进 ~/.claude/settings.json，不覆盖已有内容。"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[警告] {SETTINGS_FILE} 解析失败，将备份后重建。")
            shutil.copy(SETTINGS_FILE, SETTINGS_FILE.with_suffix(".bak.json"))
            settings = {}
    else:
        settings = {}

    perms = settings.setdefault("permissions", {})
    existing_allow = perms.setdefault("allow", [])

    added = []
    for rule in allow_rules:
        if rule not in existing_allow:
            existing_allow.append(rule)
            added.append(rule)

    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if added:
        print(f"[settings] 已添加 {len(added)} 条权限规则:")
        for r in added:
            print(f"    {r}")
    else:
        print("[settings] 权限规则已存在，无需变更。")


def clone_or_update_plugin() -> None:
    """Clone 或 pull ma3 客户端插件。"""
    if (PLUGIN_DIR / ".git").exists():
        print(f"[plugin] 已存在，执行更新 ({PLUGIN_DIR}) ...")
        result = subprocess.run(
            ["git", "-C", str(PLUGIN_DIR), "pull"],
            capture_output=True, text=True,
        )
        print(result.stdout.strip() or result.stderr.strip())
    else:
        PLUGIN_DIR.parent.mkdir(parents=True, exist_ok=True)
        print(f"[plugin] 正在 clone {PLUGIN_REPO} → {PLUGIN_DIR} ...")
        result = subprocess.run(
            ["git", "clone", PLUGIN_REPO, str(PLUGIN_DIR)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[错误] clone 失败:\n{result.stderr}")
            sys.exit(1)
        print("[plugin] clone 完成。")


def write_env(base_url: str, api_key: str) -> None:
    """写入 .env 配置文件（已存在则跳过，避免覆盖个人 key）。"""
    env_file = PLUGIN_DIR / ".env"
    if env_file.exists():
        print(f"[env] {env_file} 已存在，跳过（如需更新请手动编辑）。")
        return

    client_script = PLUGIN_DIR / "skills" / "ma3" / "scripts" / "ma3_client.py"
    content = (
        f"MA3_BASE_URL={base_url}\n"
        f"MA3_API_KEY={api_key}\n"
        f"MA3_AUTH_MODE=x-api-key\n"
        f"MA3_CLIENT_SCRIPT={client_script}\n"
    )
    env_file.write_text(content, encoding="utf-8")
    print(f"[env] 已写入 {env_file}")


def health_check(base_url: str, api_key: str) -> None:
    """快速健康检查，确认服务可达。"""
    client = PLUGIN_DIR / "skills" / "ma3" / "scripts" / "ma3_client.py"
    if not client.exists():
        print("[healthz] 跳过（客户端脚本未找到）。")
        return

    env = os.environ.copy()
    env["MA3_BASE_URL"] = base_url
    env["MA3_API_KEY"]  = api_key

    result = subprocess.run(
        [sys.executable, str(client), "healthz"],
        capture_output=True, text=True, env=env,
    )
    output = result.stdout.strip() or result.stderr.strip()
    print(f"[healthz] {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ma3 一键安装")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="ma3 服务地址")
    parser.add_argument("--api-key",  default=DEFAULT_API_KEY,  help="ma3 库 token")
    args = parser.parse_args()

    api_key = args.api_key
    if not api_key:
        api_key = input("请输入 ma3 API Key（库 token）: ").strip()
        if not api_key:
            print("[错误] API Key 不能为空。")
            sys.exit(1)

    print("\n=== ma3 安装开始 ===\n")

    merge_settings(ALLOW_RULES)
    print()
    clone_or_update_plugin()
    print()
    write_env(args.base_url, api_key)
    print()
    health_check(args.base_url, api_key)

    print("\n=== 安装完成 ===")
    print(f"客户端路径: {PLUGIN_DIR / 'skills' / 'ma3' / 'scripts' / 'ma3_client.py'}")
    print("重启 Claude Code 后权限规则生效，之后 Claude 可完全自主使用 ma3。")


if __name__ == "__main__":
    main()
