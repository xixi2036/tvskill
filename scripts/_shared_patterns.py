"""跨脚本共享的判据。

存在理由：同一条判据在多个脚本里各写一份，必然分叉。已经实证两次——
`audio_control_subjects` 与一处内联正则不同步；`OS_VO_RE` 在 validate 里修好了
词边界问题，audit_canvas_nodes 里却还是坏的旧版，导致画布审计继续漏判"系统VO"。

因此凡是**语义上必须一致**的判据一律放这里，各脚本 import，不允许再各写一份。
各脚本确实需要不同行为的（例如 SEGMENT_RE 的捕获组数、二审字段的取值域）不放进来。

`tests/test_shared_patterns.py` 会扫描所有脚本，禁止同名判据重新分叉。
"""

from __future__ import annotations

import re


# 画外音/内心独白/旁白。注意不能用 \b：中文与字母相邻不构成词边界，
# "系统VO" 里的 VO 会漏判，而这正是真实语料里最常见的写法。
# 前向只排除小写字母（避免 provo 这类词内命中），**不排除大写字母与中文**：
# 真实与模板语料里说话人写作「系统VO」「角色AVO」「主体AVO」，
# 前向若排除大写字母，角色名带拉丁后缀时会整片漏判。
# 不加 re.I：re.IGNORECASE 会让 (?<![a-z]) 连大写字母一并排除，
# 反而把「角色AVO」挡在外面。故显式列大小写。
# 2026-09-04 补：系统音／画外音同属「声源不在画面内、无可见口型」这一类，
# 判据语义本就是「非同步人声」，系统流短剧里的系统音必须归此列，
# 否则会被当成同步对白要求口型与 {} 符号。
OS_VO_RE = re.compile(
    r"(?<![a-z])(?:OS|VO|os|vo)(?![A-Za-z])|内心|画外音|画外|旁白|系统音"
)

# 精确台词真值锁：{} 内是逐字台词，{{Mixed N}} 不算。
DIALOGUE_RE = re.compile(r"(?<!\{)\{([^{}\n]+)\}(?!\})")

# 旁白／内心独白真值锁：『』。
# 豆包官方 doubao-creative-drama 的符号表有五个符号，tvskill 此前只记了四个，
# 漏的正是旁白 —— 结果《万妖图录传》EP01 的 24 句里有 18 句内心独白被写成 {}，
# 与真正的同步对白同符号，模型无从区分谁该有口型、谁该出字幕。
NARRATION_RE = re.compile(r"『([^』\n]+)』")

# 模型多镜标签。
EXACT_SHOT_RE = re.compile(r"^Shot\s+(\d+):", re.M)

# 时间戳动作规划块：`0-3 秒：` / `3-6秒:`。
# 这是万物生真实语料与豆包官方 skill 一致的写法——段内不用镜头标签，
# 而是把段时长切成连续时间段，每段写运镜、动作、剧情、声音。
# 299 条万物生视频提示词里 `Shot N:` 出现率 0%；豆包官方示例通篇 `0-3 秒`。
TIMESTAMP_BLOCK_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)\s*秒\s*[：:]", re.M
)
TIMESTAMP_BLOCK_SPLIT_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*[-–~]\s*\d+(?:\.\d+)?\s*秒\s*[：:].*?"
    r"(?=^\d+(?:\.\d+)?\s*[-–~]|^【|\Z)",
    re.M | re.S,
)


def timestamp_spans(prompt: str) -> list[tuple[float, float]]:
    """取出时间戳动作规划的各时间段。"""
    return [
        (float(a), float(b)) for a, b in TIMESTAMP_BLOCK_RE.findall(prompt)
    ]
# 末镜必须止于第一个【…】小节，否则它会吞掉【声音设计】【关键约束】和收尾行。
# 2026-09-04 实证：V06 末镜自身干净，却因【声音设计】里的「内心独白」被判
# 「同一 Shot 内混合口型对白与 OS/VO」——误报。反向更危险：末镜缺「固定机位」时，
# 会被【关键约束】里的同名字样冒名满足，漏报。故显式在 ^【 处收边。
EXACT_SHOT_BLOCK_RE = re.compile(
    r"^Shot\s+\d+:.*?(?=^Shot\s+\d+:|^【|\Z)", re.M | re.S
)

# 规划用资产：只服务导演推理，永远不进 Mixed。
PLANNING_RE = re.compile(
    r"位置图|轨迹图|构图图|动线图|平面图|俯视图|机位图|箭头|虚线|假人|色块|网格|文字标注"
)

# 音色占位槽：人工上传前的占位形态。
VOICE_SLOT_RE = re.compile(r"待上传|占位")

# 功能场景（教室）朝向判据。
CLASSROOM_RE = re.compile(r"教室|课堂|黑板|讲台")
FRONT_BOARD_RE = re.compile(
    r"(?:黑板.{0,16}(?:前墙|教室前方)|(?:前墙|教室前方).{0,16}黑板)"
)
SEAT_BOARD_RE = re.compile(
    r"(?:课桌|座椅|骨盆|髋部|膝盖|双脚|学生.{0,8}(?:身体|下半身))"
    r".{0,36}(?:面向|朝向|朝着).{0,12}(?:黑板|讲台|前墙)"
)
LOWER_BODY_LOCK_RE = re.compile(
    r"(?:(?:骨盆|髋部|膝盖|双脚|坐姿).{0,32}(?:保持|固定|仍|始终).{0,16}"
    r"(?:黑板|前方|不变)|(?:只让|仅让|只移动|仅移动|只转动|仅转动)"
    r".{0,4}(?:眼睛|视线|头部|侧头))"
)

# 空场景：与"可见人群"冲突的空间状态。
EMPTY_SCENE_RE = re.compile(r"空教室|空场景|空房间|无人物(?:教室|场景|空间)")


# ── 平台真实支持的生成参数取值域 ──────────────────────────────────
# 取自 `tvmao model get <modelId>` 的 inputSchema.enum（2026-09-04 实查
# doubao-seedance-2-0-fast-260128 与 doubao-seedance-2-5-260628）。
#
# 这不是项目偏好。此前 validate_delivery_md 与 audit_asset_consistency 各自
# 写死「必须 9:16 / 必须 480P」——那是某个竖屏项目的约定被当成了平台约束：
# 参考剧《万妖图录传》七季全部 1280×720（16:9），在这条上直接硬失败，
# 产线连下游都走不到。闸的职责应是「值是平台支持的 + 全剧只用一档」，
# 具体用哪一档由交付文件声明。
#
# 放共享模块而非各脚本内联，理由见本文件抬头：同一判据分两处写必然分叉。
SUPPORTED_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4"}
SUPPORTED_RESOLUTIONS = {"480p", "720p", "1080p"}
SUPPORTED_MODELS = {
    "Seedance 2.0 VIP",
    "Seedance 2.0 Fast VIP",
    "Seedance 2.5",
}
