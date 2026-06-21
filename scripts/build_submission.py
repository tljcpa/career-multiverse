"""
组装智联 AI 大赛提交压缩包。

转换链路（本机只有 pandoc + chromium，无 xelatex/libreoffice）：
- md -> pdf：pandoc 转 html（内嵌中文 CSS）-> chromium headless 打印 PDF（noto-cjk 字体）
- md -> docx：pandoc 原生转
- mp4：直接拷贝并按提交顺序重命名

按提交表单三槽位组织目录后打 zip。
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/root/智联AI比赛")
SUB = ROOT / "docs" / "submission"
VIDEO = ROOT / "dist" / "tljcpa+求职+春招平行宇宙+演示视频.mp4"
OUT = ROOT / "dist" / "智联AI大赛提交-春招平行宇宙"
WORK = ROOT / "dist" / "_submission_work"

# 打印用 CSS（中文字体 + 可读排版）
CSS = """
body{font-family:'Noto Sans CJK SC','WenQuanYi Zen Hei',sans-serif;max-width:840px;
margin:0 auto;line-height:1.7;color:#1a1a1a;padding:8px 28px;}
h1{font-size:25px;border-bottom:3px solid #6b46c1;padding-bottom:8px;margin-top:18px;}
h2{font-size:19px;color:#5b3aa8;margin-top:26px;border-left:4px solid #6b46c1;padding-left:10px;}
h3{font-size:15px;color:#333;margin-top:18px;}
table{border-collapse:collapse;width:100%;margin:12px 0;}
th,td{border:1px solid #ccc;padding:6px 10px;font-size:12.5px;vertical-align:top;}
th{background:#f0ebfa;}
code{background:#f4f4f4;padding:2px 5px;border-radius:3px;font-size:12px;}
pre{background:#f7f7f7;padding:12px;border-radius:6px;overflow-x:auto;font-size:11.5px;line-height:1.45;}
blockquote{border-left:4px solid #c4b5e0;margin:0 0 12px;padding:4px 14px;color:#555;background:#faf8fd;}
ul,ol{padding-left:22px;}
li{margin:3px 0;}
"""


def md_to_html(md: Path, html: Path) -> None:
    """pandoc md -> standalone html，内嵌 CSS"""
    header = WORK / "header.html"
    header.write_text(f"<style>{CSS}</style>", encoding="utf-8")
    subprocess.run(
        ["pandoc", str(md), "-s", "-H", str(header), "--metadata", "title=",
         "-o", str(html)],
        check=True,
    )


def md_to_docx(md: Path, docx: Path) -> None:
    """pandoc md -> docx（复赛附件用 word）"""
    subprocess.run(["pandoc", str(md), "-o", str(docx)], check=True)


async def html_to_pdf(html: Path, pdf: Path) -> None:
    """chromium headless 打印 PDF（中文字体已装）"""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        pg = await b.new_page()
        await pg.goto(f"file://{html}", wait_until="networkidle")
        await pg.pdf(
            path=str(pdf), format="A4", print_background=True,
            margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
        )
        await b.close()


async def main():
    # 清理 + 建目录
    if OUT.exists():
        shutil.rmtree(OUT)
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    d1 = OUT / "01-说明文档"
    d2 = OUT / "02-演示文件"
    d3 = OUT / "03-作品附件"
    for d in (d1, d2, d3):
        d.mkdir(parents=True)

    # ---- 01 说明文档（PDF）----
    h = WORK / "manual.html"
    md_to_html(SUB / "产品说明书.md", h)
    await html_to_pdf(h, d1 / "春招平行宇宙-产品说明书.pdf")
    print("[01] 产品说明书.pdf 完成")

    # ---- 02 演示文件（mp4 + PPT pdf）----
    shutil.copy(VIDEO, d2 / "01-春招平行宇宙-演示视频.mp4")
    print("[02] 演示视频.mp4 已拷贝")
    h2 = WORK / "ppt.html"
    md_to_html(SUB / "PPT-20-pages.md", h2)
    await html_to_pdf(h2, d2 / "02-春招平行宇宙-演示PPT.pdf")
    print("[02] 演示PPT.pdf 完成")

    # ---- 03 作品附件（word）----
    md_to_docx(SUB / "BP.md", d3 / "春招平行宇宙-商业计划书BP.docx")
    md_to_docx(SUB / "数据合规声明.md", d3 / "数据合规声明.docx")
    md_to_docx(SUB / "作品原创说明及授权书.md", d3 / "作品原创说明及授权书（待E签宝签署）.docx")
    print("[03] 3 个 word 附件完成")

    # ---- 提交清单 ----
    (OUT / "提交清单.txt").write_text(
        "智联招聘首届全国 AI 创新大赛 · 提交材料\n"
        "作品：春招平行宇宙 / Career Multiverse  赛道：AI + 求职  作者：tljcpa\n"
        "在线 demo：http://multiverse.zdwktlj.top/\n\n"
        "【说明文档槽位】上传 01-说明文档/春招平行宇宙-产品说明书.pdf\n"
        "【演示文件槽位】上传 02-演示文件/ 下两个文件（视频 + PPT，已按 01/02 标顺序）\n"
        "【作品附件槽位】上传 03-作品附件/ 下 word 文件\n\n"
        "注意：授权书 docx 为草稿，正式提交请通过 E 签宝完成电子签名后再上传。\n"
        "BP 里微信号一项待补（其余联系方式已填）。\n",
        encoding="utf-8",
    )

    # ---- 打包 zip ----
    zip_base = str(ROOT / "dist" / "智联AI大赛提交-春招平行宇宙")
    shutil.make_archive(zip_base, "zip", root_dir=OUT.parent, base_dir=OUT.name)
    print(f"\n=== 压缩包完成: {zip_base}.zip ===")
    # 列内容
    for f in sorted(OUT.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(OUT)}  ({f.stat().st_size//1024} KB)")


if __name__ == "__main__":
    asyncio.run(main())
