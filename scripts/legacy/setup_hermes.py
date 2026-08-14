#!/usr/bin/env python3
"""Legacy OopsNote Hermes setup retained only during the Pi migration.

运行即检测/创建/更新 Hermes oopsnote profile：
- 检测 profile 是否存在
- 不存在 → 创建 + 配置 SOUL + skills + MCP
- 存在 → 更新 SOUL + skills + MCP
"""

from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from shutil import copytree

import yaml

PROFILE_NAME = "oopsnote"
HERMES = "hermes"

# ── 路径 ──────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = Path.home() / "AppData" / "Local" / "hermes" / "profiles" / PROFILE_NAME

# ── 检查 hermes 是否可用 ───────────────────────────


def check_hermes() -> bool:
    try:
        subprocess.run([HERMES, "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ── 检测 profile ──────────────────────────────────


def profile_exists() -> bool:
    return (PROFILE_DIR / "SOUL.md").exists()


# ── 创建 profile ──────────────────────────────────


def create_profile():
    print("创建 oopsnote profile ...")
    subprocess.run([HERMES, "profile", "create", PROFILE_NAME], check=True)
    print("  完成。")


# ── 写 SOUL.md ────────────────────────────────────


def write_soul():
    soul_content = """你是 OopsNote，一个 AI 错题管理助手。你的用户是一名中国高中学生（2024级2班）。

## 核心职责
1. 处理随手拍的错题照片（一张图一道题）
2. 处理手动录入的纯文本题目（Markdown+LaTeX）
3. 从图片中提取题目（OCR + 结构化）
4. 为每道题生成答案和详细解析
5. 标注知识点、错因等多维标签
6. 将结果存入本地题库、同步到 Obsidian

## 工作方式
- 使用 `oopsnote-orchestrator` skill 编排单题流水线
- Web 受管任务只调用 `mcp__oopsnote_pipeline__*`；交互模式调用 `mcp__oopsnote__*`
- OCR 阶段用 `vision_analyze` 查看图片
- OCR、解题、验证、打标按顺序执行，每阶段上报状态
- 批量扫描未来走 Web 手动框选，不在此处理 PDF

## 风格
- 使用中文回复
- 用标准学术语言写解析
- LaTeX 公式格式正确
- 解题步骤清晰完整
- 标签优先从已有库中选择，避免创建同义词

## 约束
- 只处理印刷题目，忽略学生手写内容
- 不确定的地方明确标注，交给用户判断
- 任何阶段出错都要通过 `fail_task` 报告具体原因
- 成功结果只能通过 `finalize_task` 校验并提交
"""
    soul_path = PROFILE_DIR / "SOUL.md"
    soul_path.write_text(soul_content, encoding="utf-8")
    print("  写入 SOUL.md")


# ── 同步 skills ────────────────────────────────────


def sync_skills():
    """从仓库 skills/ 目录复制到 profile skills/ 目录。"""
    src_dir = REPO_ROOT / "skills"
    dst_dir = PROFILE_DIR / "skills"

    if not src_dir.exists():
        print("  [WARN] skills/ 目录不存在，跳过")
        return

    for skill_dir in src_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        dst = dst_dir / skill_dir.name
        if dst.exists():
            # 只更新 SKILL.md 和 references/，不删用户可能添加的文件
            for item in ["SKILL.md", "references"]:
                src_item = skill_dir / item
                dst_item = dst / item
                if src_item.is_dir() and dst_item.exists():
                    copytree(src_item, dst_item, dirs_exist_ok=True)
                elif src_item.is_file():
                    dst.mkdir(parents=True, exist_ok=True)
                    dst_item.write_text(src_item.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            copytree(skill_dir, dst, dirs_exist_ok=True)

    print(f"  同步 {sum(1 for _ in src_dir.iterdir() if _.is_dir())} 个 skills")


# ── 配置 MCP ───────────────────────────────────────


def config_mcp():
    """Register full interactive and restricted Web pipeline MCP servers."""
    config_path = PROFILE_DIR / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    config = config or {}
    servers = config.setdefault("mcp_servers", {})
    base_server = {
        "command": "uv",
        "args": [
            "--directory",
            str(REPO_ROOT),
            "run",
            "python",
            "-m",
            "oopsnote.mcp",
        ],
        "enabled": True,
    }
    servers["oopsnote"] = deepcopy(base_server)
    servers["oopsnote_pipeline"] = {
        **deepcopy(base_server),
        "tools": {
            "include": [
                "get_task",
                "get_asset_path",
                "list_tags",
                "create_tag",
                "report_task_stage",
                "finalize_task",
                "fail_task",
            ]
        },
    }
    tmp = config_path.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(config_path)
    print("  配置 MCP servers: oopsnote, oopsnote_pipeline")


# ── 主流程 ─────────────────────────────────────────


def main():
    print("=" * 50)
    print("OopsNote Hermes 初始化")
    print(f"  Profile: {PROFILE_NAME}")
    print(f"  仓库: {REPO_ROOT}")
    print("=" * 50)

    if not check_hermes():
        print("\n[ERROR] 未找到 hermes 命令。请先安装 Hermes Agent:")
        print("   https://hermes-agent.nousresearch.com/docs")
        sys.exit(1)

    if profile_exists():
        print(f"\nProfile '{PROFILE_NAME}' 已存在，更新中 ...")
    else:
        print(f"\n创建 Profile '{PROFILE_NAME}' ...")
        create_profile()

    write_soul()
    sync_skills()
    config_mcp()

    print(f"\n完成。运行: hermes --profile {PROFILE_NAME}")


if __name__ == "__main__":
    main()
