# EchoWhale 后端统一规范与实时语音陪练总设计

## 1. 文档目的

这份文档用于先统一 EchoWhale 后端的整体设计，再按模块逐步实现。

当前目标不是直接写完全部功能，而是先把以下内容定死：

- 后端模块边界
- 数据表结构
- API 结构与响应体规范
- Deepgram 实时语音陪练接入方式
- 文本对话、语音对话、学习辅助、中文显示之间的职责划分

后续实现以本文件为准，再按功能拆分成单独任务推进。

---

## 2. 当前项目现状

### 2.1 已有基础

- `api/` 已有 FastAPI scaffold
- `scene_engine`、`coach_engine`、`feedback_engine`、`session_engine` 已有 mock 级骨架
- 前端已有会话页、历史页、上传页、登录注册页的结构化原型
- 目前图片分析、对话生成、反馈生成主要仍是 mock 行为

### 2.2 当前主要缺口

- 没有稳定的业务 API 路由体系
- 没有统一的响应体与错误码规范
- 没有正式数据库模型与持久化结构
- 历史记录、认证、上传、练习、语音链路还没有统一契约
- Deepgram 语音代理尚未正式接入

### 2.3 这轮设计要解决的问题

这轮不是只修一个接口，而是要先建立一个可以持续扩展的后端底座，保证以后实现每个功能时不会反复推翻协议。

---

## 3. 产品目标拆分

EchoWhale 当前后端目标拆成三层：

### 3.1 主对话层

- 用户和角色扮演 Agent 全程只说英语
- 主对话沉浸感优先
- 一次只推进一个明确交流目标
- 这层主要依赖 Deepgram Voice Agent 的实时 listen / think / speak 能力

### 3.2 学习辅助层

- 每句对话后给“建议这样回答”
- 如果用户不会说，给一条更合适的英文句子
- 如果用户说中文或明显不是英语，要引导用户改用英语
- 这层不直接混入主语音 agent，而是由 EchoWhale 后端旁路生成

### 3.3 界面理解层

- 前端对话框显示中文，降低初中级学习者理解门槛
- 保留英文原句用于真实练习和复盘
- 中文只作为显示层和学习层数据，不进入主语音角色上下文

---

## 4. 推荐总体架构

```text
React Frontend
  ├─ 图片上传
  ├─ Talk to your agent 按钮
  ├─ 麦克风采集 / 音频播放
  ├─ 中文聊天气泡
  ├─ 建议回答气泡
  └─ 历史回放与练后反馈

FastAPI Backend
  ├─ 认证与用户体系
  ├─ 图片上传与媒体管理
  ├─ 场景分析与角色生成
  ├─ 会话主表与历史管理
  ├─ Deepgram token / settings 下发
  ├─ ConversationText 旁路处理
  ├─ 中文翻译与建议回答生成
  ├─ 英语约束检查
  └─ 练后反馈与复盘数据生成

Deepgram Voice Agent
  ├─ listen: flux-general-en v2
  ├─ think: 角色化英语对话
  └─ speak: aura-2-cordelia-en
```

### 4.1 连接方式

推荐采用：

- 前端浏览器直连 Deepgram Voice Agent WebSocket
- FastAPI 负责：
  - 下发 Deepgram 临时 token
  - 生成本轮 Voice Agent `Settings` / `Prompt`
  - 接收前端回传的关键事件
  - 产出中文显示和建议回答
  - 英语约束检查(通过SceneEngineAgent产出的图片上每个物品的口语化单词进行小阶段检查)
  - 会话落库
  - 保存历史记录

### 4.2 为什么不让后端转发整条语音流

- 实时语音最怕延迟
- Deepgram 官方就是以 WebSocket 实时通道为核心
- 如果所有音频都先绕后端，再转发 Deepgram，会增加实现复杂度和实时抖动
- EchoWhale 真正要做的价值不在音频转发，而在产品级旁路逻辑

---

## 5. 后端模块划分

### 5.1 platform_foundation

负责：

- 应用启动
- 配置加载
- 数据库连接
- 统一响应体
- 统一异常与错误码
- 路由注册
- 安全与鉴权底座

不负责：

- 具体业务文案
- 具体场景逻辑

### 5.2 media_upload

负责：

- 图片上传
- 文件类型与大小校验
- 媒体元数据记录
- 对象存储 key 与临时读取地址生成
- 存储 key 与私有对象访问策略的稳定映射

不负责：

- 场景分析
- 会话生成

存储策略约束：

- 正式环境采用“私有对象存储 + 临时签名读取 URL”方案，当前目标是 Cloudflare R2 private bucket
- 数据库主记录应保存 `storage_key` 与 `upload_status`，不要把服务器本地磁盘路径或永久公开 URL 当成正式契约
- 开发期允许先落本地目录并暴露静态 URL 作为 fallback，但这只用于本地联调，不作为生产架构
- 后续即使更换读取策略，也应优先通过 `storage_key` 重新签发访问地址，而不是依赖旧磁盘路径

### 5.3 scene_engine

负责：

- 根据图片信息输出场景类型
- 生成角色身份
- 生成首句开场白
- 输出关键标签与目标

### 5.4 session_orchestration

负责：

- 创建练习 session
- 串联 scene、coach、feedback
- 维护文本练习与语音练习共用的事实数据模型

### 5.5 coach_layer

负责：

- 为 assistant 的每一轮话术生成建议回答
- 给出“你可以这样说”
- 在用户卡壳、沉默或说中文时给出帮助

说明：

- 这是产品级“学习辅助层”
- 不建议直接与主语音角色完全混成一个 agent

### 5.6 history_review

负责：

- 历史列表
- 单次会话回放
- 中英文消息对照
- 练后总结与下一步建议

### 5.7 voice_agent_integration

负责：

- Deepgram token 管理
- Voice Agent settings 生成
- 语音事件记录
- 与前端的实时状态配合

不负责：

- 完整翻译逻辑本身
- 场景分析逻辑本身

---

## 6. 数据模型总览

后端统一采用关系型主结构，推荐 PostgreSQL。

### 6.1 users

用途：用户主表

字段建议：

- `id`
- `nickname`
- `email`
- `status`
- `created_at`
- `updated_at`

### 6.2 user_credentials

用途：邮箱密码登录凭证

字段建议：

- `id`
- `user_id`
- `provider`
- `password_hash`
- `last_login_at`
- `created_at`
- `updated_at`

### 6.3 refresh_tokens

用途：登录刷新令牌

字段建议：

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `revoked_at`
- `created_at`

### 6.4 media_assets

用途：图片上传记录

字段建议：

- `id`
- `user_id`
- `filename`
- `content_type`
- `file_size`
- `storage_key`
- `upload_status`
- `created_at`

说明：

- `storage_key` 是对象存储中的稳定主键，后续切换公有/私有访问策略时优先依赖它
- 前端与下游读取图片时，应优先通过 `storage_key` 换取短时效读取 URL，而不是消费永久外链
- 如果开发期先用本地静态目录模拟上传，也应尽量保持 `storage_key` 这组契约不变，避免后续接入 R2 时重做数据模型
- `upload_status` 建议至少支持 `pending`、`uploaded`、`failed`
- 正式写库顺序建议是：先生成记录和 `storage_key`，上传成功后把状态切为 `uploaded`，读取地址按需再签发

### 6.5 scene_profiles

用途：图片分析结果快照

字段建议：

- `id`
- `media_id`
- `scene_type`
- `role_name`
- `conversation_goal`
- `opener_en`
- `opener_zh`
- `tags_json`
- `confidence`
- `created_at`

说明：

- 一张图片在未来可能允许重新分析，因此建议把分析结果独立成表

### 6.6 practice_sessions

用途：会话主表

字段建议：

- `id`
- `user_id`
- `media_id`
- `scene_profile_id`
- `session_mode`
- `status`
- `level`
- `started_at`
- `ended_at`
- `created_at`
- `updated_at`

说明：

- `session_mode` 至少支持 `text`、`voice`

### 6.7 practice_messages

用途：统一的会话消息事实表

字段建议：

- `id`
- `session_id`
- `turn_index`
- `speaker`
- `source`
- `english_text`
- `display_zh`
- `language_ok`
- `message_status`
- `created_at`

说明：

- 不管是文本输入还是语音输入，最终都落到这张表
- `speaker` 支持 `user`、`assistant`、`coach`、`system`
- `source` 支持 `text`、`voice`、`hint`、`review`

### 6.8 practice_suggestions

用途：存每一轮建议回答

字段建议：

- `id`
- `session_id`
- `message_id`
- `suggested_reply_en`
- `suggested_reply_zh`
- `more_natural_en`
- `more_natural_zh`
- `hint_type`
- `created_at`

说明：

- 一般挂在 assistant 说完后的那条消息上
- 这是学习辅助层的核心数据

### 6.9 practice_feedbacks

用途：练后或轮次反馈

字段建议：

- `id`
- `session_id`
- `message_id`
- `grammar_en`
- `grammar_zh`
- `more_natural_en`
- `more_natural_zh`
- `useful_words_json`
- `next_step_en`
- `next_step_zh`
- `created_at`

### 6.10 voice_agent_sessions

用途：每次 Deepgram 实时连接

字段建议：

- `id`
- `session_id`
- `deepgram_request_id`
- `deepgram_connection_status`
- `listen_model`
- `listen_version`
- `speak_model`
- `prompt_version`
- `opened_at`
- `closed_at`
- `created_at`

### 6.11 voice_agent_events

用途：记录关键实时事件

字段建议：

- `id`
- `voice_agent_session_id`
- `event_type`
- `event_role`
- `content_text`
- `raw_payload_json`
- `created_at`

说明：

- 主要记录 `Welcome`、`SettingsApplied`、`ConversationText`、`UserStartedSpeaking`、`AgentThinking`、`AgentAudioDone`、`Error`、`Warning`

### 6.12 session_reviews

用途：练后总结

字段建议：

- `id`
- `session_id`
- `highlight_zh`
- `next_try_zh`
- `summary_en`
- `summary_zh`
- `created_at`

---

## 7. API 统一规范

### 7.1 响应体规范

参考 `Fastapi-template`，统一采用：

```json
{
  "code": 200,
  "message": "Success",
  "data": {}
}
```

错误时：

```json
{
  "code": 1004,
  "message": "Resource not found",
  "data": null
}
```

### 7.2 错误码层级建议

- `1001` 参数校验错误
- `1002` 认证失败
- `1003` 无权限
- `1004` 资源不存在
- `1005` 服务器内部错误
- `1101` 文件类型非法
- `1102` 文件大小超限
- `1201` session 不存在
- `1202` session 状态非法
- `1301` 语音 bootstrap 失败
- `1302` Deepgram token 获取失败
- `1303` 语音事件写入失败
- `1401` 非英语输入

### 7.3 路由域划分

推荐路由如下：

#### auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

#### media

- `POST /api/v1/media/upload`
- `GET /api/v1/media/{media_id}`

#### practice

- `POST /api/v1/practice/sessions`
- `GET /api/v1/practice/sessions/{session_id}`
- `POST /api/v1/practice/sessions/{session_id}/turns`
- `POST /api/v1/practice/sessions/{session_id}/voice/bootstrap`
- `POST /api/v1/practice/sessions/{session_id}/voice/events`
- `POST /api/v1/practice/sessions/{session_id}/voice/finalize`
- `GET /api/v1/practice/sessions/{session_id}/review`

#### history

- `GET /api/v1/history/sessions`
- `GET /api/v1/history/sessions/{session_id}`

#### system

- `GET /api/v1/system/health`

---

## 8. 关键接口说明

### 8.1 图片上传

`POST /api/v1/media/upload`

输入方式建议：

- `multipart/form-data`
- 文件字段统一使用 `file`
- 第一版只接受单文件上传

默认校验建议：

- 文件类型：`image/jpeg`、`image/png`、`image/webp`
- 文件大小：默认不超过 `10 MB`
- 文件名仅作为展示字段使用，入库存储路径必须重新生成安全 `storage_key`

处理流程建议：

1. 后端先校验类型、大小和基础文件头
2. 生成 `media_id` 与 `storage_key`
3. 上传到对象存储；开发环境可写本地静态目录 fallback
4. 落库 `media_assets`
5. 签发短时效 `preview_url`
6. 返回媒体元数据给前端

成功输出建议：

- `media_id`
- `filename`
- `content_type`
- `file_size`
- `storage_key`
- `preview_url`
- `preview_url_expires_at`
- `upload_status`

失败输出建议：

- 非法类型返回 `1101`
- 文件超限返回 `1102`
- 存储写入失败返回 `1005` 或后续单独细分 media storage 错误码

响应示例：

```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "media_id": "med_123456",
    "filename": "coffee-shop.png",
    "content_type": "image/png",
    "file_size": 245812,
    "storage_key": "media/demo-user/2026/04/01/med_123456-coffee-shop.png",
    "preview_url": "https://signed.example.com/media/demo-user/2026/04/01/med_123456-coffee-shop.png?signature=demo",
    "preview_url_expires_at": "2026-04-02T12:00:00Z",
    "upload_status": "uploaded"
  }
}
```

### 8.2 获取媒体详情

`GET /api/v1/media/{media_id}`

用途：

- 给前端或 session 创建流程读取媒体元数据
- 给后续 scene analysis、history detail 等链路复用统一媒体事实

输出建议：

- `media_id`
- `user_id`
- `filename`
- `content_type`
- `file_size`
- `storage_key`
- `upload_status`
- `created_at`

说明：

- 如果媒体不存在，返回 `1004`
- 如果媒体状态不是 `uploaded`，创建 session 时应拒绝继续下游分析

### 8.3 创建会话

`POST /api/v1/practice/sessions`

输入：

- `media_id`
- `mode`
- `level`

输出：

- `session_id`
- `scene`
- `role`
- `opener_en`
- `opener_zh`
- `tags`
- `status`

说明：

- `media_id` 必须指向一个 `upload_status = uploaded` 的媒体记录
- 创建 session 时通过 `storage_key` 换取签名 URL，不直接依赖永久公开外链

### 8.4 文本练习回合

`POST /api/v1/practice/sessions/{session_id}/turns`

输入：

- `content`

输出：

- 新增 message
- suggestion
- feedback

### 8.5 语音 bootstrap

`POST /api/v1/practice/sessions/{session_id}/voice/bootstrap`

用途：

- 前端点击 `Talk to your agent` 前调用

输出：

- `deepgram_token`
- `deepgram_ws_url`
- `settings`
- `initial_agent_message`
- `voice_agent_session_id`

### 8.6 语音事件旁路写入

`POST /api/v1/practice/sessions/{session_id}/voice/events`

用途：

- 前端收到关键 Deepgram 事件后，把产品需要的事件回传后端

输入建议：

- `voice_agent_session_id`
- `event_type`
- `role`
- `content_text`
- `raw_payload`

输出建议：

- `persisted_message`
- `display_zh`
- `suggestion`
- `language_guard`
- `session_state_patch`

### 8.7 历史详情

`GET /api/v1/history/sessions/{session_id}`

输出：

- session 基本信息
- 中英文消息列表
- suggestion 列表
- feedback 列表
- 练后 review

---

## 9. Deepgram 接入设计

### 9.1 目标配置

目标对齐你指定的 playground 风格：

- endpoint: `agent`
- language: `en`
- speak model: `aura-2-cordelia-en`
- listen version: `v2`
- listen model: `flux-general-en`

### 9.2 正式实现原则

不把 `promptId=customer-support` 当成生产实现依赖。

原因：

- playground URL 里的 `promptId` 更像产品预设引用
- 正式后端更稳妥的方式，是由 EchoWhale 后端生成自己的 `agent.think.provider.prompt`
- 这样角色扮演、英语约束、教学风格都由项目自己控制

### 9.3 Voice Agent Settings 生成原则

Settings 核心思路：

- `audio.input.encoding = linear16`
- `audio.output.encoding = linear16`
- `agent.listen.provider.model = flux-general-en`
- `agent.listen.provider.version = v2`
- `agent.speak.provider.model = aura-2-cordelia-en`
- `agent.think.provider` 使用可配置 LLM
- `agent.think.prompt` 写入 EchoWhale 自己的角色设定

### 9.4 prompt 规则建议

prompt 至少包含这些约束：

- 你是一个角色化英语陪练对象
- 只使用英语
- 学习者也必须尽量用英语回答
- 如果学习者使用中文，不要切换成中文
- 要用简单、鼓励式、自然的英语要求对方再试一次
- 每次只推进一个明确交流目标
- 回复保持简洁

### 9.5 首句触发

前端收到 `SettingsApplied` 后，应立即触发首句开场。

首句来源：

- 来自 `scene_engine` 的 `opener_en`

使用方式：

- 前端向 Deepgram 发 `InjectAgentMessage`

---

## 10. 实时事件流

推荐流程：

### 10.1 创建准备

1. 前端上传图片
2. 后端分析图片，生成场景、角色、首句
3. 前端请求 `voice/bootstrap`
4. 后端返回 token 与 settings

### 10.2 建立实时连接

1. 前端连接 Deepgram websocket
2. 收到 `Welcome`
3. 发送 `Settings`
4. 收到 `SettingsApplied`

### 10.3 首句发出

1. 前端发送 `InjectAgentMessage`
2. agent 开始第一句英语角色对话

### 10.4 对话进行中

前端持续处理：

- `ConversationText`
- `UserStartedSpeaking`
- `AgentThinking`
- `AgentAudioDone`

### 10.5 旁路写入与学习辅助

当收到 assistant 的 `ConversationText`：

- 前端显示英文原句
- 前端调用后端旁路事件接口
- 后端生成：
  - 中文显示
  - 建议这样回答
  - 更自然版本
- 前端渲染建议卡

当收到 user 的 `ConversationText`：

- 前端调用旁路事件接口
- 后端判断是否是英语
- 若不是英语：
  - 标记 `language_guard`
  - 返回“请尽量用英语回答”
  - 返回一条建议句

### 10.6 结束与复盘

1. 用户结束本轮练习
2. 前端调用 `voice/finalize`
3. 后端生成练后 summary / review
4. 历史页可查看中英文对照与建议

---

## 11. 学习辅助层设计

### 11.1 建议回答

触发时机：

- assistant 每说完一轮后

输出内容：

- `suggested_reply_en`
- `suggested_reply_zh`
- `more_natural_en`
- `more_natural_zh`

前端呈现方式：

- 在 assistant 消息后立即弹出一张建议卡

### 11.2 卡壳提示

推荐优先实现为文字 coach，而不是第二个实时语音 agent。

原因：

- 不会打断主角色沉浸感
- 不会让“角色”和“老师”混在一起
- 更容易控制展示与收起

触发条件可包括：

- 用户长时间沉默
- 用户连续两次明显非英语
- 用户输入过短且无法推进对话

### 11.3 英语约束

采用双保险：

#### 第一层：prompt 约束

主 Voice Agent prompt 明确要求：

- only speak English
- learner should answer in English

#### 第二层：后端守卫

后端收到 user 文本后再判断：

- 如果不是英语，不推进正常学习回合
- 返回 coach 提示

---

## 12. 前端需要配合的状态机

建议至少维护以下状态：

- `idle`
- `connecting`
- `ready`
- `assistant_speaking`
- `waiting_user`
- `user_speaking`
- `thinking`
- `showing_suggestion`
- `error`
- `ended`

关键事件驱动：

- `SettingsApplied` -> `ready`
- 首句注入 -> `assistant_speaking`
- `AgentAudioDone` -> `waiting_user`
- `UserStartedSpeaking` -> `user_speaking`
- `AgentThinking` -> `thinking`

---

## 13. 实现顺序建议

为了降低返工，建议实现顺序固定如下：

### Phase 1：平台统一规范

- 统一响应体
- 统一异常
- 统一错误码
- 路由注册结构
- 数据库连接与 ORM

### Phase 2：认证与媒体

- 注册 / 登录 / refresh / me
- 图片上传
- 媒体记录
- R2 / CDN 公开地址契约

### Phase 3：文本练习主链路

- 创建 session
- 文本输入回合
- suggestion / feedback
- 历史列表与详情

### Phase 4：Deepgram 语音 bootstrap

- token 下发
- settings 生成
- voice session 建模

### Phase 5：实时事件旁路

- ConversationText 写库
- 中文显示生成
- 建议回答生成
- 英语约束守卫

### Phase 6：练后复盘

- review summary
- 历史回放
- 历史详情聚合

---

## 14. 当前默认假设

如果你没有额外改动，当前文档默认采用以下假设：

- 数据库采用 PostgreSQL 目标建模
- 正式媒体存储采用 Cloudflare R2 private bucket + signed URL，开发期可临时使用本地静态目录 fallback
- 媒体记录以 `storage_key` 和 `upload_status` 为主，不把本地磁盘路径或永久公开 URL 作为正式数据库契约
- 前端浏览器直连 Deepgram
- 后端只处理业务旁路，不转发整条音频流
- 中文只做显示与学习辅助，不进入主语音上下文
- “另一个 agent”默认做成文字 coach，不先做第二个语音 agent
- 用户体系首轮一起纳入，而不是继续用 demo user

---

## 15. 下一步协作方式

你接下来可以按这份文档逐条给我反馈，例如：

- 哪些表要删
- 哪些接口要先做
- 哪些字段命名想改
- Deepgram 部分要不要换成后端桥接
- 认证要不要缩小范围

等你确认后，我再按功能逐个实现，而不是一次性铺开。
