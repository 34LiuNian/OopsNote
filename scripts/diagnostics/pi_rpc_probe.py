#!/usr/bin/env python3
"""Low-level Pi JSONL RPC diagnostic probe.

This is not a pytest suite or the OopsNote end-to-end benchmark. It exercises
the locally configured Pi executable directly when RPC protocol debugging is
needed.
"""

import json
import subprocess
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = ROOT / ".pi" / "runtime.json"


def load_pi_command() -> list[str]:
    if not RUNTIME_PATH.exists():
        raise RuntimeError(f"Missing local Pi runtime config: {RUNTIME_PATH}")
    config = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    command = config.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise RuntimeError(".pi/runtime.json command must be a non-empty string array")
    provider = config.get("provider", "deepseek")
    model = config.get("model", "deepseek-v4-flash")
    return [*command, "--provider", provider, "--model", model]


PI_CMD = load_pi_command()

PASS = "[PASS]"
FAIL = "[FAIL]"

results_list = []


def report(name, ok):
    results_list.append((name, ok))
    print(f"  {PASS if ok else FAIL} {name}")


def test_rpc_basic():
    print("--- Test 1: 基础 RPC (启动 -> prompt -> 收事件 -> 退出) ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    events = []
    start = time.time()

    proc.stdin.write(
        json.dumps({"type": "prompt", "message": "Say exactly: RPC works fine. No extra text."})
        + "\n"
    )
    proc.stdin.flush()

    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            events.append(event)
            if event.get("type") == "agent_settled":
                break
        except json.JSONDecodeError:
            pass

    elapsed = time.time() - start
    types = set(e.get("type") for e in events)
    print(f"   事件数: {len(events)}, 类型: {types}")
    print(f"   耗时: {elapsed:.2f}s")
    proc.stdin.close()
    proc.wait(timeout=10)
    ok = elapsed < 60 and len(events) > 0
    report("test_rpc_basic", ok)
    return ok


def test_rpc_prompt_response():
    print("\n--- Test 2: prompt/response 往返 ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(
        json.dumps({"id": "req-1", "type": "prompt", "message": "Say exactly: Hello from RPC"})
        + "\n"
    )
    proc.stdin.flush()

    got_response = False
    got_content = False
    start = time.time()

    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            if event.get("type") == "response" and event.get("command") == "prompt":
                got_response = event.get("success", False)
                print(f"   prompt response: success={got_response}")
            if event.get("type") == "message_update":
                delta = event.get("assistantMessageEvent", {})
                if delta.get("type") == "text_delta":
                    got_content = True
            if event.get("type") == "agent_settled":
                break
        except json.JSONDecodeError:
            pass

    elapsed = time.time() - start
    print(f"   耗时: {elapsed:.2f}s")
    proc.stdin.close()
    proc.wait(timeout=10)
    ok = got_response and got_content
    report("test_rpc_prompt_response", ok)
    return ok


def test_rpc_get_state():
    print("\n--- Test 3: get_state ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(json.dumps({"id": "req-state", "type": "get_state"}) + "\n")
    proc.stdin.flush()

    state_data = None
    start = time.time()
    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            if event.get("type") == "response" and event.get("command") == "get_state":
                state_data = event.get("data")
                break
        except json.JSONDecodeError:
            pass

    elapsed = time.time() - start
    print(f"   耗时: {elapsed:.2f}s")
    if state_data:
        print(f"   model: {state_data.get('model', {}).get('id', 'N/A')}")
        print(f"   sessionId: {state_data.get('sessionId', 'N/A')}")
        print(f"   thinkingLevel: {state_data.get('thinkingLevel', 'N/A')}")
        print(f"   autoCompactionEnabled: {state_data.get('autoCompactionEnabled', 'N/A')}")
    proc.stdin.close()
    proc.wait(timeout=10)
    ok = state_data is not None and "model" in state_data
    report("test_rpc_get_state", ok)
    return ok


def test_rpc_session_stats():
    print("\n--- Test 4: get_session_stats (token/cost) ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(
        json.dumps({"id": "req-prompt", "type": "prompt", "message": "Say exactly: stats test"})
        + "\n"
    )
    proc.stdin.flush()
    for line in proc.stdout:
        try:
            if json.loads(line.strip()).get("type") == "agent_settled":
                break
        except json.JSONDecodeError:
            pass

    proc.stdin.write(json.dumps({"id": "req-stats", "type": "get_session_stats"}) + "\n")
    proc.stdin.flush()
    stats_data = None
    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            if event.get("type") == "response" and event.get("command") == "get_session_stats":
                stats_data = event.get("data")
                break
        except json.JSONDecodeError:
            pass

    if stats_data:
        print(f"   tokens: {stats_data.get('tokens', {})}")
        print(f"   cost: {stats_data.get('cost')}")
        print(f"   contextUsage: {stats_data.get('contextUsage', {})}")
    proc.stdin.close()
    proc.wait(timeout=10)
    ok = stats_data is not None and "tokens" in stats_data and "cost" in stats_data
    report("test_rpc_session_stats", ok)
    return ok


def test_rpc_abort():
    print("\n--- Test 5: abort 中途终止 ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(
        json.dumps(
            {
                "id": "req-prompt",
                "type": "prompt",
                "message": "Write a long story about a magical forest. At least 500 words.",
            }
        )
        + "\n"
    )
    proc.stdin.flush()
    time.sleep(2)
    proc.stdin.write(json.dumps({"id": "req-abort", "type": "abort"}) + "\n")
    proc.stdin.flush()

    got_abort = False
    start = time.time()
    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            if event.get("type") == "response" and event.get("command") == "abort":
                got_abort = event.get("success", False)
                print(f"   abort response: success={got_abort}")
                break
        except json.JSONDecodeError:
            pass
    elapsed = time.time() - start
    print(f"   耗时: {elapsed:.2f}s")
    proc.stdin.close()
    proc.wait(timeout=10)
    report("test_rpc_abort", ok=got_abort)
    return got_abort


def test_rpc_no_builtin_tools():
    print("\n--- Test 6: --no-builtin-tools (工具限制) ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(
        json.dumps(
            {
                "type": "prompt",
                "message": "Use the read tool to read /etc/hostname, then tell me what it says.",
            }
        )
        + "\n"
    )
    proc.stdin.flush()

    has_tool_call = False
    start = time.time()
    for line in proc.stdout:
        try:
            event = json.loads(line.strip())
            if event.get("type") == "message_update":
                delta = event.get("assistantMessageEvent", {})
                if delta.get("type") == "toolcall_start":
                    has_tool_call = True
                    name = delta.get("partial", {}).get("name", "unknown")
                    print(f"   agent 尝试调用: {name}")
            if event.get("type") == "agent_settled":
                break
        except json.JSONDecodeError:
            pass
    elapsed = time.time() - start
    print(f"   耗时: {elapsed:.2f}s, 尝试调工具: {has_tool_call}")
    proc.stdin.close()
    proc.wait(timeout=10)
    report("test_rpc_no_builtin_tools", ok=True)
    return True


def test_rpc_stress():
    print("\n--- Test 7: 连续 5 个短任务 ---")
    success = 0
    total_start = time.time()
    for i in range(5):
        start = time.time()
        try:
            proc = subprocess.Popen(
                [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            proc.stdin.write(
                json.dumps(
                    {"id": f"req-{i}", "type": "prompt", "message": f"Say exactly: Task {i} done"}
                )
                + "\n"
            )
            proc.stdin.flush()
            settled = False
            for line in proc.stdout:
                try:
                    if json.loads(line.strip()).get("type") == "agent_settled":
                        settled = True
                        break
                except json.JSONDecodeError:
                    pass
            proc.stdin.close()
            proc.wait(timeout=15)
            elapsed = time.time() - start
            if settled:
                success += 1
                print(f"   Task {i}: PASS ({elapsed:.2f}s)")
            else:
                print(f"   Task {i}: FAIL (no agent_settled, {elapsed:.2f}s)")
        except Exception as e:
            print(f"   Task {i}: ERROR {e}")
    total_elapsed = time.time() - total_start
    print(f"   总计: {success}/5 PASS, {total_elapsed:.2f}s")
    report("test_rpc_stress", ok=success >= 4)
    return success >= 4


def test_rpc_stderr():
    print("\n--- Test 8: stderr 检查 ---")
    proc = subprocess.Popen(
        [*PI_CMD, "--mode", "rpc", "--no-session", "--no-builtin-tools"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    proc.stdin.write(json.dumps({"type": "prompt", "message": "Say exactly: stderr check"}) + "\n")
    proc.stdin.flush()
    for line in proc.stdout:
        try:
            if json.loads(line.strip()).get("type") == "agent_settled":
                break
        except json.JSONDecodeError:
            pass
    proc.stdin.close()
    proc.wait(timeout=10)
    stderr_out = proc.stderr.read()
    if stderr_out.strip():
        print(f"   stderr 有输出: {stderr_out[:300]}")
    else:
        print("   stderr 干净")
    ok = len(stderr_out.strip()) == 0
    report("test_rpc_stderr", ok)
    return ok


if __name__ == "__main__":
    # 版本信息
    r = subprocess.run([*PI_CMD, "--version"], capture_output=True, text=True)
    print(f"Pi version: {r.stdout.strip()}")
    print("Model: deepseek/deepseek-v4-flash")
    print(
        f"DEEPSEEK_API_KEY: {'SET' if 'DEEPSEEK_API_KEY' in subprocess.run('set', capture_output=True, text=True, shell=True).stdout else 'checking...'}"
    )
    print()

    tests = [
        ("basic", test_rpc_basic),
        ("prompt_response", test_rpc_prompt_response),
        ("get_state", test_rpc_get_state),
        ("session_stats", test_rpc_session_stats),
        ("abort", test_rpc_abort),
        ("no_builtin_tools", test_rpc_no_builtin_tools),
        ("stress_5_tasks", test_rpc_stress),
        ("stderr_clean", test_rpc_stderr),
    ]

    print("=" * 60)
    print("Pi RPC 压测开始")
    print("=" * 60)
    print()

    for name, fn in tests:
        print(f"[{name}]")
        try:
            fn()
        except Exception as e:
            print(f"  异常: {e}")
            traceback.print_exc()
            report(name, False)
        print()

    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    all_pass = True
    for name, ok in results_list:
        print(f"  {PASS if ok else FAIL}  {name}")
        if not ok:
            all_pass = False

    print(f"\n总体: {'ALL PASS' if all_pass else 'SOME FAILED'}")
