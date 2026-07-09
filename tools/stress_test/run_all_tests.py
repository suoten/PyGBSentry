"""压力测试总运行脚本 — 按顺序执行所有测试场景。

使用方式:
  python tools/stress_test/run_all_tests.py \
      --base-url http://localhost:8000 \
      --sip-host 127.0.0.1 --sip-port 5060 \
      --token YOUR_JWT_TOKEN \
      --channels "ch001,ch002,ch003,ch004,ch005,ch006,ch007,ch008,ch009,ch010" \
      --output-dir ./stress_test_results

依赖: pip install httpx psutil
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any

from concurrent_register_test import run_concurrent_register
from concurrent_login_test import run_concurrent_login
from concurrent_preview_test import run_concurrent_preview
from exception_scenario_test import run_all_tests as run_exception_tests
from endurance_monitor import run_endurance_monitor


async def run_all(
    base_url: str,
    sip_host: str,
    sip_port: int,
    token: str,
    channels: list[str],
    device_count: int,
    user_count: int,
    user_prefix: str,
    password: str,
    preview_duration: int,
    endurance_hours: float,
    log_path: str,
    output_dir: str,
    admin_username: str = "",
    admin_password: str = "",
) -> dict[str, Any]:
    """运行所有压力测试场景。"""
    os.makedirs(output_dir, exist_ok=True)
    all_results: dict[str, Any] = {
        "start_time": time.time(),
        "base_url": base_url,
        "sip_host": sip_host,
        "sip_port": sip_port,
    }

    # ─── 并发测试 ───
    print("\n" + "=" * 70)
    print("  第一阶段: 并发测试")
    print("=" * 70)

    # 1. 并发注册
    print("\n>>> 测试 1/5: 并发设备注册")
    try:
        result = await run_concurrent_register(
            server_ip=sip_host,
            server_port=sip_port,
            device_count=device_count,
            device_prefix="3402000000132",
            password=password,
            realm="3402000000",
        )
        all_results["concurrent_register"] = result
        with open(os.path.join(output_dir, "01_concurrent_register.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        all_results["concurrent_register"] = {"error": str(e)}
        print(f"  测试异常: {e}")

    # 2. 并发登录
    print("\n>>> 测试 2/5: 并发用户登录")
    try:
        result = await run_concurrent_login(
            base_url=base_url,
            user_count=user_count,
            user_prefix=user_prefix,
            password=password,
            concurrency=20,
            admin_username=admin_username,
            admin_password=admin_password,
        )
        all_results["concurrent_login"] = result
        with open(os.path.join(output_dir, "02_concurrent_login.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        all_results["concurrent_login"] = {"error": str(e)}
        print(f"  测试异常: {e}")

    # 3. 并发预览
    print(f"\n>>> 测试 3/5: 并发预览 ({preview_duration} 分钟)")
    try:
        result = await run_concurrent_preview(
            base_url=base_url,
            token=token,
            channels=channels,
            duration_minutes=preview_duration,
        )
        all_results["concurrent_preview"] = result
        with open(os.path.join(output_dir, "03_concurrent_preview.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        all_results["concurrent_preview"] = {"error": str(e)}
        print(f"  测试异常: {e}")

    # ─── 异常场景测试 ───
    print("\n" + "=" * 70)
    print("  第二阶段: 异常场景测试")
    print("=" * 70)

    # 4. 异常场景
    print("\n>>> 测试 4/5: 异常场景")
    try:
        result = await run_exception_tests(
            base_url=base_url,
            sip_host=sip_host,
            sip_port=sip_port,
            db_type="sqlite",
            db_path="",
        )
        all_results["exception_scenarios"] = result
        with open(os.path.join(output_dir, "04_exception_scenarios.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        all_results["exception_scenarios"] = {"error": str(e)}
        print(f"  测试异常: {e}")

    # ─── 耐久测试（最后执行，耗时最长） ───
    print("\n" + "=" * 70)
    print("  第三阶段: 耐久测试")
    print("=" * 70)

    # 5. 耐久监控
    print(f"\n>>> 测试 5/5: 耐久监控 ({endurance_hours} 小时)")
    try:
        result = await run_endurance_monitor(
            base_url=base_url,
            log_path=log_path,
            duration_hours=endurance_hours,
            output_file=os.path.join(output_dir, "05_endurance_monitor.json"),
        )
        all_results["endurance_monitor"] = result
    except Exception as e:
        all_results["endurance_monitor"] = {"error": str(e)}
        print(f"  测试异常: {e}")

    # ─── 总结 ───
    all_results["end_time"] = time.time()
    all_results["total_elapsed_s"] = round(all_results["end_time"] - all_results["start_time"], 1)

    # 保存总报告
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print("  所有测试完成!")
    print(f"  结果目录: {output_dir}")
    print(f"  总报告: {summary_path}")
    print(f"  总耗时: {all_results['total_elapsed_s']}s")
    print(f"{'='*70}\n")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry 压力测试总运行脚本")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sip-host", default="127.0.0.1")
    parser.add_argument("--sip-port", type=int, default=5060)
    parser.add_argument("--token", default="", help="JWT token (预览测试需要)")
    parser.add_argument("--channels", default="", help="通道ID列表(逗号分隔)")
    parser.add_argument("--device-count", type=int, default=50)
    parser.add_argument("--user-count", type=int, default=100)
    parser.add_argument("--user-prefix", default="testuser")
    parser.add_argument("--password", default="default_password")
    parser.add_argument("--preview-duration", type=int, default=30, help="预览持续时间(分钟)")
    parser.add_argument("--endurance-hours", type=float, default=72, help="耐久测试时长(小时)")
    parser.add_argument("--log-path", default="./logs/app.log")
    parser.add_argument("--output-dir", default="./stress_test_results")
    parser.add_argument("--skip-endurance", action="store_true", help="跳过耐久测试")
    parser.add_argument("--admin-username", default="", help="管理员用户名（用于预创建测试用户）")
    parser.add_argument("--admin-password", default="", help="管理员密码")
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    endurance_hours = 0 if args.skip_endurance else args.endurance_hours

    asyncio.run(run_all(
        base_url=args.base_url,
        sip_host=args.sip_host,
        sip_port=args.sip_port,
        token=args.token,
        channels=channels,
        device_count=args.device_count,
        user_count=args.user_count,
        user_prefix=args.user_prefix,
        password=args.password,
        preview_duration=args.preview_duration,
        endurance_hours=endurance_hours,
        log_path=args.log_path,
        output_dir=args.output_dir,
        admin_username=args.admin_username,
        admin_password=args.admin_password,
    ))


if __name__ == "__main__":
    main()
