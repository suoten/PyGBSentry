#!/usr/bin/env python
"""
逐页前端验收测试：使用 Playwright 自动化浏览器访问每个路由，
检查白屏、控制台红色 error、404 资源加载。

会话策略：
1. 启动浏览器，访问 /login 登录
2. 登录成功后，保存 localStorage 中的 token
3. 依次访问每个路由，每次访问前注入 token
4. 收集控制台错误和网络 404
"""
import json
import sys
import time
from pathlib import Path

# FIX: [验收脚本] Windows 默认 stdout 编码为 GBK，无法输出 emoji（✅⚠️❌）。
# reconfigure 为 UTF-8 以避免 UnicodeEncodeError。
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"
USERNAME = "admin"
PASSWORD = "admin123"

# 所有可能的前端路由（基于 router/index.ts）
ROUTES = [
    "/dashboard",
    "/monitor",
    "/map",
    "/health",
    "/sla",
    "/alarms",
    "/alarm-notifications",
    "/alarm-link-rules",
    "/work-orders",
    "/devices",
    "/push-streams",
    "/pull-proxies",
    "/legacy-gateway",
    "/platforms",
    "/ai-vision",
    "/channels",
    "/channels/legacy",
    "/channels/region",
    "/channels/group",
    "/device-records",
    "/cloud-records",
    "/record-schedule",
    "/users",
    "/roles",
    "/api-keys",
    "/organizations",
    "/ops",
    "/asset-management",
    "/network",
    "/stream-optimization",
    "/map-providers",
    "/config-center",
    "/release-center",
    "/audit-center",
    "/reports",
    "/suite-center",
    "/help",
    "/plugins",
    "/profile",
    "/account-security",
]


def login(page):
    """登录并保存 token"""
    print("[1] 登录中...")
    page.goto(f"{FRONTEND_URL}/login", wait_until="domcontentloaded", timeout=30000)

    # 等待登录表单渲染（Element Plus 的 input 在 el-input 内部）
    try:
        # 等待 password input 出现
        page.wait_for_selector("input[type='password']", timeout=15000)
        page.wait_for_timeout(1000)
        print("  ✓ 登录表单已加载")
    except Exception as e:
        print(f"  ⚠️ 等待登录表单超时: {e}")
        # 检查页面是否已经登录（直接跳转到了 dashboard）
        if "/login" not in page.url:
            print(f"  ✓ 已登录，当前 URL: {page.url}")
            return page.evaluate("""() => {
                const keys = Object.keys(sessionStorage);
                const tokenKeys = keys.filter(k => k.toLowerCase().includes('token'));
                const result = {};
                tokenKeys.forEach(k => result[k] = sessionStorage.getItem(k));
                return result;
            }""")
        return None

    # 填写登录表单 - 使用更精确的选择器
    try:
        # 第一个 input 是用户名，第二个是密码
        inputs = page.query_selector_all("input")
        if len(inputs) >= 2:
            username_input = inputs[0]
            password_input = inputs[1]
            username_input.fill(USERNAME)
            password_input.fill(PASSWORD)
            print(f"  ✓ 已填写用户名和密码")

            # 找登录按钮 - Element Plus 的按钮
            login_btn = page.query_selector("button.login-btn") or \
                        page.query_selector("button.el-button--primary") or \
                        page.query_selector("button:has-text('登录')") or \
                        page.query_selector("button:has-text('Login')") or \
                        page.query_selector("button[type='submit']")
            if login_btn:
                login_btn.click()
                page.wait_for_timeout(3000)
                print("  ✓ 登录按钮已点击")
            else:
                # 按 Enter 提交
                password_input.press("Enter")
                page.wait_for_timeout(3000)
                print("  ✓ 按 Enter 提交")
        else:
            print(f"  ⚠️ 未找到足够的 input 元素 (找到 {len(inputs)} 个)")
            return None
    except Exception as e:
        print(f"  ⚠️ 登录异常: {e}")
        return None

    # 等待跳转
    page.wait_for_timeout(3000)
    current_url = page.url
    print(f"  当前 URL: {current_url}")

    # 验证是否登录成功（检查 sessionStorage 中是否有 token）
    token_data = page.evaluate("""() => {
        const keys = Object.keys(sessionStorage);
        const tokenKeys = keys.filter(k => k.toLowerCase().includes('token'));
        const result = {};
        tokenKeys.forEach(k => result[k] = sessionStorage.getItem(k));
        return result;
    }""")
    print(f"  sessionStorage token keys: {list(token_data.keys())}")

    if not token_data:
        # 尝试从 cookie 获取
        cookies = page.context.cookies()
        print(f"  Cookies: {[c['name'] for c in cookies]}")

    return token_data


def inject_token(page, token_data):
    """在页面上注入 token（前端使用 sessionStorage 存储 token）"""
    if not token_data:
        return
    js_code = "sessionStorage.clear();\n"
    for k, v in token_data.items():
        js_code += f"sessionStorage.setItem({json.dumps(k)}, {json.dumps(v)});\n"
    page.evaluate(js_code)


def test_route(page, route, console_errors, network_404s, network_errors):
    """测试单个路由"""
    result = {
        "route": route,
        "status": "✅正常",
        "white_screen": False,
        "console_errors": [],
        "resource_404": [],
        "network_errors": [],
        "redirected": False,
        "final_url": "",
        "notes": "",
    }

    # 清空之前的错误记录
    console_errors.clear()
    network_404s.clear()
    network_errors.clear()

    try:
        # 访问路由
        page.goto(f"{FRONTEND_URL}{route}", wait_until="networkidle", timeout=20000)
    except Exception as e:
        # 超时可能是页面长时间加载（如视频流），继续检查
        if "Timeout" in str(e):
            result["notes"] = "页面加载超时(可能正常)"
        else:
            result["status"] = "❌严重"
            result["notes"] = f"导航异常: {str(e)[:100]}"
            return result

    page.wait_for_timeout(2000)  # 等待页面渲染

    # 检查是否被重定向到 /login
    current_url = page.url
    result["final_url"] = current_url
    if "/login" in current_url and route != "/login":
        result["redirected"] = True
        result["status"] = "⚠️部分问题"
        result["notes"] = "重定向到登录页(session失效)"
        return result

    # 检查白屏：body 是否有可见内容
    try:
        body_text = page.evaluate("""() => {
            const body = document.body;
            if (!body) return '';
            const text = body.innerText || '';
            const html = body.innerHTML || '';
            return text.trim() + '|||' + html.trim();
        }""")
        text_part, html_part = body_text.split("|||", 1) if "|||" in body_text else ("", body_text)
        if len(text_part) < 10 and len(html_part) < 100:
            result["white_screen"] = True
            result["status"] = "❌严重"
            result["notes"] = "页面白屏(body 内容过少)"
    except Exception as e:
        result["notes"] += f" ; 检查白屏异常: {e}"

    # 收集控制台错误
    for err in console_errors:
        # 过滤掉一些已知的无害警告
        if any(keyword in err for keyword in [
            "Download the React DevTools",
            "_Element Plus_",
            "[Vue Warn]",
        ]):
            continue
        result["console_errors"].append(err)

    if result["console_errors"]:
        result["status"] = "⚠️部分问题"

    # 收集 404 资源
    for err_404 in network_404s:
        # 排除一些预期的 404（如地图瓦片）
        if "/map" in route and ("tile" in err_404 or "tiles" in err_404):
            continue
        result["resource_404"].append(err_404)

    if result["resource_404"]:
        result["status"] = "⚠️部分问题"

    # 收集网络错误
    for net_err in network_errors:
        result["network_errors"].append(net_err)

    if result["network_errors"] and result["status"] == "✅正常":
        result["status"] = "⚠️部分问题"

    return result


def main():
    print("=" * 80)
    print("PyGBSentry 前端逐页验收测试")
    print("=" * 80)
    print(f"前端地址: {FRONTEND_URL}")
    print(f"测试路由数: {len(ROUTES)}")
    print()

    results = []

    with sync_playwright() as p:
        # 启动浏览器（headless 模式更快）
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        # 创建页面
        page = context.new_page()

        # 收集控制台错误
        console_errors = []
        console_warnings = []

        def on_console(msg):
            text = msg.text
            if msg.type == "error":
                # 忽略 403/401/503 等业务错误（这些是 API 返回的错误，不是 JS 错误）
                if any(skip in text for skip in [
                    "Failed to load resource",
                    "503",
                    "401",
                    "403",
                    "500",
                    "ERR_",
                ]):
                    return
                console_errors.append(text[:200])
            elif msg.type == "warning":
                console_warnings.append(text[:200])

        page.on("console", on_console)

        # 收集网络错误
        network_404s = []
        network_errors = []

        def on_response(response):
            url = response.url
            status = response.status
            # 只关心前端资源加载的 404，不关心 API 调用的 404
            if status == 404:
                # 排除 API 调用（/api/v1/）的 404，这些已在 API 路由检查中处理
                if "/api/v1/" not in url and "/api/common/" not in url:
                    network_404s.append(f"{status} {url[:150]}")
            elif status >= 500:
                network_errors.append(f"{status} {url[:150]}")

        page.on("response", on_response)

        # 1. 登录
        token_data = login(page)
        if not token_data:
            print("\n❌ 登录失败，无法继续测试")
            browser.close()
            return

        print(f"\n[2] 开始逐页测试 {len(ROUTES)} 个路由...\n")

        # 2. 逐页测试
        for i, route in enumerate(ROUTES, 1):
            print(f"[{i:2d}/{len(ROUTES)}] 测试 {route}...", end=" ")

            # 每次访问前注入 token
            try:
                inject_token(page, token_data)
            except Exception:
                pass

            result = test_route(page, route, console_errors, network_404s, network_errors)
            results.append(result)

            # 输出简要结果
            status_icon = {"✅正常": "✅", "⚠️部分问题": "⚠️", "❌严重": "❌"}.get(result["status"], "?")
            notes = result["notes"][:60] if result["notes"] else ""
            err_count = len(result["console_errors"])
            r404_count = len(result["resource_404"])
            print(f"{status_icon} (errors={err_count}, r404={r404_count}) {notes}")

            # 如果 session 失效，重新登录
            if result["redirected"]:
                print("  → 重新登录...")
                token_data = login(page)

        browser.close()

    # 3. 输出详细报告
    print("\n" + "=" * 80)
    print("逐页验收状态表")
    print("=" * 80)
    print()
    print(f"| # | 路由 | 状态 | 控制台错误 | 404资源 | 备注 |")
    print(f"|---|------|------|-----------|--------|------|")
    for i, r in enumerate(results, 1):
        route = r["route"]
        status = r["status"]
        err_count = len(r["console_errors"])
        r404_count = len(r["resource_404"])
        notes = r["notes"][:50]
        print(f"| {i} | {route} | {status} | {err_count} | {r404_count} | {notes} |")

    # 4. 输出问题汇总
    print("\n" + "=" * 80)
    print("问题汇总")
    print("=" * 80)

    has_issues = False
    for r in results:
        if r["status"] != "✅正常":
            has_issues = True
            print(f"\n【{r['status']}】{r['route']}")
            if r["white_screen"]:
                print(f"  - 白屏")
            if r["redirected"]:
                print(f"  - 重定向: {r['notes']}")
            for err in r["console_errors"][:5]:
                print(f"  - 控制台错误: {err[:150]}")
            for r404 in r["resource_404"][:5]:
                print(f"  - 404资源: {r404[:150]}")
            for net_err in r["network_errors"][:3]:
                print(f"  - 网络错误: {net_err[:150]}")

    if not has_issues:
        print("\n✅ 所有页面验收通过，无任何问题！")

    # 5. 统计
    print("\n" + "=" * 80)
    print("统计")
    print("=" * 80)
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "✅正常")
    warn = sum(1 for r in results if r["status"] == "⚠️部分问题")
    err = sum(1 for r in results if r["status"] == "❌严重")
    print(f"总计: {total} 页")
    print(f"  ✅ 正常: {ok}")
    print(f"  ⚠️ 部分问题: {warn}")
    print(f"  ❌ 严重问题: {err}")

    # 6. 保存报告到文件
    report_path = Path("_page_acceptance_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# PyGBSentry 前端逐页验收报告\n\n")
        f.write(f"- 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 前端地址: {FRONTEND_URL}\n")
        f.write(f"- 测试路由数: {total}\n\n")
        f.write("## 验收状态表\n\n")
        f.write("| # | 路由 | 状态 | 控制台错误数 | 404资源数 | 备注 |\n")
        f.write("|---|------|------|-------------|----------|------|\n")
        for i, r in enumerate(results, 1):
            f.write(f"| {i} | `{r['route']}` | {r['status']} | {len(r['console_errors'])} | {len(r['resource_404'])} | {r['notes'][:50]} |\n")

        f.write("\n## 统计\n\n")
        f.write(f"- ✅ 正常: {ok}/{total}\n")
        f.write(f"- ⚠️ 部分问题: {warn}/{total}\n")
        f.write(f"- ❌ 严重问题: {err}/{total}\n")

        if has_issues:
            f.write("\n## 问题详情\n\n")
            for r in results:
                if r["status"] != "✅正常":
                    f.write(f"### 【{r['status']}】{r['route']}\n\n")
                    if r["white_screen"]:
                        f.write("- ❌ 白屏\n")
                    if r["redirected"]:
                        f.write(f"- ⚠️ 重定向: {r['notes']}\n")
                    for err in r["console_errors"][:10]:
                        f.write(f"- 控制台错误: `{err[:200]}`\n")
                    for r404 in r["resource_404"][:10]:
                        f.write(f"- 404资源: `{r404[:200]}`\n")
                    for net_err in r["network_errors"][:5]:
                        f.write(f"- 网络错误: `{net_err[:200]}`\n")
                    f.write("\n")

    print(f"\n报告已保存至: {report_path.absolute()}")


if __name__ == "__main__":
    main()
