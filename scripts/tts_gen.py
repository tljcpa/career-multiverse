"""
Azure Speech TTS：把 video-script-final.md 的旁白逐段合成 mp3 + srt 字幕。

为什么不用 OpenAI / Edge：
- Azure Speech 学生订阅 free tier 50 万字符/月，永远够用
- zh-CN-YunxiNeural 是温暖男声，自然度好
- 同时返回精确 word-level timestamps，方便生成 srt

使用：本机或 VM 跑 `python scripts/tts_gen.py`
产物：backend/data/video/01.mp3 ~ 08.mp3 + 同名 .srt
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 旁白逐段（与 video-script-final.md 严格对应）
SEGMENTS: list[dict[str, str | float]] = [
    {
        "id": "01",
        "text": "天气可以预报，城市有数字孪生，但人才市场至今只能凭经验决策。应届生凭感觉投出 60 份简历，70% 没有回音；不知道 HR 怎么评价、公司隐性门槛多深、选哪个 offer 三年后不后悔。",
        "duration_s": 18,
    },
    {
        "id": "02",
        "text": "所以我们做了第一个可实验的人才市场——春招平行宇宙。先从应届生春招开始：让 AI 替你跑完 1000 次平行宇宙的春招，看完统计结论再决定怎么投递，而不是赌一次。",
        "duration_s": 20,
    },
    {
        "id": "03",
        "text": "第一步，上传你的简历，可以附上 GitHub 和博客。AI 一次性读完，输出五个维度的内部画像——项目含金量、实习、成就、沟通表达、GPA 分位，每一维都附上评分理由，还会判定你的学校档和学历档。我们不微调任何模型：招聘市场是动态的，公司和求职者随时进出，微调出来的分身今天训练、明天就过期；而 LLM 实时评估，永远基于最新的你和最新的市场。",
        "duration_s": 40,
    },
    {
        "id": "04",
        "text": "化身进入 3D 沙盘宇宙。49 家虚构公司按行业聚成星团，每家都有独立的 HR Agent，每个 HR Agent 都有自己的招聘门槛、文化标签、隐性筛选标准。你能采访任意一家 HR。比如问焰火：你们加班严重吗？它会用真实的 HR 口吻回答你。这是一个动态市场。评委可以现场在治理页加入一家新公司或新求职者，沙盘立刻看到变化。",
        "duration_s": 60,
    },
    {
        "id": "05",
        "text": "1000 次平行春招跑完，结果摆在你面前。你最可能的去向、能拿到几个 offer、中位薪资多少，全是统计结论，不是拍脑袋的建议。简历好的人会海投养鱼，累计拿到十几个 offer——但最终只能去一家，所以真正的问题从来不是能不能拿到，而是该去哪一个。你还能看到全市场画像：49 家公司、96 个 JD、200 名求职者，平均招聘门槛 82 分。",
        "duration_s": 55,
    },
    {
        "id": "06",
        "text": "这是别的 AI 求职工具做不到的：反事实预演。拖动滑动条——把项目含金量再做扎实一点，看平均薪资和 offer 率怎么变；把简历质量调低，看结局怎么退步。AI 不是给你一句空建议，是统计意义上的后悔药：每个改动的真实代价和收益都摆出来，你再决定要不要去打磨那个项目。",
        "duration_s": 50,
    },
    {
        "id": "07",
        "text": "春招平行宇宙已经部署上线，公网随时可访问。商业上，三边收钱：C 端应届生付费跑 sim，B 端给 HR 出反向品牌报告，与招聘平台分润导流。AI 时代的求职决策，从此有了第二次机会。",
        "duration_s": 30,
    },
    {
        "id": "08",
        "text": "本视频由 Playwright 录屏，Azure Speech 合成旁白。工具仅是协作，核心创意原创。春招平行宇宙，让 AI 替你跑 1000 次春招。",
        "duration_s": 10,
    },
]


def _load_azure_creds() -> tuple[str, str]:
    """从 /home/claude/azure/pool.json 读 Speech 凭证"""
    path = Path("/home/claude/azure/pool.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    speech = data["accounts"]["stu-001"]["speech"]
    return speech["key1"], speech["location"]


def synthesize_segment(seg: dict, key: str, region: str) -> tuple[Path, Path]:
    """合成单段 mp3，并生成 srt 字幕。返回 (mp3_path, srt_path)"""
    import azure.cognitiveservices.speech as speechsdk

    out_dir = PROJECT_ROOT / "backend" / "data" / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / f"{seg['id']}.mp3"
    srt_path = out_dir / f"{seg['id']}.srt"

    # SSML：rate +5% 略提速，云希男声
    ssml = f"""<speak version='1.0' xml:lang='zh-CN'>
  <voice name='zh-CN-YunxiNeural'>
    <prosody rate='+5%' pitch='+0%'>{seg['text']}</prosody>
  </voice>
</speak>"""

    cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
    )
    audio_cfg = speechsdk.audio.AudioOutputConfig(filename=str(mp3_path))
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio_cfg)

    # 启用 word boundary 事件，用于生成 srt
    word_events: list[dict] = []
    synth.synthesis_word_boundary.connect(
        lambda evt: word_events.append({
            "text": evt.text,
            "offset_ms": evt.audio_offset / 10000,  # 100ns → ms
            "duration_ms": evt.duration.total_seconds() * 1000,
        })
    )

    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"TTS failed for {seg['id']}: {result.reason}")

    # 生成 srt：按 word boundary 聚合成 2-3 秒一条字幕
    _write_srt(seg["text"], word_events, srt_path)

    return mp3_path, srt_path


def _write_srt(full_text: str, words: list[dict], out: Path) -> None:
    """从 word boundary 事件生成 srt 字幕。
    按时间窗口（~3 秒）聚合 word，避免单 word 字幕太碎"""
    if not words:
        # 没有 word boundary 数据 → 写单条覆盖全文（fallback）
        out.write_text(
            f"1\n00:00:00,000 --> 00:01:00,000\n{full_text}\n",
            encoding="utf-8",
        )
        return

    # 分组：每条字幕 ~12 字 或 ~3 秒
    lines: list[tuple[float, float, str]] = []  # (start_ms, end_ms, text)
    buf_text = ""
    buf_start_ms = words[0]["offset_ms"]
    for w in words:
        buf_text += w["text"]
        end_ms = w["offset_ms"] + w["duration_ms"]
        # 换行条件：>= 12 字 OR 时长 > 3 秒
        if len(buf_text) >= 12 or (end_ms - buf_start_ms) > 3000:
            lines.append((buf_start_ms, end_ms, buf_text))
            buf_text = ""
            buf_start_ms = end_ms
    # 收尾
    if buf_text:
        lines.append((buf_start_ms, words[-1]["offset_ms"] + words[-1]["duration_ms"], buf_text))

    # 写 srt
    def fmt(ms: float) -> str:
        total_ms = int(ms)
        h, rem = divmod(total_ms, 3600_000)
        m, rem = divmod(rem, 60_000)
        s, ms_part = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"

    srt_text = ""
    for i, (start, end, text) in enumerate(lines, start=1):
        srt_text += f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n"
    out.write_text(srt_text, encoding="utf-8")


def main() -> None:
    try:
        import azure.cognitiveservices.speech  # noqa: F401
    except ImportError:
        print("缺 SDK，安装：pip install azure-cognitiveservices-speech")
        sys.exit(1)

    key, region = _load_azure_creds()
    print(f"Azure Speech region={region}, key 长度 {len(key)}")
    print()

    for seg in SEGMENTS:
        print(f"合成段 {seg['id']}: {len(seg['text'])} 字符, 目标 {seg['duration_s']}s")
        try:
            mp3, srt = synthesize_segment(seg, key, region)
            actual_sec = mp3.stat().st_size / (192_000 / 8)  # 192 kbps mono mp3
            print(f"  → {mp3.name}  约 {actual_sec:.1f}s  +  {srt.name}")
        except Exception as e:
            print(f"  [FAIL] {e}")
        time.sleep(0.5)  # 避免 rate limit

    print()
    print("全部完成。下一步 ffmpeg 合成视频")


if __name__ == "__main__":
    main()
