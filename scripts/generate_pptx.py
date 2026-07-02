"""
决赛答辩 PPT 生成(python-pptx)。
和 deepseek 文本堆版的区别:每页以真页面截图 / 设计图为主视觉，文字克制，深色统一。
素材：/tmp/ppt-shots/ 下 7 张 demo 真截图 + 5 张设计图；二维码在 docs/submission/。
输出：docs/submission/春招平行宇宙-决赛答辩.pptx
本文件生成后，wly 在 PowerPoint 打开过一遍、微调、导出 PDF 备用。
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

SHOTS="/tmp/ppt-shots"
QR="/root/智联AI比赛/docs/submission/demo-二维码-multiverse.png"
OUT="/root/智联AI比赛/docs/submission/春招平行宇宙-决赛答辩.pptx"

BG=RGBColor(0x0A,0x0E,0x1A); PANEL=RGBColor(0x13,0x18,0x29)
CYAN=RGBColor(0x22,0xD3,0xEE); PURPLE=RGBColor(0xA8,0x55,0xF7)
GOLD=RGBColor(0xFB,0xBF,0x24); INK=RGBColor(0xE5,0xE9,0xF0); INK2=RGBColor(0x8B,0x93,0xA7)
FONT="微软雅黑"
SW,SH=Inches(13.333),Inches(7.5)

prs=Presentation(); prs.slide_width=SW; prs.slide_height=SH
BLANK=prs.slide_layouts[6]

def bg_dark(slide):
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb=BG

def full_img(img):
    s=prs.slides.add_slide(BLANK); bg_dark(s)
    s.shapes.add_picture(img,0,0,width=SW,height=SH)  # 设计图已是完整16:9视觉，铺满
    return s

def tbox(s,x,y,w,h,text,size,color,bold=True,align=PP_ALIGN.LEFT):
    tb=s.shapes.add_textbox(x,y,w,h); tf=tb.text_frame; tf.word_wrap=True
    p=tf.paragraphs[0]; p.alignment=align
    r=p.add_run(); r.text=text; f=r.font
    f.size=Pt(size); f.bold=bold; f.color.rgb=color; f.name=FONT
    return tb

def shot_page(img,title,sub=""):
    s=prs.slides.add_slide(BLANK); bg_dark(s)
    tbox(s,Inches(0.6),Inches(0.35),Inches(12),Inches(0.8),title,26,CYAN)
    # 截图作为主视觉，居中留边（16:9 → 宽 10.6 高 5.96）
    iw=Inches(10.6); ih=Inches(5.96); ix=(SW-iw)//2; iy=Inches(1.25)
    s.shapes.add_picture(img,ix,iy,width=iw,height=ih)
    if sub: tbox(s,Inches(0.6),Inches(7.0),Inches(12),Inches(0.4),sub,13,INK2,bold=False)
    return s

def text_page(title,bullets,accent=CYAN):
    s=prs.slides.add_slide(BLANK); bg_dark(s)
    tbox(s,Inches(0.9),Inches(0.9),Inches(11.5),Inches(1.0),title,32,accent)
    # 卡片
    card=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(0.9),Inches(2.3),Inches(11.5),Inches(4.2))
    card.fill.solid(); card.fill.fore_color.rgb=PANEL; card.line.color.rgb=CYAN; card.line.width=Pt(1)
    card.shadow.inherit=False
    tf=card.text_frame; tf.word_wrap=True; tf.margin_left=Inches(0.5); tf.margin_top=Inches(0.4)
    tf.vertical_anchor=MSO_ANCHOR.TOP
    for i,b in enumerate(bullets):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        p.space_after=Pt(14)
        r=p.add_run(); r.text="·  "+b; f=r.font; f.size=Pt(18); f.color.rgb=INK; f.name=FONT; f.bold=False
    return s

def end_page(title,sub):
    s=prs.slides.add_slide(BLANK); bg_dark(s)
    tbox(s,Inches(1),Inches(2.2),Inches(11.3),Inches(1.2),title,34,INK,align=PP_ALIGN.CENTER)
    tbox(s,Inches(1),Inches(3.5),Inches(11.3),Inches(0.7),sub,20,CYAN,bold=False,align=PP_ALIGN.CENTER)
    # 二维码 + 说明
    qw=Inches(1.8); s.shapes.add_picture(QR,(SW-qw)//2,Inches(4.5),width=qw,height=qw)
    tbox(s,Inches(1),Inches(6.4),Inches(11.3),Inches(0.5),"扫码体验 multiverse.zdwktlj.top  ·  github.com/tljcpa/career-multiverse",13,INK2,bold=False,align=PP_ALIGN.CENTER)
    return s

# ===== 14 页 =====
full_img(f"{SHOTS}/design_cover.png")                                    # 1 封面
full_img(f"{SHOTS}/design_problem.png")                                  # 2 问题
shot_page(f"{SHOTS}/report.png","把整个春招反复推演，用统计结论替代单次赌博","offer 率 98.4% / 平均 5.3 offer / 中位薪资 53 万 / 第 10 周落定 / 去向分散在声剧-γ·鲸火-1·云枢等 8+ 家——基于数十次真实模拟的统计结论，引擎可放大到全量真实市场")  # 3
text_page("从预测未来，到实验未来",[                                       # 4
 "现有 AI 求职工具：当前数据 → 一个预测结果（简历改词 / 面试外挂 / 词袋匹配）",
 "我们：当前状态 → 构建虚拟市场 → 观察演化 → 反事实分析",
 "从推荐系统到模拟系统的跃迁——改变一个条件，看结局怎么变",
])
full_img(f"{SHOTS}/design_threelayer.png")                               # 5 三层视角
shot_page(f"{SHOTS}/profile.png","LLM 五维画像评估，透明不黑盒","每维附评分理由（引用简历证据）+ 学校档 / 学历档双维度加成，综合分可展开")  # 6
shot_page(f"{SHOTS}/sandbox.png","3D 沙盘：约 300 家公司星团 · 你的数字分身","每家公司独立 HR Agent，可现场采访；点击公司节点触发投递")  # 7
text_page("反事实预演：从预测未来，到实验未来（核心卖点）",[  # 8
 "拖动三个滑块：简历质量 / 项目含金量 / 学校档，系统把市场重新推演一遍",
 "输出 offer 数、薪资、去向的变化——例：项目含金量 +15 → 平均 offer 从 5.3 升到 9.4、中位薪资从 53 万升到 62 万",
 "不止告诉你「简历 80 分」，更告诉你「改了会怎样」",
 "把职业规划从玄学，变成基于概率与因果的科学决策（现场 demo 可动态演示）",
])
full_img(f"{SHOTS}/design_arch.png")                                     # 9 架构
full_img(f"{SHOTS}/design_chain.png")                                    # 10 商业价值链
text_page("从 demo 到全量：我们的引擎 × 平台的数据",[                    # 10b 规模化 / 合作
 "现在：约 300 家虚构公司的沙盘——作用是证明引擎跑得通",
 "核心资产不是数据量，是「让人才市场可实验」的引擎与方法论",
 "接入平台级全量真实数据 + 算力 → 覆盖真实市场的人才市场数字孪生",
 "这正是与平台最自然的合作：我们出引擎和方法，平台出数据、算力、场景",
 "「缺数据」不是短板，是合作接口；全量下用分层架构（粗筛 + 精模拟）承接",
])
text_page("现阶段不急于钉死盈利——先验证",[                        # 11
 "价值在于：让人才市场的决策第一次变得「可实验」",
 "变现有多条可能：个人获客 / 高校群体洞察 / 企业品牌 / 平台集成，不预设唯一答案",
 "我们判断高校可能最先跑通（有就业率 KPI + 预算），但这是待验证的假设，不是算好的账",
 "早期该做的是找标杆校验证真实付费意愿、转起数据飞轮，而非纸面财务预测",
],accent=GOLD)
text_page("非科班单人 · 22 天 · AI 当队友",[                              # 12
 "创作者 tljcpa：机械原理跨考考研中，非计算机科班",
 "AI（Claude Code）做工程实现，核心创意 / 产品方向 / 架构决策由本人主导",
 "落地证据：真实录屏演示 + 开源代码（可本地部署）+ 线上可访问 demo",
],accent=PURPLE)
end_page("求职不该是一场只有一次的赌博","让人才市场——先实验，再决策")        # 13

prs.save(OUT)
print("生成完成：",OUT,"共",len(prs.slides._sldIdLst),"页")
