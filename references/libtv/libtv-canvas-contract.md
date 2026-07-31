# TVMao 画布接口合同

> 文件名暂保留 `libtv-canvas-contract.md`，只为兼容既有 SKILL 链接；运行时后端已经迁移为 TVMao CLI。默认只交付 Markdown。创建/更新节点与运行生成必须分开授权。

## 1. 已验证环境

2026-07-31 本机帮助、实时 schema 与 `huabu_studio` 源码提交
`95fde2d509ad7f2da5a66221b134ca1fbf6565fc`：

```bash
tvmao version                         # 2.0.0
tvmao --help
tvmao node create --help
tvmao node update --help
tvmao edge --help
tvmao model get doubao-seedance-2-0-fast-260128
```

默认模型使用稳定 ID `doubao-seedance-2-0-fast-260128`，而不是旧展示名
`Seedance 2.0 Fast VIP`。当前实时 schema 支持：

- `duration`：数字 `4..15`（另有 `-1`，TVSkill 不自动使用）；
- `ratio`：含 `9:16`；
- `resolution`：`480p` 或 `720p`；
- `prompt`：必填字符串。

每次实际写画布前仍须重新读取 schema。模型 ID、可用状态或 enum 漂移时停止写入，不能沿用缓存。

## 2. LibTV → TVMao 兼容性对照

| 旧 LibTV 假设 | TVMao 2.0 事实 | 迁移动作 |
|---|---|---|
| `libtv node list -p <UUID>` 返回 `{nodes:[...]}` | `tvmao node list --project <int>` 直接返回数组 | 解析器改为数组，项目 ID 改为整数 |
| `libtv node <id>` 兼做查询和修改 | `tvmao node get/update <id>` 明确分离 | 所有读写改用显式子命令 |
| 节点可按展示名查找和更新 | `node create/update` 没有节点名参数 | 更新必须显式传 `--node VNN=<节点ID>`；缺映射时创建新节点 |
| `-t video` | `--type video-generator` | 使用 TVMao 语义节点类型 |
| 展示模型名 `Seedance 2.0 Fast VIP` | 稳定 `modelId=doubao-seedance-2-0-fast-260128` | 旧名只在本地兼容映射中存在，写入使用稳定 ID |
| `params.settings={ratio,resolution,duration,enableSound}` | `params.prompt/ratio/resolution/duration` 扁平 | 删除嵌套 settings 与 `modeType` |
| 有 `enableSound` 开关 | Seedance 2.0 schema 不暴露声音开关 | 以台词合同、audio-input 入边和成片音轨验收代替，不伪造参数 |
| `mixedList` + `mixedListOrder` | 入边数组顺序就是模型输入顺序 | 用 `edge list --to` 回读；不存在额外 order 字段 |
| `--left-add/--left-rm` | `node update --left/--left-rm` | 更新时同一命令先删旧边，再按目标顺序追加 |
| `@[语义] {{Mixed N}}` 是旧内部 DSL | 网页 canonical 是 `@[图片:<nodeId>]`，运行时序列化为 `图片N` | 写入真实节点 ID token；普通 `@图片N` 不会形成 chip |
| 资源节点可按名字唯一匹配 | TVMao 输入节点没有可靠展示名匹配合同 | `--apply` 必须显式传 `--asset 素材或语义=<节点ID>` |
| 节点任务状态是数字 | `idle/generating/succeeded/failed` | 只允许更新 `idle`；其它状态新建版本节点 |
| 无素材合规命令 | doubao-seedance 输入需 `compliance active` | `--pre-run` 把全部素材 active 设为硬门禁 |
| 没有并发版本保护 | `node update --snapshot-version` | 参数更新前读 `canvas get.version` 并带回；多边重连须单独执行并精确回读 |

## 3. 唯一同步来源

画布同步只读取最终 `<集号>-LibTV视频节点提示词.md`。文件名与 `Mixed` 表格暂时保留，
用于兼容现有 110 项确定性校验；它们现在是 TVSkill 的平台中立内部 DSL，不是 TVMao 节点的
最终 prompt。

每个 `## 生成段 VNN` 对应一个 `video-generator` 节点：

- 完成提示词代码块先编译，再写入 `params.prompt`；
- Mixed 表格按行决定入边总顺序；
- 同媒体分别编号：图片、视频、音频各自从 1 开始；
- `@[单知影] {{Mixed 1}}` 写入为 `@[图片:n-abc]（单知影）`；网页运行时序列化为 `图片1（单知影）`；
- 模型、比例、分辨率和时长写入扁平 params；
- 运行状态阻塞、音色占位或规划图进入输入表时禁止同步。

编译必须满足：每个 Mixed 行恰好有对应官方引用，语义一致，编译后不残留
`{{Mixed N}}`、`{{Image N}}` 或 `{{Portrait N}}`。

### 3.1 图像资产节点不是视频 Mention 节点

上述 canonical mention 合同只适用于 `video-generator`。当前 `image-generator` 前端把 prompt 原文与 ordered `connectedImages` 分开提交，没有 `PromptMentionEditor` 序列化阶段：

- 真实关联是入边，不是 prompt chip；
- prompt 采用 `参考图N（语义名）`，N 按 `edge list --to` 从 1 排列；
- 普通 `图片N/图N` 缺少可审计语义，禁止使用；
- `@[图片:nodeId]` 在图像节点里不会被正确序列化，禁止使用；
- 运行依赖节点前用 `audit_image_asset_node.py --pre-run` 验证父图成功且有输出。

## 4. 素材上传与确定性映射

```bash
tvmao asset upload /absolute/path/to/ref.png --project <PROJECT_ID> --create-node
tvmao asset upload /absolute/path/to/voice.wav --project <PROJECT_ID> --create-node
```

TVMao 的输入类型为 `image-input`、`audio-input`、`video-input`。同步时素材名不能靠模糊搜索，
必须显式提供映射：

```bash
--asset '单知影身份图=n-abc123' \
--asset '单知影音色参考-5s=n-def456'
```

映射键可写素材列或绑定语义；同一行命中零个或多个节点都停止。输入节点类型必须与表格类型一致。

位置图、轨迹图、构图图、平面图、箭头图、文字标注图和未验收尾帧不得上传为正式输入边。

## 5. 两阶段写入

第一阶段只 dry-run：

```bash
python3 scripts/sync_delivery_markdown.py <本集.md> \
  --project <PROJECT_ID> \
  --asset '素材A=n-...' \
  --asset '素材B=n-...'
```

输出计划、稳定 modelId、编译后 prompt、目标输入顺序和缺失素材。明确授权写画布后才追加
`--apply`。已有 idle 节点的更新必须显式给段号映射：

```bash
--node V01=n-video123
```

没有节点映射时创建新节点。TVMao 没有可靠的节点名查找合同，禁止按前缀猜测节点。

同步脚本只调用 `node create` 或 `node update`，绝不调用 `node run`。写后必须重新执行：

```bash
tvmao node get <NODE_ID> --project <PROJECT_ID>
tvmao edge list --to <NODE_ID> --project <PROJECT_ID>
```

入边回读顺序与 Mixed 表格不一致时写入失败。

TVMao CLI 2.0.0 会把同一条 `node update` 中的多项 `--left-rm/--left` 展开为连续
画布写入，而每次写入都会递增版本。因此不能把固定 `--snapshot-version` 与多边重连放在
同一命令中，否则命令会与自身刚产生的新版本冲突。同步器先用快照版本保护参数更新；仅当
现有入边与目标入边不同，才单独执行幂等重连，并立即用 `edge list --to` 校验完整顺序。

## 6. 只读审计

TVMao 不支持节点名前缀筛选合同，因此审计必须显式指定节点，或明确选择全项目：

```bash
python3 scripts/audit_canvas_nodes.py \
  --project <PROJECT_ID> \
  --node <NODE_ID> \
  --asset '单知影身份图=n-abc123'

# 只有确实要审计项目内全部 video-generator 时：
python3 scripts/audit_canvas_nodes.py --project <PROJECT_ID> --all
```

审计以以下实时事实为准：

- `node get` 的 `modelId`、扁平 `params` 与状态；
- `edge list --to` 的有序上游节点；
- `node list` 的上游类型；
- `compliance status` 的素材合规状态；
- 节点 prompt 中的 `@[图片:<nodeId>]/@[视频:<nodeId>]/@[音频:<nodeId>]`，以及按入边序列化后的 `图片N/视频N/音频N`。

语义核对依赖 `--asset` 提供的人类可读标签；未提供时只能核对 ID、类型、编号和是否完整引用，
不能声称“语义资产完全正确”。

## 7. 合规与运行前凭证

`doubao-seedance*` 的上游素材必须先通过合规校验：

```bash
tvmao compliance verify <INPUT_NODE_ID>... --project <PROJECT_ID>
tvmao compliance status --project <PROJECT_ID>
```

校验是异步的。只有全部相关输入为 `active` 才能进入运行前门禁：

```bash
python3 scripts/audit_canvas_nodes.py \
  --project <PROJECT_ID> \
  --node <NODE_ID> \
  --asset '素材A=n-...' \
  --pre-run \
  --receipt <NODE_ID>-pre-run-audit.md
```

`--pre-run` 同时要求节点状态为 `idle`。凭证指纹覆盖 prompt、modelId、全部扁平 params、
有序入边、合规状态和节点状态。任一项变化后凭证立即失效。

## 8. 运行授权

运行是 TVMao 唯一消耗积分的动作，必须由用户对具体节点另行授权。`huabu_studio`
当前网页会先把 canonical mention 序列化为 `图片N/视频N/音频N`，但 TVMao CLI 2.0.0
的 `node run` 服务路径直接使用存储 prompt，没有执行同构序列化。因此 TVSkill 节点当前必须
从网页运行，不能执行下列命令：

```bash
tvmao node run <NODE_ID> --project <PROJECT_ID> --wait
```

也不能用 `--param-string prompt=...` 绕过：运行覆盖会写回 `settings.videoPrompt`，使节点丢失
关联 chip。只有 CLI 服务端补齐与 `PromptMentionEditor.serializeMentionPrompt` 同构的转换并
通过回归测试后，才能恢复 CLI 运行。不得把 `--wait`、`node run` 或任何隐式运行拼进同步脚本。同一连续组只运行当前可运行的第一段；
前段成片验收通过后，后段才允许绑定其稳定续接帧。

图像资产另按依赖 DAG 分层授权：用户对第一层的运行确认不授权第二层。每层全部终态并完成视觉验收后必须暂停，通过弹窗或等价明确选项取得下一层的新确认；随后才对下一层执行 `audit_image_asset_node.py --pre-run`。禁止自动级联运行。

## 9. 失败边界

- 找不到或未登录 TVMao：停止写入，保留 Markdown。
- 实时 model schema 不含目标参数或 enum 不接受当前值：停止，不私自降级模型。
- 缺少 `--asset`、节点不存在或输入类型不符：停止，不猜测。
- 更新目标不是 `idle`：停止并新建版本节点。
- 现有节点 modelId 与目标不同：`node update` 无法安全改模型，停止并新建版本节点。
- 入边回读顺序不一致：停止，不运行。
- 对 Seedance 的输入合规状态不是 `active`：运行前门禁失败。
- 审计有硬错误：不得运行，不得把已有结果登记为续接来源。
- 网络、认证或 schema 漂移：保留 stderr，不能误判为节点不存在。

官方入口只用于安装与人工核对，不是 skill 运行时外部知识依赖。
