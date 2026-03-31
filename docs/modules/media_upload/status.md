# Module Status: `media_upload`

## 基本信息

- `module`: `media_upload`
- `status`: `building`
- `branch`: `module/media_upload`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

负责图片上传、媒体元数据、类型与大小校验、对象存储 URL 生成，为后续场景理解提供稳定输入。

## 当前真相

- 现有实现：`api/models/media_model.py`、`api/db/media_db.py`、`api/integrations/storage/r2.py`
- 已完成边界：媒体模型和对象存储 URL 生成骨架
- 仍然缺失：上传路由、文件校验、真实持久化闭环

## 输入输出契约

- 输入：图片文件、文件名、媒体元数据
- 输出：媒体 ID、可访问 URL、后续可追踪的媒体记录
- 关键字段：`media_id`、`url`、文件类型、大小

## 代码位置

- `api/models/media_model.py`
- `api/db/media_db.py`
- `api/integrations/storage/`
- 未来相关 route：`api/routes/`

## 当前工作

- `[ ]` 明确上传接口输入输出
- `[ ]` 定义文件校验规则
- `[ ]` 补媒体创建与读取的最小测试

## 测试门

- `module_test_passed` 的标准：上传输入、媒体记录和 URL 生成链路可稳定验证
- 最少要覆盖的用例：合法文件、非法类型、超限输入、URL 生成
- 还没覆盖的风险：真实对象存储接入前后的行为差异

## 阻塞项

- 上传路由与测试尚未落地

## 变更记录

- `2026-03-30`：初始化模块状态文档
