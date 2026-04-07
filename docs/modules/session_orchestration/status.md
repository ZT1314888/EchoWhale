# Module Status: `session_orchestration`

## 基本信息

- `module`: `session_orchestration`
- `status`: `building`
- `branch`: `module/session_orchestration`
- `owner`: `codex`
- `updated_at`: `2026-04-07`

## 模块目标

串联 scene、coach、feedback 三个模块，管理会话状态、消息聚合与主链路推进。

## 当前真相

- 现有实现：`api/modules/session_engine/`、`api/db/session_db.py`、`api/routes/v1/sessions.py`
- 已完成边界：`start/get/reply/review` 主链路已落地，session/message/review 已切到数据库持久化，前端上传成功后会创建真实 session 并进入真实练习页
- 已完成边界：session 创建前仍会校验媒体必须为 `uploaded`，场景分析继续通过签名 URL 读取媒体对象
- 已完成边界：history 列表与详情读取接口已落地，前端 `PostPracticeReview` / `History` 已切到真实后端读取
- 已完成边界：已修复 session 初始 opener 持久化时的父子写入顺序问题，`POST /api/v1/sessions` 不再因 `session_messages_session_id_fkey` 在严格 FK 数据库下报错
- 已完成边界：session owner 已切到 `user:* / visitor:*` 命名空间，匿名体验与登录用户边界不再依赖 `default_user_id`
- 已完成边界：新增 `/api/v1/sessions/{session_id}/voice/bootstrap` 与 `/api/v1/sessions/{session_id}/voice/complete`，可向前端下发 Deepgram token + settings，并在结束时将 transcript 回写为 session messages 与 review
- 已完成边界：Deepgram voice bootstrap 已补生产配置门禁、adapter 异常翻译和 `1302` 错误收口，不再把底层 `httpx.LocalProtocolError` 直接打成 500
- 已完成边界：Deepgram voice settings 当前走原生 `agent.think.provider + prompt` 路径，浏览器直连保留不变，但实时语音热路径不再依赖公网 think proxy
- 已完成边界：前端语音 hook 已补初始化超时与 `AgentThinking` 超时保护，卡顿时会退出等待态并回写 `init_phase / thinking_stall_ms`
- 已完成边界：前端语音 hook 已切到低延迟采集与连续播放排程，当前默认使用 `AudioContext({ latencyHint: 'interactive' })`、`ScriptProcessor(1024)` 优先、单声道 `ideal 16kHz` 采集和 `nextPlayTime` 连续调度
- 已完成边界：Deepgram voice settings 已补 Flux `eot_threshold / eager_eot_threshold / eot_timeout_ms` 与可配置 `output_sample_rate`，并把更多音频侧 diagnostics 带回 `voice/complete`
- 仍然缺失：跨模块更完整的系统级联调

## 输入输出契约

- 输入：`user_id`、`media_id`、学习者回复、历史会话上下文
- 输出：会话对象、状态推进、消息聚合结果
- 关键字段：`session_id`、`status`、`messages`

## 代码位置

- `api/modules/session_engine/`
- `api/db/session_db.py`
- `api/routes/v1/sessions.py`

## 当前工作

- `[x]` 明确 start/get/reply 三条主链路
- `[x]` 落数据库 session/message repository 与迁移脚本
- `[x]` 补 session API 与模块级最小测试
- `[x]` 对接 history/review 查询链路
- `[x]` 收口 reply 原子更新与空输入校验
- `[x]` 修复 session 首条 message 在 FK 严格数据库下的持久化顺序 bug
- `[x]` 接入 Deepgram Voice Agent bootstrap / complete 编排路径
- `[ ]` 做更完整的前后端系统联调

## 测试门

- `module_test_passed` 的标准：会话启动、快照读取、回复推进、review/history 读取可稳定验证
- 已覆盖：session repository 持久化、session API start/get/reply/review、voice bootstrap/complete、history 列表与详情、媒体状态保护、session 签名 URL 消费、reply 原子更新、严格 FK 模式下的 session 初始 message 持久化回归
- 还没覆盖的风险：跨模块系统级联调、真实 Deepgram token + 国内网络实机 smoke、匿名 visitor 到正式账号的升级绑定

## 阻塞项

- 真实文本主链路已闭环，语音主链路的 bootstrap / complete 也已落地；当前剩余的是完整 `upload -> session -> deepgram voice -> review -> history` 实链路 smoke test

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-04-03`：新增 session repository、数据库迁移与 `/api/v1/sessions` start/get/reply 路由，前端练习主路径接入真实 session API
- `2026-04-04`：新增 `/api/v1/sessions/{session_id}/review` 与 `/api/v1/history/sessions*`，补 session review 持久化、reply 原子更新、前端 review/history 切真
- `2026-04-04`：修复 `save_session()` 在 FK 严格数据库下先写 `session_messages` 的顺序 bug，补强 FK 回归测试与 PostgreSQL 定向验证
- `2026-04-05`：引入真实 auth 与 `visitor_id`，session owner 改为 `user:* / visitor:*` 命名空间，`history` 读取切到真实登录用户范围
- `2026-04-06`：`POST /api/v1/sessions` 遇到 unsupported scene image 时返回 `422/1007`，基础设施型 scene 失败改为显式 `503`，不再静默创建通用会话
- `2026-04-06`：新增 Deepgram Voice Agent bootstrap / complete API、token/settings 组装与 transcript 回写路径
- `2026-04-06`：补齐 Deepgram voice 配置门禁与 adapter 错误收口；`voice/bootstrap` 遇到 token 获取失败时改为返回 `1302`，并记录脱敏配置状态日志
- `2026-04-06`：补齐 Voice Agent `agent.think.provider` / `endpoint` schema，并新增 `/api/v1/deepgram/think/chat/completions` 代理国内 OpenAI-compatible think 网关
- `2026-04-07`：为国内无 VPN 场景移除实时 `agent.think.endpoint` 依赖，改回原生 `provider + prompt`，并在前端补初始化/思考超时保护
- `2026-04-07`：补齐低延迟音频热路径，前端改为低延迟采集 + 连续播放排程，后端下发 Flux turn-taking 参数和 output sample rate 配置

