# EchoWhale PRD

## 1. 项目概述

### 1.1 项目定位

EchoWhale 是一个面向日常口语初中级学习者的情景式英语陪练系统。用户上传一张日常生活图片后，系统识别图片中的场景和关键物体，基于该场景发起一段角色化英语对话，并对用户的回复给出简洁、可操作的学习反馈。

本项目优先做成：

- 一个可在线演示的开源作品
- 一个具备完整用户链路的 AI 教育产品原型
- 一个适合写入简历、能体现全栈 + AI 工程能力的项目

### 1.2 核心价值

- 把“看图识物”升级成“基于真实场景开口练英语”
- 把 AI 对话从泛聊天变成有明确语境的口语训练
- 把反馈从长篇解释收敛成用户真正能立刻吸收的建议

### 1.3 目标用户

- 日常口语初中级英语学习者
- 想提升实际开口能力，而不是只背单词和语法的人
- 需要轻量、高频、真实语境练习的学生或职场新人

## 2. 产品目标

### 2.1 MVP 目标

第一版只解决一个清晰问题：

> 用户上传一张生活场景图片后，能够在 3 分钟内完成一轮完整的英语情景对话练习，并收到简洁反馈。

### 2.2 成功标准

- 用户能成功上传图片并创建会话
- 系统能稳定给出一个合理场景和角色设定
- 用户至少完成 3 轮英文对话
- 每轮回复后都能获得结构化反馈
- 会话历史可回看

### 2.3 非目标

第一版暂不做：

- 语音识别和发音打分
- 本地模型训练与微调平台
- 复杂课程系统和付费体系
- 多角色群聊或多 Agent 协作可视化

## 3. 核心用户流程

### 3.1 主流程

1. 用户进入首页
2. 用户上传图片
3. 系统识别场景与关键物体
4. 系统生成角色身份和开场白
5. 用户用英文回复
6. 系统输出：
   - 教练式追问或回应
   - 语法纠错
   - 更自然表达
   - 推荐词汇
7. 用户继续多轮练习
8. 会话结束后保存历史记录

### 3.2 示例场景

- 餐厅点餐
- 咖啡店下单
- 办公室日常沟通
- 街头问路 / 出行场景

## 4. 功能需求

### 4.1 图片上传与媒体管理

- 支持上传常见图片格式
- 返回媒体 ID 与可访问 URL
- 为后续接入 Cloudflare R2 做预留
- 需要限制文件大小与类型

### 4.2 场景理解模块

- 输入：图片或图片元数据
- 输出：
  - 场景类型
  - 角色设定
  - 开场白
  - 视觉锚点
  - 教学词汇候选
  - 置信度

### 4.3 对话教练模块

- 根据场景与历史轮次生成回应
- 对话风格要简洁、自然、可继续追问
- 每轮只推动一个明确交流目标

### 4.4 学习反馈模块

- 每轮至少输出 3 类反馈：
  - `Grammar`
  - `More Natural`
  - `Useful Words`
- 反馈必须短，不做大段讲解

### 4.5 会话编排模块

- 串联场景理解、对话教练、学习反馈
- 管理多轮消息记录
- 保存会话状态与历史

### 4.6 历史记录

- 查看历史会话
- 查看对应场景、角色、消息和反馈
- 为后续复习功能预留入口

## 5. 系统模块划分

后端采用“产品结构清晰 + Agent 内部模块化”的混合结构。

### 5.1 API 层

- `auth`
- `uploads`
- `sessions`
- `history`
- `admin`

### 5.2 Agent / Engine 模块

#### `scene_engine`

- 负责图片理解和场景推断
- 输出场景、角色、开场白、视觉锚点和教学词汇候选

#### `coach_engine`

- 负责生成对话回复
- 保持角色一致性和多轮推进

#### `feedback_engine`

- 负责生成学习反馈
- 输出纠错、自然表达、关键词汇

#### `session_engine`

- 负责会话编排
- 串联前面三个 engine

## 6. 目录结构与职责说明

本项目目录设计目标是：

- 顶层一眼能看出产品入口
- 后端内部保留强模块化的 Agent 结构
- 前后端、基础设施、测试、文档边界清晰

### 6.1 顶层目录

```text
EchoWhale/
├── api/               # FastAPI 后端
├── frontend/          # React 前端
├── docs/              # 产品、架构与使用文档
├── tests/             # 测试代码
├── infra/             # 部署与基础设施配置
├── README.md          # 项目说明
├── requirements.txt   # 后端依赖
└── .env.example       # 环境变量示例
```

#### `api/`

- 后端主目录
- 负责 API、业务编排、Agent 模块、数据模型、第三方服务接入
- 是整个系统最核心的工程层

#### `frontend/`

- Web 前端目录
- 负责上传图片、展示对话、显示反馈和历史记录
- 后续部署到 Cloudflare Pages

#### `docs/`

- 文档目录
- 存放 PRD、架构设计、API 文档、使用说明
- 用于开源展示与协作沟通

#### `tests/`

- 测试目录
- 包含 API、模块级、集成测试
- 用于保证后续扩展 engine 时不破坏现有链路

#### `infra/`

- 基础设施目录
- 存放 Docker、Cloudflare、Terraform 等部署相关配置
- 用于区分业务代码与部署代码

### 6.2 后端目录结构

```text
api/
├── main.py            # FastAPI 启动入口
├── core/              # 核心配置
├── common/            # 公共组件
├── routes/            # API 路由层
├── services/          # 应用服务层
├── modules/           # Agent / Engine 模块层
├── models/            # 数据模型层
├── db/                # 持久化与数据访问
├── integrations/      # 第三方服务接入层
├── tasks/             # 异步任务
└── migrations/        # 数据库迁移
```

#### `api/main.py`

- FastAPI 应用启动入口
- 负责注册中间件、挂载路由、暴露健康检查

#### `api/core/`

- 系统级配置目录
- 负责环境变量读取、全局配置管理、未来的安全与日志配置
- 这里的代码不直接承载业务逻辑

#### `api/common/`

- 公共能力目录
- 放统一响应格式、公共异常、依赖注入、枚举等通用代码
- 作用是减少各模块重复实现基础逻辑

#### `api/routes/`

- API 路由层
- 负责接收 HTTP 请求、参数校验、调用 service、返回响应
- 不直接承载复杂业务逻辑

#### `api/routes/v1/`

- 第一版 API 路由命名空间
- 后续支持版本化演进时可以继续增加 `v2`

#### `api/services/`

- 应用服务层
- 面向路由，负责业务编排与模块调用
- 不应堆放 Prompt 和模型细节

#### `api/modules/`

- Agent / Engine 模块层
- 是 EchoWhale 与普通 FastAPI CRUD 项目最不一样的部分
- 每个模块对应一个明确的 AI 业务能力

#### `api/models/`

- 数据模型目录
- 当前阶段放会话、媒体、消息、用户等结构定义
- 后续可逐步演进为 ORM 或持久化实体层

#### `api/db/`

- 数据访问层
- 当前阶段使用轻量存储实现
- 后续替换为 PostgreSQL、Repository、Session 管理时仍沿用这一层

#### `api/integrations/`

- 第三方接入层
- 统一接入 LLM、对象存储、消息队列等外部依赖
- 目的是把业务逻辑与外部服务 SDK 解耦

#### `api/tasks/`

- 异步任务目录
- 为图片分析、会话总结、未来的批处理任务预留
- 后续可以接 Celery、RQ 或其他队列系统

#### `api/migrations/`

- 数据库迁移目录
- 当前先占位，后续接入数据库后用于维护 schema 版本

### 6.3 Agent 模块目录结构

```text
api/modules/
├── scene_engine/
├── coach_engine/
├── feedback_engine/
└── session_engine/
```

#### `scene_engine/`

- 场景理解模块
- 负责将图片信息转成“可对话的场景结构”

当前内部结构：

```text
scene_engine/
├── agent.py          # 场景理解主逻辑
├── schema.py         # 场景输入输出结构
├── service.py        # 对外调用入口
├── state.py          # 场景状态定义
├── prompts/          # 场景分析提示词
├── tools/            # 图片标签、预处理等工具
└── providers/        # 多模态/视觉模型适配层
```

各目录职责：

- `agent.py`
  - 负责组织场景理解流程
  - 调用 provider，输出统一结果
- `schema.py`
  - 定义输入输出结构
  - 确保上下游模块之间的契约稳定
- `service.py`
  - 作为模块对外入口
  - 供 `session_engine` 或 `services` 调用
- `state.py`
  - 存放该 engine 的状态定义
  - 为后续复杂上下文保留扩展点
- `prompts/`
  - 管理场景推断相关提示词
  - 避免 Prompt 分散在业务代码中
- `tools/`
  - 存放图片标签提取、预处理、小型规则工具
- `providers/`
  - 封装视觉模型或多模态模型适配
  - 后续可以切换不同供应商

#### `coach_engine/`

- 对话教练模块
- 负责生成角色化、可持续推进的英语对话

当前内部结构：

```text
coach_engine/
├── agent.py          # 对话生成主逻辑
├── schema.py         # 对话输入输出结构
├── service.py        # 对外调用入口
├── state.py          # 对话轮次和状态
├── prompts/          # 对话提示词
├── tools/            # 对话规则和追问工具
└── providers/        # 聊天模型适配层
```

各目录职责：

- `agent.py`
  - 负责角色设定、回复生成、追问控制
- `schema.py`
  - 定义 learner message、scene、reply 等结构
- `service.py`
  - 向外提供统一调用接口
- `state.py`
  - 管理轮次、上下文或角色状态
- `prompts/`
  - 存放系统提示词和对话风格控制模板
- `tools/`
  - 存放追问策略、规则问句等辅助逻辑
- `providers/`
  - 统一封装聊天模型供应商

#### `feedback_engine/`

- 学习反馈模块
- 负责把用户输入转成学习可吸收的反馈结果

当前内部结构：

```text
feedback_engine/
├── agent.py          # 反馈生成主逻辑
├── schema.py         # 反馈结构定义
├── service.py        # 对外调用入口
├── state.py          # 反馈状态定义
├── prompts/          # 反馈提示词
└── tools/            # 纠错和句式处理工具
```

各目录职责：

- `agent.py`
  - 负责纠错、自然表达、词汇建议的组合输出
- `schema.py`
  - 统一反馈结构，避免前端与后端字段不一致
- `service.py`
  - 对外暴露反馈生成能力
- `state.py`
  - 为后续个性化反馈保留状态扩展
- `prompts/`
  - 管理学习反馈相关 Prompt
- `tools/`
  - 存放句式整理、纠错辅助、小型规则逻辑

#### `session_engine/`

- 会话编排模块
- 负责把场景理解、对话生成、学习反馈串成一条主流程

当前内部结构：

```text
session_engine/
├── agent.py          # 会话主编排逻辑
├── schema.py         # 会话输入输出结构
├── service.py        # 对外调用入口
├── state.py          # 会话状态定义
└── prompts/          # 会话总结与编排提示词
```

各目录职责：

- `agent.py`
  - 负责统一调度 `scene_engine`、`coach_engine`、`feedback_engine`
- `schema.py`
  - 统一会话创建、消息发送等结构
- `service.py`
  - 供 `session_service` 或其他应用层调用
- `state.py`
  - 管理 session 生命周期和状态
- `prompts/`
  - 存放总结类或会话编排类提示词

### 6.4 前端目录结构

```text
frontend/
├── public/           # 静态资源
└── src/
    ├── components/   # 可复用 UI 组件
    ├── pages/        # 页面级组件
    ├── services/     # 前端 API 调用封装
    ├── hooks/        # 自定义 hooks
    └── utils/        # 前端工具函数
```

各目录职责：

- `frontend/public/`
  - 放公共静态资源和 HTML 模板
- `frontend/src/components/`
  - 放上传组件、对话组件、反馈组件等复用 UI
- `frontend/src/pages/`
  - 放首页、上传页、会话页、历史页
- `frontend/src/services/`
  - 封装与后端 API 的交互逻辑
- `frontend/src/hooks/`
  - 放认证、会话状态等自定义 hooks
- `frontend/src/utils/`
  - 放格式化、文案处理、前端公共工具

### 6.5 测试与基础设施目录

#### `tests/api/`

- API 层测试
- 验证接口入参与响应结构是否正确

#### `tests/modules/`

- 模块级测试
- 分别测试 scene、coach、feedback、session 四个 engine

#### `tests/integration/`

- 集成测试
- 重点测试上传 -> 会话 -> 多轮消息 -> 历史记录这条主链路

#### `infra/docker/`

- Docker 相关配置
- 用于本地与部署环境统一

#### `infra/cloudflare/`

- Cloudflare 相关配置
- 后续放置 Pages、R2、Turnstile、缓存策略等配置说明或脚本

#### `infra/terraform/`

- 基础设施自动化配置目录
- 如果后续需要自动化部署，可在这里维护 IaC
## 7. 技术方案

### 6.1 前端

- React
- 页面结构：
  - 首页
  - 上传页
  - 会话页
  - 历史页

### 6.2 后端

- FastAPI
- 按 `routes / services / modules / models / db / integrations` 拆分
- 第一版允许先使用内存存储或 mock 数据打通链路

### 6.3 存储与基础设施

- 数据库存储用户、会话、媒体元数据
- 对象存储使用 Cloudflare R2
- CDN 使用 Cloudflare
- 后续可增加 Redis 队列处理图片分析与总结任务

### 6.4 模型策略

- 第一版采用 API 优先
- 保留 provider 抽象，后续可切换不同多模态和对话模型
- 不将模型供应商细节暴露到业务层

## 8. Cloudflare 方案

### 7.1 第一版使用范围

- Cloudflare Pages：前端部署
- Cloudflare R2：图片存储
- Cloudflare CDN：静态资源与图片分发
- Turnstile：防刷与基础防滥用

### 7.2 设计原则

- Cloudflare 负责分发和媒体链路
- 模型推理仍由后端或外部模型 API 承担
- 避免第一版把复杂推理迁移到边缘侧

## 9. 开源与简历导向要求

### 8.1 开源要求

- 仓库结构清晰，访客一眼能看懂产品入口
- 提供 `.env.example`
- 提供 README、PRD、架构文档
- 模块边界清楚，便于后续贡献

### 8.2 简历亮点

项目应体现以下能力：

- FastAPI 模块化后端设计
- React 前端交互设计
- 基于场景的 Agent 编排
- 第三方模型与存储的适配层设计
- Cloudflare 基础设施整合能力

## 10. 验收标准

### 9.1 功能验收

- 可以完成图片上传 -> 创建会话 -> 多轮对话 -> 查看历史的完整链路
- 系统对不同图片文件名或场景输入能给出不同会话结果
- 每轮都能输出结构化反馈

### 9.2 工程验收

- 基础目录结构搭建完成
- 模块边界明确
- PRD 与代码目录一致
- 后续新增 engine 不需要推翻现有结构

## 11. 版本规划

### v0.1

- 完成仓库基础结构
- 完成 PRD、README、架构文档

### v0.2

- 完成 mock 数据链路
- 打通图片上传、会话创建、消息发送

### v0.3

- 接入真实模型与 Cloudflare R2
- 完成前端基础交互页面

### v0.4

- 增加会话总结与历史复习能力
- 完善测试与部署文档
