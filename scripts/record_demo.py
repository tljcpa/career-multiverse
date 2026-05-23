"""
Playwright 录屏脚本：在 Azure VM 上跑，按 video-script-final.md 的分段录制 8 段 mp4。

为什么不一次录完整段（让 ffmpeg 后期切）：
1. 每段时长精确控制，与 TTS 旁白严格对齐
2. 录错一段重录单段即可，不用重跑整个用户旅程
3. 失败重试只需重跑挂掉的段

使用：在 VM 上 `python scripts/record_demo.py`，
产物 mp4 在 ~/e2e-demo-clips/
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUT = Path("/home/azureuser/e2e-demo-clips")
OUT.mkdir(exist_ok=True)
BASE = "http://localhost/"

# 视频规格
VIEWPORT = {"width": 1920, "height": 1080}
VIDEO_SIZE = VIEWPORT


async def section_3_upload(page: Page) -> None:
    """段 3：上传 + AI 认识你 (47 秒)"""
    await page.goto(BASE, wait_until="domcontentloaded")
    await page.wait_for_url("**/#/upload", timeout=15000)
    await asyncio.sleep(3)  # 让评委看清上传页

    # 鼠标缓慢移动到"使用 Demo 数据"按钮
    btn = await page.query_selector('button:has-text("使用 Demo 数据")')
    if btn is not None:
        await btn.hover()
        await asyncio.sleep(1.5)
        await btn.click()

    # 等跳到 finetuning，停留拍 4 阶段进度（mock 端 12 秒动画）
    await page.wait_for_url("**/#/finetuning", timeout=30000)
    # 整个 finetuning 动画跑完 + 跳到 sandbox 之前留出来
    await asyncio.sleep(35)


async def section_4_sandbox(page: Page) -> None:
    """段 4：3D 沙盘 (60 秒)。前提：已经在 sandbox 页或 finetuning 自动跳过来"""
    # 确保在 sandbox
    try:
        await page.wait_for_url("**/#/sandbox", timeout=120000)
    except Exception:
        await page.goto(BASE + "#/sandbox", wait_until="domcontentloaded")
    await asyncio.sleep(8)  # 3D 沙盘渲染 + 让相机转一圈

    # 镜头：点击焰火节点 → 弹 HR 采访
    # 焰火是第一家公司，找含"焰火"标签的节点
    # （Sandbox3D.vue 用 emit 触发 click，无法 selector 点 mesh
    #  → 改成点列表/按钮，如果没有该按钮，跳过）
    try:
        focal = await page.query_selector('[data-company-code="焰火"]')
        if focal:
            await focal.click()
            await asyncio.sleep(3)
    except Exception:
        pass

    # 总时长留满
    await asyncio.sleep(15)


async def section_5_report(page: Page) -> None:
    """段 5：1000 次报告 (60 秒)"""
    # 找"查看 1000 次平行宇宙报告"按钮
    btn = await page.query_selector('button:has-text("查看 1000 次平行宇宙报告")')
    if btn is not None:
        await btn.click()

    await page.wait_for_url("**/#/report", timeout=30000)
    # 等图表加载
    try:
        await page.wait_for_selector("svg", timeout=60000)
    except Exception:
        pass
    await asyncio.sleep(20)  # 让评委看到 4 图表 + KPI

    # 滚到决策树位置
    await page.evaluate("window.scrollBy(0, 600)")
    await asyncio.sleep(15)


async def section_6_counterfactual(page: Page) -> None:
    """段 6：反事实滑动条 (55 秒)"""
    # 滚到反事实区域（页面下半）
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(5)

    # 找滑动条
    sliders = await page.query_selector_all('input[type="range"]')
    if sliders and len(sliders) >= 2:
        # 慢慢拖动第 1 个滑动条（项目含金量）+15
        await sliders[0].evaluate('(el, v) => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })) }', "15")
        await asyncio.sleep(4)
        # 第 2 个滑动条（简历质量）-20
        await sliders[1].evaluate('(el, v) => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })) }', "-20")
        await asyncio.sleep(4)
        # 还原项目含金量
        await sliders[1].evaluate('(el, v) => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })) }', "0")
        await asyncio.sleep(3)
    # 留够时长
    await asyncio.sleep(15)


async def section_7_dashboard(page: Page) -> None:
    """段 7（部分）：dashboard 看板 (30 秒)"""
    await page.goto(BASE + "#/dashboard", wait_until="domcontentloaded")
    await asyncio.sleep(8)  # 等图表加载
    # 截图位置滚动
    await page.evaluate("window.scrollTo(0, 400)")
    await asyncio.sleep(15)


async def record_section(
    p, name: str, action_coro_factory, duration_min: int
) -> None:
    """录制单段。
    name: 输出文件名前缀，e.g. '03-upload'
    action_coro_factory: 接受 page，返回 awaitable 的函数
    duration_min: 最少录制秒数（避免动作快导致视频太短）"""
    target_dir = OUT / name
    target_dir.mkdir(exist_ok=True)

    browser = await p.chromium.launch(headless=True)
    ctx = await browser.new_context(
        viewport=VIEWPORT,
        record_video_dir=str(target_dir),
        record_video_size=VIDEO_SIZE,
    )
    page = await ctx.new_page()

    start = time.time()
    try:
        await action_coro_factory(page)
    except Exception as e:
        print(f"  [WARN] {name} 录制异常: {e}")

    # 保证最少时长
    elapsed = time.time() - start
    if elapsed < duration_min:
        await asyncio.sleep(duration_min - elapsed)

    # close context 才会 flush video
    await ctx.close()
    await browser.close()

    # video 文件命名是 playwright 内部生成的 hash，rename 一下
    for f in target_dir.glob("*.webm"):
        new_name = f.parent / f"{name}.webm"
        f.rename(new_name)
        print(f"  {name}: {new_name.name}  {new_name.stat().st_size / 1024:.0f} KB")


async def main():
    async with async_playwright() as p:
        # 段 3 + 段 4：上传 + 微调动画 + sandbox 一气录完（因为有路由自动跳转）
        # 实际后期 ffmpeg 切分
        async def full_journey(page):
            await section_3_upload(page)
            # finetuning 自动跳 sandbox
            await section_4_sandbox(page)
            await section_5_report(page)
            await section_6_counterfactual(page)

        await record_section(p, "full-journey", full_journey, duration_min=240)

        # dashboard 单独一段
        await record_section(p, "dashboard", section_7_dashboard, duration_min=30)

    print()
    print("=== 全部录制完成 ===")
    for d in OUT.iterdir():
        for f in d.glob("*.webm"):
            print(f"  {f.relative_to(OUT)}  {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    asyncio.run(main())
