#!/usr/bin/env bash
# ffmpeg 合成最终视频：
# - 录屏 mp4（来自 record_demo.py）
# - 旁白 mp3（来自 tts_gen.py）
# - 字幕 srt（来自 tts_gen.py）
# 合并成 1 个 5 分钟视频，符合赛事要求：MP4 / ≤800MB / 含字幕和语音
#
# 用法：bash scripts/build_video.sh
# 产物：dist/tljcpa+求职+春招平行宇宙+演示视频.mp4

set -e

ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
CLIPS_DIR="${VIDEO_CLIPS_DIR:-$ROOT/backend/data/video/clips}"
TTS_DIR="$ROOT/backend/data/video"
OUT_DIR="$ROOT/dist"
OUT_FILE="$OUT_DIR/tljcpa+求职+春招平行宇宙+演示视频.mp4"

mkdir -p "$OUT_DIR"

command -v ffmpeg >/dev/null 2>&1 || { echo "缺 ffmpeg"; exit 1; }

# 1. 把 webm 录屏转 mp4
echo "[1/4] 转码 webm → mp4..."
for webm in "$CLIPS_DIR"/*.webm; do
  [ -f "$webm" ] || continue
  name=$(basename "$webm" .webm)
  mp4="$CLIPS_DIR/$name.mp4"
  if [ ! -f "$mp4" ] || [ "$webm" -nt "$mp4" ]; then
    ffmpeg -y -i "$webm" -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p \
      -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
      -an "$mp4" 2>&1 | tail -1
  fi
done

# 2. 拼接 8 段 mp3 成完整音轨
echo "[2/4] 拼接旁白 mp3..."
NARRATION="$TTS_DIR/narration.mp3"
> "$TTS_DIR/_concat.txt"
for i in 01 02 03 04 05 06 07 08; do
  if [ -f "$TTS_DIR/$i.mp3" ]; then
    echo "file '$TTS_DIR/$i.mp3'" >> "$TTS_DIR/_concat.txt"
  fi
done
ffmpeg -y -f concat -safe 0 -i "$TTS_DIR/_concat.txt" -c copy "$NARRATION" 2>&1 | tail -1

# 3. 合成完整 srt
echo "[3/4] 合成完整 srt..."
TTS_DIR="$TTS_DIR" python3 - <<'PYEOF'
import os, re
from pathlib import Path

tts_dir = Path(os.environ["TTS_DIR"])
out_srt = tts_dir / "narration.srt"

def parse_ts(s):
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    return int(h)*3600_000 + int(m)*60_000 + int(sec)*1000 + int(ms)

def fmt_ts(ms):
    h, rem = divmod(int(ms), 3600_000)
    m, rem = divmod(rem, 60_000)
    s, msp = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{msp:03d}"

cum_offset_ms = 0
idx = 1
out_lines = []
for seg_id in ["01","02","03","04","05","06","07","08"]:
    srt = tts_dir / f"{seg_id}.srt"
    mp3 = tts_dir / f"{seg_id}.mp3"
    if not srt.exists():
        continue
    text = srt.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", text.strip())
    seg_max_ms = 0
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
        if not m:
            continue
        st_ms = parse_ts(m.group(1)) + cum_offset_ms
        ed_ms = parse_ts(m.group(2)) + cum_offset_ms
        seg_max_ms = max(seg_max_ms, ed_ms - cum_offset_ms)
        body = "\n".join(lines[2:])
        out_lines.append(f"{idx}\n{fmt_ts(st_ms)} --> {fmt_ts(ed_ms)}\n{body}\n")
        idx += 1
    if mp3.exists():
        actual_ms = mp3.stat().st_size / (192_000/8) * 1000
        cum_offset_ms += int(actual_ms) + 300
    else:
        cum_offset_ms += seg_max_ms + 300

out_srt.write_text("\n".join(out_lines), encoding="utf-8")
print(f"  完整 srt: {out_srt}  ({idx-1} 条字幕)")
PYEOF

# 4. 最终合成
echo "[4/4] 合成最终 mp4..."
> "$TTS_DIR/_video_concat.txt"
for mp4 in "$CLIPS_DIR"/*.mp4; do
  echo "file '$mp4'" >> "$TTS_DIR/_video_concat.txt"
done

ffmpeg -y \
  -f concat -safe 0 -i "$TTS_DIR/_video_concat.txt" \
  -i "$NARRATION" \
  -filter_complex "[0:v]subtitles='$TTS_DIR/narration.srt':force_style='Fontname=Source Han Sans SC,Fontsize=20,PrimaryColour=&Hffffff,BackColour=&H80000000,BorderStyle=4,MarginV=40'[v]" \
  -map "[v]" -map 1:a \
  -c:v libx264 -preset slow -crf 20 \
  -c:a aac -b:a 192k \
  -shortest \
  "$OUT_FILE" 2>&1 | tail -5

echo
echo "=== 完成 ==="
ls -lh "$OUT_FILE"
