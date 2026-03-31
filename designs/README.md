# EchoWhale Designs

这个目录存放 EchoWhale 的 Pencil 设计资产。

## 当前文件

- `echowhale-mvp.pen`：MVP 主设计文件

## 维护规则

- 页面和组件统一在 `.pen` 中命名，不使用随手命名的临时 frame。
- 每个核心页面都要以 `Screen/*` 命名。
- 每个共享组件都要以 `Component/*` 命名。
- 设计变量至少覆盖颜色、间距、圆角、投影和字体层级。
- 原型一旦驱动前端实现，就要同步更新 `docs/modules/frontend_app/design_mapping.md`。

## 当前范围

- 首页
- 上传入口
- 练习会话页
- 历史记录页

## 备注

当前工作流把 Pencil 作为主设计源，不再以 Figma 为主。
