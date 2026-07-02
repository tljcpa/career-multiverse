#!/usr/bin/env python3
"""Playwright 连续录屏：一个 context 跑完整流程，session 保持"""

import asyncio, os
from playwright.async_api import async_playwright

SITE = "https://multiverse.zdwktlj.top"
OUTDIR = "/tmp/video-segments"
SCREENSHOT_DIR = "/tmp/video-screenshots"
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 每段等待秒数（TTS 0% 速率 162s + 视觉留白 → 目标 300s）
SEG_WAITS = [20, 20, 55, 70, 50, 50, 25, 10]  # 合计 300s (5:00)

async def main():
    print("=== Playwright 连续录屏 ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=OUTDIR,
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # === 段1: 钩子 — 打开首页，上传页 ===
        print("段1: 钩子")
        await page.goto(SITE, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/01-upload.png", full_page=True)
        await page.wait_for_timeout(SEG_WAITS[0] * 1000 - 2000)

        # === 段2: 产品定位 — 留在首页 ===
        print("段2: 定位")
        await page.wait_for_timeout(SEG_WAITS[1] * 1000)

        # === 段3: 上传评估 — 点击 Demo → Profile ===
        print("段3: 上传+评估")
        # 找"使用 Demo 数据"按钮
        try:
            demo_btn = page.get_by_text("Demo", exact=False).first
            await demo_btn.click(timeout=5000)
        except:
            # fallback: 找任何含"Demo"的按钮
            btns = page.locator("button")
            count = await btns.count()
            for i in range(count):
                text = await btns.nth(i).inner_text()
                if "Demo" in text or "demo" in text or "demo" in text.lower():
                    await btns.nth(i).click()
                    break
        # 等跳转到 /profile
        await page.wait_for_url("**/profile**", timeout=20000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/03-profile.png", full_page=True)
        await page.wait_for_timeout(SEG_WAITS[2] * 1000 - 4000)

        # === 段4: 3D 沙盘 ===
        print("段4: 沙盘")
        await page.goto(f"{SITE}/sandbox", wait_until="networkidle")
        await page.wait_for_timeout(6000)  # 等 Three.js
        await page.screenshot(path=f"{SCREENSHOT_DIR}/04-sandbox.png", full_page=True)
        # force-click canvas bypass overlay
        canvas = page.locator("canvas").first
        if await canvas.count() > 0:
            try:
                await canvas.click(position={"x": 500, "y": 300}, force=True, timeout=3000)
                await page.wait_for_timeout(2000)
            except:
                pass
        await page.wait_for_timeout(SEG_WAITS[3] * 1000 - 8000)

        # === 段5: 1000次报告 ===
        print("段5: 报告")
        await page.goto(f"{SITE}/report", wait_until="networkidle")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/05-report.png", full_page=True)
        await page.wait_for_timeout(SEG_WAITS[4] * 1000 - 4000)

        # === 段6: 反事实滑动条 ===
        print("段6: 反事实")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/06-counterfactual.png", full_page=True)
        # 操作滑动条
        sliders = page.locator('input[type="range"]')
        cnt = await sliders.count()
        if cnt > 0:
            await sliders.first.fill("85")
            await page.wait_for_timeout(2000)
        if cnt > 1:
            await sliders.nth(1).fill("80")
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(SEG_WAITS[5] * 1000 - 4000)

        # === 段7: 市场看板 ===
        print("段7: 看板")
        await page.goto(f"{SITE}/dashboard", wait_until="networkidle")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/07-dashboard.png", full_page=True)
        await page.wait_for_timeout(SEG_WAITS[6] * 1000 - 4000)

        # === 段8: 结语 ===
        print("段8: 结语")
        await page.goto(SITE, wait_until="networkidle")
        await page.wait_for_timeout(SEG_WAITS[7] * 1000)

        # 收尾
        await page.wait_for_timeout(2000)
        await context.close()
        await browser.close()

    # 重命名录好的视频文件
    import glob, time
    time.sleep(2)
    videos = sorted(glob.glob(f"{OUTDIR}/*.webm"), key=os.path.getmtime, reverse=True)
    if videos:
        new_path = os.path.join(OUTDIR, "full-recording.webm")
        os.rename(videos[0], new_path)
        print(f"\n完整视频: {new_path}")

    print("截图保存在", SCREENSHOT_DIR)

if __name__ == "__main__":
    asyncio.run(main())
