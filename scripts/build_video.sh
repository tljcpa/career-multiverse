#!/usr/bin/env bash
# build_video v2：
# - 不用 -shortest（保留全部录屏画面）
# - 按 5 段录屏顺序拼接
# - 字体改 Noto Sans CJK SC（VM 已装）
# - 段间淡入淡出 0.5s

set -e

ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
CLIPS_DIR="${VIDEO_CLIPS_DIR:-$ROOT/backend/data/video/clips}"
TTS_DIR="$ROOT/backend/data/video"
OUT_DIR="$ROOT/dist"
OUT_FILE="$OUT_DIR/tljcpa+求职+春招平行宇宙+演示视频.mp4"

mkdir -p "$OUT_DIR"
command -v ffmpeg >/dev/null 2>&1 || { echo "缺 ffmpeg"; exit 1; }

# 1. 把 webm 录屏转 mp4（按对应旁白 mp3 时长精确截断 → 音画严丝合缝）
echo "[1/4] 转码 webm → mp4（按旁白时长精确截断）..."
SEGMENTS=(03-upload 04-sandbox 05-report 06-counterfactual 07-dashboard)
# 每段视频对应哪几段旁白 mp3（决定该段精确时长）
declare -A SEG_MP3=( [03-upload]="01 02 03" [04-sandbox]="04" [05-report]="05" [06-counterfactual]="06" [07-dashboard]="07 08" )
for seg in "${SEGMENTS[@]}"; do
  webm="$CLIPS_DIR/$seg/$seg.webm"
  mp4="$CLIPS_DIR/$seg.mp4"
  if [ ! -f "$webm" ]; then
    echo "  缺 $seg.webm，跳过"
    continue
  fi
  # 该段对应旁白 mp3 组的真实总时长（ffprobe），视频按此精确截断
  dur=0
  for i in ${SEG_MP3[$seg]}; do
    d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TTS_DIR/$i.mp3")
    dur=$(python3 -c "print($dur + $d)")
  done
  # 每次重转（-t 截断长度随旁白变化，不用缓存）
  ffmpeg -y -i "$webm" -t "$dur" -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
    -an "$mp4" 2>&1 | tail -1
  echo "  $seg → 截断到 ${dur}s"
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

# 3. 合成完整 srt（与 v1 相同）
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
        # 用 ffprobe 真实时长（和 step1 视频截断、step2 音频拼接同一基准），
        # 去掉旧的 +300ms gap——音频拼接是无缝的，字幕加 gap 会逐段累积漂移
        import subprocess
        d = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(mp3)]
        ).decode().strip()
        cum_offset_ms += int(float(d) * 1000)
    else:
        cum_offset_ms += seg_max_ms

out_srt.write_text("\n".join(out_lines), encoding="utf-8")
print(f"  完整 srt: {idx-1} 条字幕")
PYEOF

# 4. 拼接视频 + 烧字幕 + 加 fade（移除 -shortest 保留全部画面）
echo "[4/4] 合成最终 mp4..."
> "$TTS_DIR/_video_concat.txt"
for seg in "${SEGMENTS[@]}"; do
  if [ -f "$CLIPS_DIR/$seg.mp4" ]; then
    echo "file '$CLIPS_DIR/$seg.mp4'" >> "$TTS_DIR/_video_concat.txt"
  fi
done

# 字幕用 Noto Sans CJK SC（VM 已 apt install fonts-noto-cjk）
ffmpeg -y \
  -f concat -safe 0 -i "$TTS_DIR/_video_concat.txt" \
  -i "$NARRATION" \
  -filter_complex "[0:v]subtitles='$TTS_DIR/narration.srt':force_style='Fontname=Noto Sans CJK SC,Fontsize=22,PrimaryColour=&Hffffff,OutlineColour=&H000000,BorderStyle=4,BackColour=&H80000000,MarginV=50,Bold=1'[v]" \
  -map "[v]" -map 1:a \
  -c:v libx264 -preset slow -crf 20 \
  -c:a aac -b:a 192k \
  "$OUT_FILE" 2>&1 | tail -3

echo
echo "=== 完成 ==="
ls -lh "$OUT_FILE"
