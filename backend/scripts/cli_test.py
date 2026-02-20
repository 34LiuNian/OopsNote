from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from pathlib import Path

# Add backend directory to sys.path to allow importing app
backend_root = Path(__file__).resolve().parents[1]
sys.path.append(str(backend_root))

try:
    from dotenv import load_dotenv
    load_dotenv(backend_root / ".env")
except ImportError:
    pass

from app.bootstrap import load_app_config
from app.builders import (
    build_agent_settings_service,
    build_ai_client,
    build_pipeline,
    build_repository,
)
from app.services.tasks_service import TasksService
from app.storage import LocalAssetStore
from app.repository import ArchiveStore
from app.tags import tag_store
from app.models import UploadRequest
from app.clients import load_agent_config_bundle

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("cli-test")

def run_test(image_path: str, subject: str = "数学"):
    # 1. Load config
    os.environ["PERSIST_TASKS"] = "false"  # Don't clutter real storage during test
    config = load_app_config()
    
    # 2. Build dependencies (following bootstrap.py logic)
    repository = build_repository(config=config)
    asset_store = LocalAssetStore()
    archive_store = ArchiveStore()
    agent_settings_service = build_agent_settings_service()
    ai_client = build_ai_client(config=config)
    agent_config_bundle = load_agent_config_bundle(config.agent_config_path)
    
    # Use real agent bundle if available
    pipeline = build_pipeline(
        ai_client=ai_client,
        agent_config_bundle=agent_config_bundle,
        agent_settings_service=agent_settings_service,
        archive_store=archive_store,
    )
    
    tasks_service = TasksService(
        repository=repository,
        pipeline=pipeline,
        asset_store=asset_store,
        tag_store=tag_store,
    )

    # 3. Read image
    path = Path(image_path)
    if not path.exists():
        logger.error(f"Image not found: {image_path}")
        return

    print(f"\n[CONFIRM] 准备处理文件: {path.name}")
    print(f"[CONFIRM] 学科: {subject}")
    # conf = input("输入 'y' 开始处理，或直接回车退出: ").strip().lower()
    # if conf != 'y':
    #     print("取消处理。")
    #     return

    with open(path, "rb") as f:
        img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    # 4. Create and process task
    logger.info(f"Creating task for {path.name}...")
    upload = UploadRequest(
        image_base64=img_b64,
        filename=path.name,
        mime_type="image/jpeg",
        subject=subject,
    )
    
    # Create task (auto_process=False so we can call it manually and watch)
    task = tasks_service.upload_task(upload, auto_process=False)
    logger.info(f"Task created: {task.id}. Starting synchronous processing...")
    
    # Run pipeline with progress monitoring
    def on_progress(stage, message):
        print(f" >>> [PROGRESS] {stage}: {message or ''}")

    processed_task = tasks_service.process_task_sync(task.id, on_progress=on_progress)
    
    # 5. Output results
    print("\n" + "="*50)
    print(f"PROCESSING COMPLETE: {processed_task.id}")
    print(f"STATUS: {processed_task.status}")
    print("="*50)
    
    if processed_task.status == "failed":
        print(f"ERROR: {processed_task.last_error}")
        return

    print(f"\nFound {len(processed_task.problems)} problems:")
    for i, p in enumerate(processed_task.problems):
        print(f"\n--- Problem {i+1} [{p.problem_id}] ---")
        print(f"Text: {p.problem_text}")
        
        # Find solution
        sol = next((s for s in processed_task.solutions if s.problem_id == p.problem_id), None)
        if sol:
            print(f"Answer: {sol.answer}")
            print(f"Explanation: {sol.explanation}")
        
        # Find tags
        tag = next((t for t in processed_task.tags if t.problem_id == p.problem_id), None)
        if tag:
            print(f"Knowledge Points: {', '.join(tag.knowledge_points)}")
            print(f"Question Type: {tag.question_type}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OopsNote CLI Pipeline Tester")
    parser.add_argument("image", nargs="?", help="Path to the image file (optional, will list files if omitted)")
    parser.add_argument("--subject", default="数学", help="Subject (default: 数学)")
    
    args = parser.parse_args()
    
    target_image = args.image
    if not target_image:
        asset_dir = Path(backend_root) / "storage" / "assets"
        if not asset_dir.exists():
            print(f"Directory not found: {asset_dir}")
            sys.exit(1)
            
        assets = [
            f for f in asset_dir.iterdir() 
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png")
        ]
        
        if not assets:
            print(f"No valid images (.jpg, .png) found in {asset_dir}")
            sys.exit(1)
        
        print("\n未指定路径，请选择一个可用文件：")
        for i, a in enumerate(assets):
            print(f"[{i}] {a.name}")
        
        try:
            choice = int(input(f"\n选择文件序列号 (0-{len(assets)-1}): ").strip())
            target_image = str(assets[choice])
        except (ValueError, IndexError):
            print("选择无效。")
            sys.exit(1)
            
    run_test(target_image, args.subject)
