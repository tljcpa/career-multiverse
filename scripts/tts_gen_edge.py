"""
edge-tts 版旁白合成（免费，不依赖 Azure 订阅）。

背景：旧 Azure 订阅停用后 Speech 不可用，且失败的合成把本地 mp3 覆盖坏了。
改用 edge-tts（微软在线 TTS，免费、无需 key），同款云希男声 zh-CN-YunxiNeural，
复用 tts_gen.py 里已升维的旁白文案 SEGMENTS 和 _write_srt（SRT 字幕生成）。

产物：backend/data/video/01.mp3 ~ 08.mp3 + 同名 .srt
下一步：build_video.sh 合成。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import edge_tts

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_gen import SEGMENTS, _write_srt, PROJECT_ROOT  # noqa: E402

VOICE = "zh-CN-YunxiNeural"
RATE = "+5%"


async def gen_segment(seg: dict) -> Path:
    out_dir = PROJECT_ROOT / "backend" / "data" / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3 = out_dir / f"{seg['id']}.mp3"
    srt = out_dir / f"{seg['id']}.srt"

    communicate = edge_tts.Communicate(seg["text"], VOICE, rate=RATE)
    words: list[dict] = []
    with open(mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # edge-tts offset/duration 单位 100ns，与 azure 一致，/10000 = ms
                words.append({
                    "text": chunk["text"],
                    "offset_ms": chunk["offset"] / 10000,
                    "duration_ms": chunk["duration"] / 10000,
                })
    # 复用 tts_gen 的 SRT 生成（按 ~12 字 / 3 秒聚合）
    _write_srt(seg["text"], words, srt)
    return mp3


async def main() -> None:
    for seg in SEGMENTS:
        print(f"合成段 {seg['id']}: {len(seg['text'])} 字符")
        try:
            mp3 = await gen_segment(seg)
            print(f"  -> {mp3.name} ok")
        except Exception as e:
            print(f"  [FAIL] {seg['id']}: {e}")
    print("全部完成。下一步 build_video.sh")


if __name__ == "__main__":
    asyncio.run(main())
