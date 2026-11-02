# 学员档案读取 API 与前端进度页（learner_profile_progress）

> PRD v0.5 候选①收口：学员档案的写路径与提示词注入已就绪（learner_profile_prompt_injection，
> P2-7），但用户自己看不到——数据躺 `user_learning_profiles`，无读取 API、无进度页。
> 本批补齐"我的进度"读侧闭环。
> Trellis 任务：`.trellis/tasks/10-06-learner-profile-progress`。

## 目标

1. 认证用户能看到自己的滚动学习档案：CEFR 水平估计、常见错误类型、练习过的场景、累计轮数。
2. 读侧闭环不破坏既有不变量：任何响应不得外露原始 scene id（F17 单一事实源延伸）；
   提示词注入格式与 API 契约解耦。
3. 空档案（首访用户）是合法展示态：200 空载荷 + 前端引导文案，而非 404。

## 用户故事

- 当我完成若干轮练习后打开"我的进度"，我希望看到自己当前的水平估计和最常见的错误类型，
  这样我就知道下一轮该重点注意什么。
- 当我是新用户还没有任何练习时，我希望看到清晰的引导而不是报错，
  这样我就知道去上传图片开始第一次练习。

## 实现说明

### 1. 后端：GET /api/v1/learners/me/profile（只读、认证必需、无限流）

- **路由** `api/routes/v1/learners.py`：新资源组 `learners`，薄路由；本地
  `get_learner_profile_service()` 依赖 + `require_authenticated_user`（无/坏 Bearer 在依赖处
  即 401 code 1002，访客到不了业务逻辑，故无需 apply_visitor_cookie）；owner 串用
  `build_user_owner`（档案 PK 是 `user:<id>` 全串）。纯读点查无 LLM 成本面，与其他 GET
  一致不限流。`api/routes/v1/__init__.py` 注册。
- **服务** `api/services/learner_profile_service.py`：`LearnerProfileService` 仓库 get 透传。
  两个定案：
  - 不复用 `SessionEngineService`（history 的做法）——只读点查不值得拉起完整编排器
    （R2 signer、media/session 仓库），专用依赖让测试替身更干净；
  - 不复用 `agent._load_learner_profile`——写路径捕获异常降级 None 是回复轮增强分支的
    正确语义，但读 API 复用会把存储故障伪装成"空档案"；读路径不做降级吞错，仓库异常
    如实上抛 500 信封。
- **契约** `api/contracts/learner.py`（add-only 新文件）：`LearnerProfileResponse.from_profile`
  在契约层组装展示载荷（先例：contracts/history.py 调 review_builder）；None → 全空载荷
  （cefr null、空列表、0、updated_at null）。
- **展示映射** `api/modules/session_engine/learner_profile.py` 追加（既有注入函数逐字节不动）：
  - `ERROR_CATEGORY_LABELS`：9 类封闭集合 → 中文展示名（服务端持有，前端不维护副本）；
  - `MAX_DISPLAYED_ERROR_CATEGORIES = 3` / `MAX_DISPLAYED_SCENES = 12`：API 载荷独立硬顶，
    与注入面常数（MAX_INJECTED_ERROR_CATEGORIES）、写侧封顶（settings.scene_cap）互不引用
    ——注入面、写侧行宽、API 载荷是三个各自有界性论证的面；
  - `select_display_error_types`：9 类封闭集合防御过滤（读侧同源防御，防手改库/历史脏数据）
    + `(-count, category)` 确定性排序 + top 3；
  - `select_display_scenes`：键经 `review_builder.get_scene_title` 映射为展示名，
    **同名展示场景计数合并**（SCENE_COPY 中 street/travel 文案相同，映射后不合并会出现
    重复条目）+ `(-count, scene_title)` 排序 + cap 12。

### 2. 前端：/progress 进度页

- `frontend/src/pages/ProgressPage.tsx`（143 行）：CEFR 卡（页面内 A1..C2 中文文案映射表，
  "进阶（B1）"式样；null 显示"暂无水平估计"引导态）、常见错误类型列表（中文 label + 次数）、
  练习场景列表（展示名 + 次数）、累计轮数 + 最近更新；空态按 `practicedTurnCount === 0`
  判定（有轮数必有场景，判据充分），引导"上传图片开始第一次练习"Link 回首页；
  loading / form-error 态沿用惯例；语义 section/h1/h2/ul，非流式无需 aria-live。
- `frontend/src/services/learnerApi.ts` + `types/app.ts` 三类型：snake_case DTO → camelCase
  mapper（`getLearnerProfile`），错误经 toError 映射中文文案（信封 message 透传、本地
  "学习进度加载失败。"兜底）。
- 导航入口：`UserMenu` 面板"退出登录"前加"我的进度"菜单项（react-router `Link` +
  `role="menuitem"`）；`App.tsx` /progress 挂 RequireAuth（与 /history 同款）。
- 样式：`components.css` 追加 progress-* 小块，全部复用既有设计令牌（CSS 变量），
  未引入新体系。

### 3. 声明 ↔ 代码出处对照

| 声明（PRD §4.8 / api.md §12） | 代码出处 | 锁定测试 |
| --- | --- | --- |
| 认证必需，访客/匿名 401（code 1002） | `api/routes/v1/learners.py::get_my_learner_profile`（`require_authenticated_user`） | `tests/api/test_learner_routes.py::test_profile_requires_authentication` + `::test_profile_rejects_invalid_access_token` |
| 空档案 200 全空载荷而非 404 | `api/contracts/learner.py::LearnerProfileResponse.from_profile` | `tests/api/test_learner_routes.py::test_missing_profile_returns_empty_payload_instead_of_404` |
| 场景键全部服务端映射展示名，响应无原始 scene id | `api/modules/session_engine/learner_profile.py::select_display_scenes`（经 `review_builder.get_scene_title`） | `tests/api/test_learner_routes.py::test_profile_maps_display_names_and_merges_same_copy_scenes`（含无原始 id 负向断言）+ `tests/modules/test_learner_profile.py::test_select_display_scenes_humanizes_unknown_scene_ids`（gym 回退） |
| 同名展示场景计数合并（street/travel） | `select_display_scenes` 合并逻辑 | `tests/modules/test_learner_profile.py::test_select_display_scenes_maps_titles_and_merges_same_copy` |
| 错误类型 top ≤3 含中文展示名（映射在服务端） | `ERROR_CATEGORY_LABELS` + `select_display_error_types` | `tests/modules/test_learner_profile.py::test_select_display_error_types_sorts_by_count_then_category` / `::test_select_display_error_types_drops_out_of_set_keys` + 路由有数据用例 `::test_profile_maps_display_names_and_merges_same_copy_scenes` |
| 载荷有界（top 3 错误 / ≤12 场景） | `MAX_DISPLAYED_ERROR_CATEGORIES` / `MAX_DISPLAYED_SCENES` | `tests/api/test_learner_routes.py::test_scene_payload_is_capped_at_twelve` + `tests/modules/test_learner_profile.py::test_select_display_error_types_caps_at_three` / `::test_select_display_scenes_caps_at_twelve` |
| 只读不做降级吞错（存储故障如实 500） | `api/services/learner_profile_service.py` docstring 定案 | 设计约束（读路径无 try/except；信封由 main.py 全局处理器渲染） |
| 读 API 不与提示词注入格式耦合 | `build_learner_context_lines` 零改动，契约仅引用 `select_display_*` | 既有注入用例未动全绿 + 契约 import 面 |
| 前端空态引导与有数据渲染 | `frontend/src/pages/ProgressPage.tsx` | `frontend/src/App.test.tsx` 三个新用例 |
| /progress 挂 RequireAuth、未登录跳转 | `frontend/src/App.tsx` | `frontend/src/App.test.tsx::…anonymous…progress…` |

### 4. 明确排除项（遗留）

- 档案写入路径改动（写侧数学、封顶策略、更新时机均不动）。
- 档案编辑 / 目标设定（CEFR 目标、纠错偏好等用户自改能力）。
- SRS 复习机制（基于错误画像的间隔复习）。
- LLM ReviewCopy 生产消费（PRD v0.5 候选②，另行立项）。
- 访客档案（visitor 不建档是既有身份边界决策，维持不变）。
- 工具注记：`tools.agent_ops bootstrap feature` 的模板含未映射占位符（`<module-name>` 等）
  导致 bootstrap 报错，本批 feature.md 按模板手工创建；模板修复另行小件，不在本批范围。

## 验证

- 后端：`MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api` **589 passed / 9 skipped**
  （基线 578/9，+11 用例），覆盖率 **89.02%**（门禁 87，基线 88.91% 抬升；
  新增 `learner_profile_service.py` 100%）；`uv run ruff check api tests tools`、
  `uv run black --check api tests tools` 全绿。
- 前端：`npm run typecheck` 通过；`npm run coverage` 16 文件 / 115 用例全过（基线 107），
  覆盖率 **Stmts 86.44 / Branch 78.04 / Funcs 84.57 / Lines 86.44** vs 阈值 76/74/78/76，
  四项高于基线（85.97/77.42/84.02/85.97），阈值未动（Branch 两次测量差 ±0.03 属
  v8 覆盖率测量噪声）。
- 环境注记：本机 `.env` 为 live 模式，`tests/api/test_telemetry_e2e.py` 的全栈 e2e 未在
  测试内 pin mock，裸跑会因真实 coach 调用超时失败（与本批无关的既有环境陷阱）；按
  implement.md 风险条目以 `MODEL_RUNTIME_MODE=mock` 进程 pin 复跑全绿。
- 控制面：`docs/control/agent-control-plane.json` 已更新并 `render` + `check` 一致。

## 合并与关闭

- `feature_test_passed` 即达成（上节门禁全绿）；merge target：`module/session_orchestration`
  （档案域归属，前端页面随 frontend_app 看板同步）。
- 相关文档：`docs/api.md` §3 / §12、`docs/prd.md` §4.8 / §11、控制面事实源。
