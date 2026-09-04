# 成像基底与光学缺陷库

> **它填哪个槽**：[起手帧合成合同](keyframe-composition-contract.md) 第 3 节的 STYLE LOCK 骨架写着
> `<胶片/渲染语言> ＋ <摄影师或导演对标> ＋ <影片段落对标> ＋ <画幅>`，并声明「只有 STYLE LOCK
> 会漂风格」。此前 tvskill 没有任何词库支撑这四个尖括号，导演拿到的是空模板，
> 于是「电影感」只能靠形容词硬堆。本文件是这个槽位的可选词库。
>
> **实证状态（必须如实标注）**：本文件的参数取值来自外部审美文档
> `cinema-dna-21x9x3`（单次 release 提交，无测试、无 corpus 统计、无回归记录），
> **不属于万物生真值口径，也未经 EP 回归验证**。与既有合同冲突时以既有合同为准；
> 在某一集实测通过前，不得写进 `production-readiness-and-retake-contract.md` 的硬判据。

---

## 0. 适用边界（先读这条，不满足就不要用本文件）

本文件**不是全局默认**。触发条件全部成立才启用：

1. 该 `LOOK-ID` 的**保真取向**是电影感一侧。
   [光影构图与画面风格母版](visual-look-and-style-bible.md) §1 明写「电影感不是唯一目标」——
   手机随手拍、监控、DV 家用带、伪纪录花絮属于**刻意低保真**，此时本文件整份不适用，
   按低保真自己的画质特征（噪点、卷帘、自动曝光跳变、握持不稳）书写。
2. 该镜正在写**起手帧图像提示词**，或写连续组首镜的风格脊柱。
   本文件**不逐段发送**，不进每一条 `镜头N`。
3. 媒介为真人实拍或写实向 3D。风格化 3D（国漫向、日韩向）**不套用胶片乳剂条款**，
   只可取用「一个主光源法则 + 一个主导瑕疵家族」的约束思路，不写 halation 与胶片颗粒。

**画幅不写进提示词**。tvskill 交付竖屏短剧，画幅由 TVMao 节点参数负责；
外部来源里的 `2.39:1 / 21:9` 一律不迁移。STYLE LOCK 的 `<画幅>` 槽由节点参数回填，不由文字承担。

---

## 1. 先选一个成像基底，不叠加

一个 `LOOK-ID` 只允许一个基底。同一逻辑场跨段复用同一条，不逐段换同义词；
更换基底视同 `LOOK-ID` 变体，必须登记进连续性表。

| 基底 | 特征 | 典型用途 |
|---|---|---|
| 35mm 发行拷贝 | 柔和片门、拷贝密度、轻微色彩呼吸、中低微反差、细而不匀的颗粒 | 正片主线、年代戏、文戏 |
| 16mm 电视转播转录 | 分辨率更软、颗粒更粗且自然、轻微串色、曝光不完美、纪录式即时感 | 县城现实、伪纪录、回忆层 |
| 长焦胶片压缩 | 克制的浅景深、人物被压缩贴合、窗玻璃或热浪扰动 | 远观、监视视点、追逐 |
| 早期数字 / 小传感器 | 实景光下动态范围有限、边缘略硬 | 证据层、戏中戏 |
| 监控 / CRT 翻拍 | 几何畸变、屏幕纹理、眩光、暗部压死 | 证据层、被观看感 |

后两项与 §0 的低保真取向重叠，选它们时以 `visual-look-and-style-bible.md` §1 的低保真条款为准，
本文件只提供命名。

---

## 2. 成像基线参数

选定基底后，把下列参数写进 `LOOK-ID`，只把与本镜相关的短脊柱带进起手帧提示词：

- **黑位**：浓密偏深，保留暗部层次，不压成死黑；
- **高光**：柔和滚降，实景灯具处允许局部轻微晕染；
- **锐度**：中低微反差，主体清晰但不数码锐利；
- **颗粒**：细小、不均匀、自然，禁止均匀颗粒贴纸感；
- **曝光**：整体轻微欠曝约 0.5–1 档；
- **色彩**：一个主色母体 + 一个辅助色 + 极少量点缀色，具体色值以**色卡资产图**为准；
- **肤色**：自然、略暗，不做商业美容补光；
- **景深**：建立镜头用中深景深，不用浅景深掩盖构图不足。

色彩这一项**服从色卡优先**：tvskill 已有 13 色色卡参考图与 inline HEX 机制，
本文件不引入独立的「色彩命题」文字层，只约束明度、饱和与光泽方向。

---

## 3. 光学缺陷四家族

目标是 subtle optical imperfection，不是 stylized chromatic effect。
**一组镜头只允许一个主导家族**，不要四项全开。

### 3.1 色差 / 色散

只允许轻微、且只在高反差边缘出现：窗框、建筑边缘、人物轮廓、逆光物体边缘、
灯具与黑暗交界、金属反光边缘、玻璃高反差边缘。

禁止：全图 RGB 错位；明显红蓝双边；赛博/蒸汽波滤镜感；满画面彩边；影响主体识别。

推荐写法（必须带限定语）：

```text
subtle chromatic fringing on bright high-contrast edges
subtle edge chromatic fringing only on window frames, architecture edges, silhouettes
controlled edge fringing, not digital RGB split
```

**禁止裸用** `chromatic aberration` / `RGB split` / `strong aberration`——已并入
[约束编译](../v3/04c-constraint-and-negative-prompt-compiler.md) 第四节禁用表。

### 3.2 Halation｜高光晕染

只在钨丝灯、烛光、窗口高光、火焰、实景灯具、反光高点处轻微出现，
像胶片乳剂轻轻吃开高光边缘：柔和、克制、局部。

禁止：大面积发白；柔光滤镜感；商业磨皮光；无来源泛光；把暗部洗灰。

```text
soft film halation around practical lights and bright highlights
soft highlight roll-off
```

若灯具或窗口开始像柔光美容滤镜，立刻把 halation 与 bloom 减半。

### 3.3 Bloom / 空气雾化

只在光线、镜头与空气三者同时成立时使用：强窗光穿过灰尘、暗场里的火光或钨丝灯、
雾烟沙尘、湿地反射、夜景灯具与玻璃或湿地面交界。

它不是磨皮柔光，必须保留对比、空间与材质。与
[风格母版](visual-look-and-style-bible.md) §4.1 环境力锚配合使用时，
雾/尘/雨必须同时满足环境力锚的三项要求（持续声明、两处可见证据、声画同写）。

### 3.4 宽银幕镜头缺陷

允许：边缘轻微软化；高反差边缘轻微色偏；亮点不完全干净；微弱暗角；真实镜头空气感。

禁止：主体糊掉；低画质截图感；牺牲空间细节；模板化的蓝色横向 anamorphic flare。

---

## 4. 三条参数配方

配方给的是**参数向量**，直接用于填 STYLE LOCK 的 `<胶片/渲染语言>`。
括号内的对标片名**只用于导演在 `<摄影师或导演对标>` / `<影片段落对标>` 槽位内部选型**，
是否写进最终发送的提示词，由该镜的对标需求决定；不作为固定串复制到每一段。

### 配方 A｜自然光历史正剧向（对标可选：诺兰《奥本海默》）

适用：真实历史感、人物 + 自然光、大空间、烟尘、火光、会议室、外景、稳重电影感。

- 色散强度 ≈5%；halation 中偏低；高光柔化中；边缘软化低；颗粒细小；对比中高；微反差中低。

```text
subtle chromatic fringing on bright high-contrast edges
soft film halation around practical lights and bright highlights
dense blacks, natural skin, soft highlight roll-off
slight lens imperfection
```

### 配方 B｜粗野主义建筑冷感向

适用：建筑、室内空间、柱列、混凝土、大厅、权力感、现代主义冷感。

- 色散强度 4–6%；halation 低；边缘软化中低；冷暖边缘偏色有；颗粒细小偏克制；对比中高；锐度中低。

```text
subtle chromatic aberration along architectural edges
restrained lens fringing on backlit concrete and glass
slightly softened edge rendering, realistic filmic optics
cool shadow tones with warm practical highlights
```

### 配方 C｜科幻雾尘巨构向（对标可选：《银翼杀手 2049》）

适用：科幻、雾、沙、尘、城市、夜景、巨构、空旷空间。

- 色散强度 6–10%；halation 中；bloom 中；空气散射高；边缘软化中低；颗粒细小；对比中；饱和中低但综合色偏强。

```text
subtle atmospheric chromatic separation
mild anamorphic lens aberration
slight color fringing in haze, reflections, and high-contrast edges
soft optical bloom, dense cinematic atmosphere
controlled edge fringing, not digital RGB split
```

---

## 5. 与既有合同的边界

- **不覆盖稀疏预算**。`04c` 第三节的约束预算优先：每条 `镜头N` 最小画面基底、主动作结果、
  主运镜触发与终点、原台词与参考 token 都不得为塞光学词而删减。光学脊柱属于起手帧层与
  连续组首镜的风格锁定行，不是逐镜配额。
- **不产生全剧一字不差的固定串**。同一连续组复用同一条短脊柱（`libtv-completed-prompt-format.md`
  开篇风格锁定行的既有口径），但不设跨全剧的死串，也不逐段换同义词。
- **参考图口径不变**。外部来源主张「参考图默认只做抽象分析，不输入生成」「参考图只允许抽取
  一个主维度」——**该主张不适用于 tvskill**，与「@[资产] 作为视觉锚定，严格按此图渲染，
  不可改造」及起手帧钉构图的主链路正面冲突，不得迁移。
- **不引入主观打分制**。外部来源的 100 分制与一票否决表不迁移；验收仍以
  [生成成片质量审计](generated-take-quality-audit.md)、
  [制作就绪与返工合同](production-readiness-and-retake-contract.md) 和 `validate_delivery_md.py` 为准。

## 6. 自检

写完起手帧提示词后逐条核对：

- 是否只选了**一个**成像基底、**一个**主导光学缺陷家族？
- 色散是否带了「只在高反差边缘」的限定语，而不是裸词？
- halation / bloom 是否都能指回一个画面里真实存在的光源？
- 是否出现了本文件与 `04c` 共同禁用的滤镜化高风险词？
- 该 `LOOK-ID` 的保真取向确实是电影感一侧，而不是被误套在低保真段落上？
- 光学词是否挤掉了可见主体、具体场景区域或构图关系？若是，先删光学词。
