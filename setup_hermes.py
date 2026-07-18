#!/usr/bin/env python3
"""OopsNote Hermes 初始化脚本。

运行即检测/创建/更新 Hermes oopsnote profile：
- 检测 profile 是否存在
- 不存在 → 创建 + 配置 SOUL + skills + MCP
- 存在 → 更新 SOUL + skills + MCP
"""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path
from shutil import copytree, ignore_patterns

PROFILE_NAME = "oopsnote"
HERMES = "hermes"

# ── 路径 ──────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
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
    print(f"创建 oopsnote profile ...")
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
- 使用 `oopsnote-orchestrator` skill 编排流程（随手拍/手动录入/单题更新三种模式）
- 调用 `mcp__oopsnote__*` 工具读写数据
- OCR 阶段用 `vision_analyze` 查看图片
- 解题和打标用 `delegate_task` 并行处理
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
- 任何阶段出错都要报告具体原因
"""
    soul_path = PROFILE_DIR / "SOUL.md"
    soul_path.write_text(soul_content, encoding="utf-8")
    print(f"  写入 SOUL.md")


# ── 同步 skills ────────────────────────────────────

def sync_skills():
    """从仓库 skills/ 目录复制到 profile skills/ 目录。"""
    src_dir = REPO_ROOT / "skills"
    dst_dir = PROFILE_DIR / "skills"

    if not src_dir.exists():
        print("  ⚠ skills/ 目录不存在，跳过")
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
    """在 hermes config.yaml 中注册 oopsnote MCP server。"""
    config_path = Path.home() / "AppData" / "Local" / "hermes" / "config.yaml"
    if not config_path.exists():
        print("  ⚠ config.yaml 不存在，跳过 MCP 配置")
        return

    content = config_path.read_text(encoding="utf-8")

    # 检查是否已有 oopsnote 配置
    if "oopsnote:" in content and "mcp_server.py" in content:
        print("  MCP 配置已存在，跳过")
        return

    # 追加 MCP 配置
    mcp_config = f"""\n
  oopsnote:
    command: uv
    args:
      - run
      - python
      - -m
      - oopsnote.mcp
    enabled: true
"""

    # 找到 mcp: 节并添加
    if "mcp:" in content:
        # 在最后一个 mcp server 配置后插入
        lines = content.split("\n")
        new_lines = []
        in_mcp = False
        for line in lines:
            new_lines.append(line)
            if line.strip().startswith("mcp:"):
                in_mcp = True
            elif in_mcp and not line.startswith(" ") and line.strip():
                in_mcp = False
        # 在末尾追加
        new_lines.append(mcp_config.rstrip())
        config_path.write_text("\n".join(new_lines), encoding="utf-8")
    else:
        config_path.write_text(content + "\nmcp:" + mcp_config, encoding="utf-8")

    print("  配置 MCP server")


# ── 主流程 ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("OopsNote Hermes 初始化")
    print(f"  Profile: {PROFILE_NAME}")
    print(f"  仓库: {REPO_ROOT}")
    print("=" * 50)

    if not check_hermes():
        print("\n❌ 未找到 hermes 命令。请先安装 Hermes Agent:")
        print("   https://hermes-agent.nousresearch.com/docs")
        sys.exit(1)

    if profile_exists():
        print(f"\n📋 Profile '{PROFILE_NAME}' 已存在，更新中 ...")
    else:
        print(f"\n🆕 创建 Profile '{PROFILE_NAME}' ...")
        create_profile()

    write_soul()
    sync_skills()
    config_mcp()

    print(f"\n✅ 完成。运行: hermes --profile {PROFILE_NAME}")


if __name__ == "__main__":
    main()
