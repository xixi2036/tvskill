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
OS_VO_RE = re.compile(r"(?<![a-z])(?:OS|VO|os|vo)(?![A-Za-z])|内心|画外音|旁白")

# 精确台词真值锁：{} 内是逐字台词，{{Mixed N}} 不算。
DIALOGUE_RE = re.compile(r"(?<!\{)\{([^{}\n]+)\}(?!\})")

# 模型多镜标签。
EXACT_SHOT_RE = re.compile(r"^Shot\s+(\d+):", re.M)
EXACT_SHOT_BLOCK_RE = re.compile(r"^Shot\s+\d+:.*?(?=^Shot\s+\d+:|\Z)", re.M | re.S)

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
