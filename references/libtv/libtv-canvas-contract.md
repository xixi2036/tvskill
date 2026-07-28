# LibTV 画布接口合同

> 默认只交付 Markdown。只有用户明确要求操作画布时，才执行本合同；创建/更新节点与运行生成必须分开授权。

## 1. 唯一同步来源

画布同步只读取 TVSkill 最终交付的 `<集号>-LibTV视频节点提示词.md`，不生成、不读取旧
`payload`、`asset-plan`、`movement-ledger` 或 `reference-manifest` JSON。

每个 `## 生成段 VNN` 对应一个未运行的 LibTV `video` 节点：

- `LibTV 完成提示词（整块复制）`代码块写入节点 `prompt`；
- `Mixed 上传顺序`表决定素材连接和实时 `mixedListOrder`；
- 集级模型、画幅、分辨率与段级时长、声音开关写入节点 settings；
- 运行状态为“阻塞”的段禁止同步为可生成节点；
- 位置图、轨迹图、构图图、平面图、箭头图与文字标注图禁止进入 Mixed。

禁止创建 `script` 节点作为中间事实表，禁止调用 `libtv script storyboard`。

## 2. 环境与实时 schema

目标电脑必须安装并登录 LibTV CLI。实际操作前读取本机命令帮助和目标模型 schema；
本文件不把特定 CLI 版本号或已缓存字段当作永久事实。

```bash
libtv --help
libtv node --help
libtv node list -p <PROJECT_UUID>
```

节点默认参数为 `Seedance 2.0 Fast VIP`、`9:16`、`480P`、声音开启。若实时 schema 中模型名、
分辨率写法、时长范围或声音字段不同，以实时 schema 为准，同时保留 Markdown 中的语义
合同。除非用户明确覆盖，不得擅自改模型或关闭声音。

## 3. 素材上传

人物图、角色音色、干净首帧/已验收续接帧、当前人数场景状态图和关键道具状态图必须先由
Codex 或人工审核，再作为独立资源上传。每个可识别人物和每名说话人的音色各用独立资源。

```bash
libtv upload <RESOURCE_NODE_NAME> \
  --project <PROJECT_UUID> \
  --resource /absolute/path/to/media
```

上传后以画布回读的节点 ID、名称和媒体类型为准。素材名应与 Markdown 的“素材”列唯一匹配；
同名节点、缺失节点、错误媒体类型或未验收素材都必须先处理，不能让同步脚本猜测。

规划图只帮助确定空间和机位，不上传、不连接。未验收尾帧不能作为续接帧。

## 4. 两阶段写入

第一阶段只创建或更新未运行视频节点：

```bash
python3 scripts/sync_delivery_markdown.py <本集.md> \
  --project <PROJECT_UUID> \
  --node-prefix <节点名前缀> \
  --node-suffix=-v3提示词
```

命令默认 dry-run。用户已明确要求写画布时才追加 `--apply`。可用 `--only 1,2,3`
限制生成段。同步脚本不得传入或拼接 `--run`，不得覆盖已有生成结果的节点。

写入时按 Markdown 表格顺序连接素材，并重写 `prompt`、媒体列表和 Order 字段。LibTV 在
删除或重建媒体边时可能清空 `{{Mixed N}}` 或保留旧缓存，因此命令返回成功不等于节点合格。

第二阶段必须重新读取画布事实：

```bash
python3 scripts/audit_canvas_nodes.py \
  --project <PROJECT_UUID> \
  --name-prefix <节点名前缀>
```

也可重复使用 `--node <NODE_ID>` 精确限定。审计以实时 `prompt`、`mixedList`、
`mixedListOrder`、`audioList`、模型、settings 和任务状态为唯一真值，不采信 Markdown
表格中的自报顺序。

## 5. Mixed 与声音硬门禁

`Mixed N` 必须对应实时 `mixedListOrder` 第 N 位，且同时满足：

- 编号从 1 连续，无越界、漏用或重复职责；
- `@[语义资产]` 与实际节点名称、媒体类型和唯一用途一致；
- 不同人物、不同音色、场景、首帧和道具不得共用一个 Mixed；
- 含台词、OS、VO 或旁白时，声音开启，所有实际说话人均绑定自己的已审核音色；
- 正式对白段缺任一说话人音色、干净首帧或已验收续接帧时必须阻塞；
- 规划资产、空教室图与可见群像要求冲突、错误人数场景图均为硬错误。

特别注意：提示词写 `@[角色] {{Mixed 1}}` 只表达作者意图，不证明 Mixed 1 的实际内容。
只有回读语义、媒体类型和顺序全部一致才算绑定成功。

## 6. 运行前凭证

只有画布审计 `errors=0` 才能报告“画布提示词已就绪”。用户明确授权运行具体节点前，
对目标节点执行：

```bash
python3 scripts/audit_canvas_nodes.py \
  --project <PROJECT_UUID> \
  --node <NODE_ID> \
  --pre-run \
  --receipt <NODE_ID>-pre-run-audit.md
```

凭证绑定当前节点指纹。`prompt`、Mixed、媒体 Order、模型、settings 或任务状态任一变化后，
凭证立即失效，必须重新审计。不得用旧凭证运行新输入。

同一连续组按顺序运行：前段生成、下载并验收通过后，后段才可连接该段的稳定续接帧。
已有结果若未通过质量审计，结果和尾帧都视为拒绝态。

## 7. 失败边界

- 未安装、未登录或未绑定项目：停止写入，保留本地 Markdown。
- 素材名称匹配为零个或多个节点：停止并要求唯一化，不模糊猜测。
- 素材缺失、媒体类型错误或职责冲突：保持阻塞，不降级为无参考生成。
- 写入或回读失败：保留 stderr，不把网络或认证错误误判为节点不存在。
- `Mixed N` 与实时媒体顺序不一致：修复、重写 prompt、再次回读。
- 画布审计有硬错误：不得运行，不得把已有结果登记为验收续接帧。
- CLI 或模型 schema 漂移：先按实际帮助与 schema 更新适配，再执行写入。

## 8. 已验证的踩坑清单

以下每条都由实机验证得出（建节点 → 画布回读 → 前端渲染核对），不是推测。

### 8.1 绑定语法：只有 `{{Mixed N}}` 真生效

实测四种写法建同样的节点、连同一张图，看前端是否渲染成引用 chip：

| 写法 | 结果 |
|---|---|
| `@[语义名] {{Mixed N}}` | ✅ **唯一有效**。平台把 `{{Mixed N}}` 改写成 `{{Image N}}` 或 `{{Portrait N}}`（★2026-07-27 修正：不是统一改写成 `{{Image N}}`；同一 prompt 内不同素材会按素材形态分别改写为两者之一，具体判据未查清，只确认两种都是平台合法产物），渲染为带缩略图的 chip，chip 上带 `data-mention-node-id` = 该素材真实节点 ID |
| `@[素材节点 UUID]` | ❌ 纯文本，不解析 |
| `@[CDN 文件名 hash]` | ❌ 纯文本，不解析 |
| `@[语义名]` 单独用 | ❌ 纯文本，不解析 |

**要点**：
- 真正起作用的是 **`{{Mixed N}}`**；`@[语义名]` 只是给人读与给审计脚本比对用，模型侧不依赖它。
- **不得用 Asset ID / 文件名 hash 充当引用**——模型无法把 Asset ID 关联到参考内容，官方指南亦明确禁止。
- LibTV 是 Seedance 官方 API 的前端封装：`{{Mixed N}}` 最终编译成官方指代格式 `图片N`。看官方 API 文档时要分清「模型层语法」与「LibTV 前端语法」，不要拿一层的证据否定另一层。

### 8.2 顺序只能回读，不能自报

`Mixed N` 的 N **必须**来自回读画布实时 `mixedListOrder`。用本地素材列表顺序、上传顺序或 `--left-add` 的传参顺序去推断，**会整体错位**（实测把三个语义全绑到错误素材上）。

### 8.3 素材改名的连带影响

- 资源节点改名：`libtv node <名> --name <新名>` 会因校验失败报 `params.model 不能为空`，需补 `-s model=Lib Image` 才能通过。
- 改名后**视频节点里的 `mixedList` / `imageList` 仍缓存旧 label**，审计读的是 `mixedList` 的 label，不是节点当前名。需用 `-s mixedList=<json>` 覆写 label 同步。
- **同一语义名不得被多个素材共用**，否则语义指代失效且违反职责唯一。

### 8.4 重连媒体边会清空 `{{Mixed N}}`

`--left-rm` + `--left-add` 重建连接后，prompt 里的 `{{Mixed N}}` 会被清掉、`label` 变 `None`。**重连之后必须重写 prompt 并再次回读验证**。

### 8.5 修一个节点的正确顺序

1. 回读 `mixedListOrder` 拿真实顺序；
2. 资源节点改名为语义名（补 `-s model=`）；
3. 用 `-s mixedList=` 同步 label；
4. 按真实顺序写 `@[语义名] {{Mixed N}}`，确保每个 Mixed 都被引用；
5. 跑 `audit_canvas_nodes.py` 回读验证，零硬错误才算完成。

> **自证陷阱**：用本 skill 自己的审计脚本验证本 skill 自己的规范，只能证明「符合书面约定」，不能证明「平台真的按这个绑定」。涉及平台行为的结论，必须以**前端渲染实测**或**平台回写结果**为准。

### 8.6 §8.2 的踩坑会真实复发,以及审计脚本只能用在生成前

2026-07-27 在同一个 skill 内、明知 §8.2 规则的情况下，批量建 4 个视频节点时**仍然按 `--left-add` 的连接顺序假设写 `Mixed N`，没有逐节点回读 `mixedListOrder` 再定稿**——4 个节点里 2 个（V1、V4）顺序整体错位或部分错位。视觉结果仍然凑合，是因为角色资产辨识度够高、模型自己"认出该放哪张图"掩盖了顺序错误，**不代表顺序写对了**。

**教训**：知道规则不等于会应用规则；批量操作时更容易图快跳过"回读→再写"这一步。写完 N 个节点的最终 prompt 前，必须逐个跑一次 `libtv node <名>` 读 `mixedListOrder` 再落笔，不能凭建节点顺序推断，哪怕只是"批量重复同一套动作"也不能省。

**另外，`audit_canvas_nodes.py` 的绑定检测只在生成前有效**：节点一旦真实生成过，平台就已经把 prompt 里的 `{{Mixed N}}` 改写成 `{{Image N}}`/`{{Portrait N}}`，而审计脚本的正则只认字面 `Mixed`，改写后再跑审计会对每个已生成节点系统性报"画布 Mixed 未被提示词绑定"。这不是脚本的 bug，是用法超出了它的设计场景（`--pre-run` 门禁，不是生成后回溯审计）——生成后要复核绑定是否正确，只能靠直接读 `mixedListOrder` 和 prompt 里改写后的 token 手动核对，或者在**下次编辑同一节点、prompt 还原成 `{{Mixed N}}` 之前**跑审计。

官方入口仅用于人工核对和安装，不是 skill 运行时依赖：https://www.liblib.tv/cli
