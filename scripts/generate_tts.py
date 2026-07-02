#!/usr/bin/env python3
"""从 JSON 分段文件生成 TTS 音频 (edge-tts)"""

import asyncio, edge_tts, json, os, subprocess

VOICE = "zh-CN-YunxiNeural"
OUTDIR = "/tmp/video-segments"
os.makedirs(OUTDIR, exist_ok=True)

async def gen_one(entry):
    filepath = os.path.join(OUTDIR, f"{entry['file']}.mp3")
    comm = edge_tts.Communicate(entry["text"], VOICE, rate="+0%")
    await comm.save(filepath)
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", filepath],
                       capture_output=True, text=True)
    dur = float(r.stdout.strip())
    print(f"  {entry['file']}.mp3  {dur:.1f}s")
    return dur

async def main():
    with open("/tmp/tts-segments.json") as f:
        segments = json.load(f)
    print(f"=== 生成 {len(segments)} 段 TTS 音频 (voice={VOICE}) ===")
    total = 0
    for seg in segments:
        d = await gen_one(seg)
        total += d
    print(f"\n总时长: {total:.1f}s ({total/60:.1f}min)")
    with open(os.path.join(OUTDIR, "durations.txt"), "w") as f:
        f.write(f"total_duration={total:.1f}\n")

if __name__ == "__main__":
    asyncio.run(main())
