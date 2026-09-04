"""分镜语法：受控词表与写作纪律判据。

对标 doubao-creative-drama 的 `references/storyboard.md`（用户 2026-09-04 指定为主要基准）。

tvskill 此前的镜头是散文式的——景别、视角、机位、朝向糊在一句话里，
最严重的是**完全没有「视角类型」这个维度**：整条产线从没区分过
镜头是「从外面看」（第三人称客观）还是「从角色眼睛里看」（POV 第一人称）。

对标方的镜头是结构化四要素头 + 转场标注：

    0-3 秒：[特写｜林远 POV 第一人称视角｜手持感运镜｜俯拍]
      从林远眼睛高度俯看书架下层，前景是他的左手…… [视线跟随切]

本模块提供词表与判据，由 validate_delivery_md 落成闸。
"""

from __future__ import annotations

import re


# ── 受控词表 ────────────────────────────────────────────────

# 景别（8 词）：决定观众与主体的距离
SHOT_SIZES = (
    "大特写", "特写", "近景", "中景", "全景", "远景", "大远景", "过肩镜头", "过肩",
)

# 视角类型：tvskill 此前完全缺失的维度
VIEWPOINT_OBJECTIVE = "第三人称客观视角"
VIEWPOINT_POV_RE = re.compile(r"POV\s*第一人称视角")
VIEWPOINT_SWITCH = "POV 与第三视角切换"

# 机位状态（13 词）：基础运动 / 情绪表达 / 动作冲击
CAMERA_MOVES = (
    # 基础运动
    "推镜", "拉镜", "摇镜", "移镜", "升降镜", "固定",
    # 情绪表达
    "环绕运镜", "手持感运镜", "希区柯克变焦", "呼吸感镜头",
    # 动作与冲击力
    "甩镜转场", "格挡震动", "子弹时间", "冲刺跟拍",
    # 常用补充
    "跟拍", "斯坦尼康跟拍",
)

# 拍摄角度与主体朝向（7 词）
CAMERA_ANGLES = (
    "正面", "侧面", "左侧面", "右侧面", "半侧面", "3/4 侧", "3/4侧",
    "背面", "仰拍", "俯拍", "平视",
)

# 转场：每个镜头末尾必须声明
TRANSITIONS = ("硬切", "叠化", "视线跟随切", "甩镜转场", "淡入", "淡出", "闪白", "闪黑")
TRANSITION_RE = re.compile(r"\[(" + "|".join(TRANSITIONS) + r")\]")

# ── 四要素头 ────────────────────────────────────────────────

SHOT_HEAD_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*[-–~]\s*\d+(?:\.\d+)?\s*秒\s*[：:]\s*\[([^\]]+)\]"
)
HEAD_SEP = "｜"

# ── 写作纪律 ────────────────────────────────────────────────

# 抽象情绪词：对标方明确「不建议使用"很悲伤""非常愤怒"等抽象词汇」，
# 要求改写为具体身体细节（低头、肩膀颤抖、指节攥紧衣角……）。
ABSTRACT_EMOTION_RE = re.compile(
    r"(?:很|非常|十分|极其|特别|无比)\s*"
    r"(?:悲伤|难过|愤怒|生气|紧张|焦虑|开心|高兴|害怕|恐惧|震惊|失望|绝望)"
)

# 群体量词：对标方要求写全每个角色名，不得用数字或量词概括。
CROWD_QUANTIFIER_RE = re.compile(
    r"(?:[一二三四五六七八九十两几]+\s*(?:个|名|位)\s*人|众人|大家|所有人|"
    r"[^\s，。；]{1,6}们)\s*[^\s，。；]{0,6}"
    r"(?:面面相觑|大惊失色|冲了上来|围了上来|议论纷纷|一齐|同时)"
)

# 代词指代：同一角色全程同名，不得中途改用代词。
# 只查镜头正文里的独立代词，不查台词内容（台词里说「他」是正常的）。
# 注意不能用 \w 做边界：Python 的 \w 匹配中文，「那个男人走过来」里后面的
# 「走」会让否定前瞻失效，整条判据形同虚设。直接匹配短语即可。
PRONOUN_REF_RE = re.compile(r"那个男人|那个女人|那名男子|那名女子|那名男人|那名女人")

# POV 相关
POV_SELFIE_BAN_RE = re.compile(r"自拍|监控视角|无人机视角|航拍视角")
POV_EYE_LEVEL_RE = re.compile(r"眼睛高度|视线高度|眼高")
POV_FACE_BAN_RE = re.compile(r"完整正脸|正脸完整|完整的正脸")

# 中文戏剧化念白语速：每秒约 4 字（与 _shot_budget 保持一致）
SPOKEN_CHARS_PER_SECOND = 4.0


def parse_shot_head(line: str) -> list[str] | None:
    """取出四要素头。返回 [景别, 视角类型, 机位状态, 角度与朝向]，不合规返回 None。"""
    match = SHOT_HEAD_RE.match(line)
    if not match:
        return None
    parts = [p.strip() for p in match.group(1).split(HEAD_SEP)]
    return parts if len(parts) == 4 else None


def in_vocabulary(value: str, table: tuple[str, ...]) -> bool:
    return any(word in value for word in table)


def is_pov(viewpoint: str) -> bool:
    return bool(VIEWPOINT_POV_RE.search(viewpoint))


# ── 模糊质量词（对标 doubao-creative-drama assets.md）──────────
# 官方原文：「禁止使用模糊质量词单独作为约束，例如"高级、漂亮、震撼、氛围感强"，
# 必须替换为具体的构图、光影、色彩、材质和空间描述。」
# 与 zy-cinematic-realism 的 Restraint Test 同向：风格词不能冒充实质。
# 不要给中文词加「前后不能是中文」的边界——中文文本里词的前后本来就是中文，
# 「画面氛围感强」前面是「面」就会被否定掉，整条判据形同虚设。
# 这个错误在本文件的 PRONOUN_REF_RE 上已经犯过一次（用 \w 做边界），
# 两次都是回归测试抓出来的。中文判据直接匹配短语即可。
VAGUE_QUALITY_RE = re.compile(
    r"高级感|非常高级|很高级|漂亮|震撼|氛围感强|大片感|高大上|"
    r"精美绝伦|美轮美奂|画面感强|视觉冲击力强|质感十足"
)

# 场景美学受控词（官方推荐组合，供参考而非强制）
SCENE_AESTHETIC_WORDS = (
    "电影级场景设计", "影视级布光", "黄金构图", "三分法构图", "强空间纵深",
    "前中后景层次清晰", "体积光", "柔和环境光", "真实全局光照", "自然阴影",
    "材质细节丰富", "细腻纹理", "真实反射", "空气透视", "低饱和高级色调",
    "统一色温", "叙事性陈设", "环境细节丰富",
)
