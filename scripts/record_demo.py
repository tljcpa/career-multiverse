"""
Playwright 录屏 v3：对齐当前真实实现 + 预热注入 session 解决数据断流。

v2 → v3 的关键修复：
1. 路由对齐：旧版等 `#/finetuning`（该路由已删除）。真实流程是
   /upload → 点"使用 Demo 数据" → /profile（自动起 sim）→ /sandbox。
2. 数据断流修复：sandbox / report / counterfactual 页都靠 sessionStorage 里的
   simSessionId 才有数据。旧版每段开独立 browser context，context 之间
   sessionStorage 不共享 → 段 04/05/06 录到空沙盘 / 报错报告页。
   v3 先用 API 预热一个「跑到 done」的 sim，拿到 (user_id, sim_session_id)，
   再用 page.add_init_script 在每个 context 加载前把它写进 sessionStorage
   （key=multiverse_session_v1），页面秒出真实数据。
3. BASE 指向线上：本机不跑前端，前端在 multiverse.zdwktlj.top。
4. 段 03 改为录「上传 → 五维画像 + 评分构成 + 评分参考」，与新旁白一致
   （旁白已去掉 RAG/向量索引的假叙事）。

依赖：playwright（python 包 + chromium）、本机能访问线上 URL。
产物：backend/data/video/clips/03-upload.webm ~ 07-dashboard.webm
下一步：build_video.sh 合成。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.async_api import Page, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 线上站点（本机不跑前端，录线上）
BASE = "http://multiverse.zdwktlj.top/"
API = "http://multiverse.zdwktlj.top/api"
VIEWPORT = {"width": 1920, "height": 1080}

# 产物目录：与 build_video.sh 的 CLIPS_DIR 默认值（$ROOT/backend/data/video/clips）一致
OUT = PROJECT_ROOT / "backend" / "data" / "video" / "clips"
OUT.mkdir(parents=True, exist_ok=True)

# 旁白 mp3 目录（本机 tts_gen.py 的输出位置）
TTS_DIR = PROJECT_ROOT / "backend" / "data" / "video"

# sessionStorage 持久化 key（见 frontend/src/stores/session.ts）
STORAGE_KEY = "multiverse_session_v1"

# 用于演示的简历（写实，对应旁白里的"五维画像"）
DEMO_RESUME = (
    "赵明，浙江大学计算机科学与技术本科，2024 届。"
    "阿里巴巴后端开发实习 6 个月，负责交易链路高并发优化。"
    "GPA 3.8/4.0，专业前 10%。"
    "主导 3 个深度项目：分布式缓存中间件、RAG 知识库、高并发秒杀系统。"
    "两个开源项目累计 800 star。ACM-ICPC 区域赛银牌。"
    "掌握 Go / Java / Python / Redis / Kubernetes。目标岗位：后端开发工程师。"
)


def _api_post(path: str, payload: dict) -> dict:
    """POST JSON 到后端，返回解析后的 dict"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_upload_demo_resume() -> str:
    """用 multipart 上传 demo 简历，返回 user_id。
    用 urllib 手搓 multipart（避免引第三方依赖）"""
    boundary = "----multiversedemoboundary"
    parts = []
    # resume_file 字段
    parts.append(f"--{boundary}")
    parts.append('Content-Disposition: form-data; name="resume_file"; filename="demo.md"')
    parts.append("Content-Type: text/markdown")
    parts.append("")
    parts.append(DEMO_RESUME)
    # 空的 github/blog/extra（后端 Form 默认值即可，可省略）
    parts.append(f"--{boundary}--")
    parts.append("")
    body = "\r\n".join(parts).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/candidate/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["user_id"]


def _api_upload_demo_persona() -> str:
    """走"使用 Demo 数据"等价路径：上传一个空 multipart（无 resume_file），
    后端走 demo 分支返回内置 persona（王明 / C9 / 硕士）。
    这样预热注入的 session 和段 03 点 Demo 按钮看到的是同一个人，全片人物一致。"""
    boundary = "----multiversedemoboundary"
    body = f"--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"{API}/candidate/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["user_id"]


def prewarm_session() -> tuple[str, str]:
    """录屏前预热：上传 demo persona → 起 sim → 轮询到 done。
    返回 (user_id, sim_session_id)，供 record 时注入 sessionStorage。
    用 demo persona（王明）保证和段 03 点 Demo 按钮看到的是同一个人。"""
    print("[预热] 创建 demo persona（王明，与段 03 一致）...")
    user_id = _api_upload_demo_persona()
    print(f"[预热] user_id={user_id}")

    print("[预热] 启动 1000 次 sim...")
    sid = _api_post("/simulation/start", {"user_id": user_id, "n_runs": 1000})["sim_session_id"]
    print(f"[预热] sim_session_id={sid}，等待跑完...")

    for i in range(40):  # 最多等 ~5 分钟
        status = _api_get(f"/simulation/status/{sid}")
        if status.get("stage") == "done":
            print(f"[预热] sim 完成（第 {i} 次轮询）")
            return user_id, sid
        time.sleep(8)
    print("[预热] 警告：sim 未在超时内完成，仍继续（页面可能走 mock 兜底）")
    return user_id, sid


def _audio_duration_sec(mp3_path: Path) -> float:
    """用 ffprobe 拿 mp3 时长"""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)],
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return 30.0


async def record_segment(p, seg_id: str, action_fn, target_duration: float,
                         session_payload: dict) -> Path | None:
    """录一段。每段独立 context，但通过 add_init_script 预注入 session，
    保证 sandbox/report 等页面加载即有真实数据（修 v2 数据断流）"""
    target_dir = OUT / seg_id
    target_dir.mkdir(exist_ok=True)
    # 清掉上次运行残留的 webm，否则下面 glob 可能挑到旧文件 rename，新录的反而留成 hash 名
    for stale in target_dir.glob("*.webm"):
        stale.unlink()

    browser = await p.chromium.launch(headless=True, args=["--use-gl=swiftshader",
                                                           "--enable-webgl",
                                                           "--ignore-gpu-blocklist"])
    ctx = await browser.new_context(
        viewport=VIEWPORT,
        record_video_dir=str(target_dir),
        record_video_size=VIEWPORT,
    )
    # 关键：页面任何脚本执行前，先把 session 写进 sessionStorage
    init_js = (
        "try { sessionStorage.setItem(" + json.dumps(STORAGE_KEY) + ", "
        + json.dumps(json.dumps(session_payload)) + "); } catch (e) {}"
    )
    await ctx.add_init_script(init_js)

    page = await ctx.new_page()

    start = asyncio.get_event_loop().time()
    try:
        await action_fn(page)
    except Exception as e:
        print(f"  [WARN] {seg_id} action 异常: {e}")

    elapsed = asyncio.get_event_loop().time() - start
    remaining = target_duration - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)

    await ctx.close()
    await browser.close()

    for f in target_dir.glob("*.webm"):
        new_name = target_dir / f"{seg_id}.webm"
        f.rename(new_name)
        sz = new_name.stat().st_size / 1024
        print(f"  → {seg_id}.webm  {sz:.0f} KB  目标 {target_duration:.1f}s")
        return new_name
    return None


# ============ 各段 action 函数 ============

async def action_03_upload(page: Page):
    """段 3：上传页 → 点 Demo → Profile 五维画像 + 评分构成 + 评分参考。
    与新旁白一致（LLM 一次性评估，不再是 finetuning 动画）"""
    await page.goto(BASE + "#/upload", wait_until="domcontentloaded")
    await asyncio.sleep(4)  # 看清上传页
    btn = await page.query_selector('button:has-text("使用 Demo 数据")')
    if btn:
        await btn.hover()
        await asyncio.sleep(1)
        await btn.click()
    # 跳到 /profile
    try:
        await page.wait_for_url("**/profile", timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(4)  # 等五维评分卡渲染
    # 展开"查看评分构成"
    for sel in ['button:has-text("评分构成")', 'button:has-text("83 是怎么算的")',
                'button:has-text("查看评分构成")']:
        b = await page.query_selector(sel)
        if b:
            await b.click()
            await asyncio.sleep(3)
            break
    # 展开"评分参考标准"
    rb = await page.query_selector('button:has-text("评分参考标准")')
    if rb:
        await rb.click()
        await asyncio.sleep(3)
        # 关掉弹窗避免遮挡后续
        close = await page.query_selector('button:has-text("关闭"), button:has-text("×")')
        if close:
            await close.click()


async def action_04_sandbox(page: Page):
    """段 4：3D 沙盘浏览"""
    await page.goto(BASE + "#/sandbox", wait_until="domcontentloaded")
    await asyncio.sleep(4)  # 3D 渲染
    try:
        canvas = await page.query_selector("canvas")
        if canvas:
            box = await canvas.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                for dx in [-150, 150, 0, -80, 80, 0]:
                    await page.mouse.move(cx + dx, cy, steps=12)
                    await asyncio.sleep(1.2)
    except Exception:
        pass


async def action_05_report(page: Page):
    """段 5：1000 次报告 KPI + 图表"""
    await page.goto(BASE + "#/report", wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("svg", timeout=60000)
    except Exception:
        pass
    await asyncio.sleep(3)
    await page.evaluate("window.scrollTo({top: 200, behavior: 'smooth'})")
    await asyncio.sleep(5)
    await page.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
    await asyncio.sleep(5)


async def action_06_counterfactual(page: Page):
    """段 6：反事实滑动条真拖动"""
    await page.goto(BASE + "#/report", wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("svg", timeout=60000)
    except Exception:
        pass
    await page.evaluate("window.scrollTo({top: document.body.scrollHeight - 200, behavior: 'smooth'})")
    await asyncio.sleep(3)
    sliders = await page.query_selector_all('input[type="range"]')
    # 用键盘方向键拖动：focus 滑块后按 ArrowRight N 次，每次 +step。
    # 这是真实用户交互，Vue 的 v-model 一定接得住（之前直接 set el.value 反而被 Vue 忽略）。
    # 三个滑块目标 delta：简历质量 +10、项目含金量 +15、学校等级 +1
    steps = [10, 15, 1]
    for idx, slider in enumerate(sliders[:3]):
        await slider.focus()
        await asyncio.sleep(0.5)
        for _ in range(steps[idx]):
            await slider.press("ArrowRight")
            await asyncio.sleep(0.08)  # 让 UI 跟上，呈现"拖动"动感
        await asyncio.sleep(3.5)  # 停留看反事实结果变化


async def action_07_dashboard(page: Page):
    """段 7+8：市场全景 dashboard"""
    await page.goto(BASE + "#/dashboard", wait_until="domcontentloaded")
    await asyncio.sleep(8)
    await page.evaluate("window.scrollTo({top: 500, behavior: 'smooth'})")
    await asyncio.sleep(8)


async def main():
    # 1. 预热：拿一个跑到 done 的真实 sim session
    user_id, sim_session_id = prewarm_session()
    session_payload = {
        "userId": user_id,
        "simSessionId": sim_session_id,
        "hasUploaded": True,
    }
    print(f"[注入] session_payload={session_payload}")
    print()

    # 2. 各段录制计划
    # fallback 故意设小（20s）：让"旁白 mp3 实际时长 + 1.5s"驱动每段录制长度，
    # 避免视频段比旁白长导致末尾大段静音。各段旁白实测：
    # 03≈62s（01+02+03）/ 04≈30s / 05≈25s / 06≈26s / 07≈30s（07+08）
    plan = [
        ("03-upload", action_03_upload, 20),
        ("04-sandbox", action_04_sandbox, 20),
        ("05-report", action_05_report, 20),
        ("06-counterfactual", action_06_counterfactual, 20),
        ("07-dashboard", action_07_dashboard, 20),
    ]
    # 每段对应旁白 mp3（决定录制时长）
    mp3_map = {
        "03-upload": ["01.mp3", "02.mp3", "03.mp3"],
        "04-sandbox": ["04.mp3"],
        "05-report": ["05.mp3"],
        "06-counterfactual": ["06.mp3"],
        "07-dashboard": ["07.mp3", "08.mp3"],
    }

    async with async_playwright() as p:
        for seg_id, action_fn, fallback in plan:
            total = 0.0
            for mp3 in mp3_map.get(seg_id, []):
                mp = TTS_DIR / mp3
                if mp.exists():
                    total += _audio_duration_sec(mp)
            target = max(total + 1.5, fallback) if total > 0 else fallback
            print(f"[{seg_id}] 目标 {target:.1f}s")
            await record_segment(p, seg_id, action_fn, target, session_payload)

    print()
    print("=== 全部录制完成 ===")
    for d in sorted(OUT.iterdir()):
        if d.is_dir():
            for f in d.glob("*.webm"):
                print(f"  {f.relative_to(OUT)}  {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    asyncio.run(main())
