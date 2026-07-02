"""
决赛现场精华版视频旁白(1-2 分钟,配合作品展示 10 分钟穿插用)。
edge-tts 生成,和主视频同款云希男声。舍弃 deepseek 5:08 全版现场播的做法。
产物：backend/data/video/highlight/h1..h5.mp3 + srt
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
import edge_tts
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_gen import _write_srt, PROJECT_ROOT  # noqa: E402

VOICE="zh-CN-YunxiNeural"; RATE="+6%"
SEGMENTS=[
 {"id":"h1","text":"天气可以预报，城市有数字孪生，但人才市场至今只能凭经验决策。我们做了第一个可实验的人才市场——春招平行宇宙。"},
 {"id":"h2","text":"上传简历，AI 一次性生成五维画像和你的数字分身，进入 49 家公司组成的模拟市场，并行跑 1000 次完整春招。给你的不是建议，是统计结论。"},
 {"id":"h3","text":"我们更进一步，做了反事实预演：拖动滑块，把项目含金量再做扎实一点，看 offer 率和薪资怎么变。从预测未来，到实验未来。"},
 {"id":"h4","text":"不只求职者。企业能把招聘策略丢进市场做对照实验，高校能看本校群体的竞争力和技能缺口。个人、企业、学校，同一个可实验的人才市场。"},
 {"id":"h5","text":"春招平行宇宙，先实验，再决策。"},
]

async def gen(seg):
    out=PROJECT_ROOT/"backend"/"data"/"video"/"highlight"; out.mkdir(parents=True,exist_ok=True)
    mp3=out/f"{seg['id']}.mp3"; srt=out/f"{seg['id']}.srt"
    c=edge_tts.Communicate(seg["text"],VOICE,rate=RATE); words=[]
    with open(mp3,"wb") as f:
        async for ch in c.stream():
            if ch["type"]=="audio": f.write(ch["data"])
            elif ch["type"]=="WordBoundary":
                words.append({"text":ch["text"],"offset_ms":ch["offset"]/10000,"duration_ms":ch["duration"]/10000})
    _write_srt(seg["text"],words,srt); return mp3

async def main():
    for s in SEGMENTS:
        try: m=await gen(s); print(f"{s['id']} ok")
        except Exception as e: print(f"{s['id']} FAIL {e}")
    print("精华旁白生成完成")

if __name__=="__main__":
    asyncio.run(main())
