"""OopsNote CLI — 调试/开发用入口。

做得简单，够调试用就行。不面向日常使用。
Phase 2 接入 Hermes 后 scan 才真正工作。
"""

from __future__ import annotations

import argparse


def cmd_scan(args: argparse.Namespace) -> None:
    """桩：扫描 PDF/图片，触发 AI 流水线。"""
    path = args.path
    subject = args.subject or ""
    print(f"[scan] {path} (subject={subject})")
    print("[scan] TODO: Phase 2 — 接入 Hermes pipeline")


def cmd_search(args: argparse.Namespace) -> None:
    """桩：多维度搜索。"""
    print("[search] TODO: Phase 3")


def cmd_paper(args: argparse.Namespace) -> None:
    """桩：生成练习卷。"""
    print("[paper] TODO: Phase 5")


def cmd_sync(args: argparse.Namespace) -> None:
    """桩：云端同步。"""
    print("[sync] TODO: Phase 3")


def main() -> None:
    parser = argparse.ArgumentParser("oopsnote", description="OopsNote CLI (调试用)")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="扫描 PDF/图片")
    p_scan.add_argument("path", help="PDF 或图片路径")
    p_scan.add_argument("--subject", "-s", help="学科")

    p_search = sub.add_parser("search", help="搜索题库")
    p_search.add_argument("--tags", help="标签，逗号分隔")
    p_search.add_argument("--subject", "-s", help="学科")
    p_search.add_argument("--since", help="起始日期")

    p_paper = sub.add_parser("paper", help="生成练习卷")
    p_paper.add_argument("--knowledge", help="知识点")
    p_paper.add_argument("--count", type=int, default=10)
    p_paper.add_argument("--output", "-o", help="输出路径")

    sub.add_parser("sync", help="云端同步")

    args = parser.parse_args()
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "paper":
        cmd_paper(args)
    elif args.command == "sync":
        cmd_sync(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
