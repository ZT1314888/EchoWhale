# `scene_engine` Live Evaluation

## 目标

用项目里已经上传到 R2 的真实图片，对 `scene_engine` 做独立评估，验证：

- `scene` 是否匹配预期场景
- `visual_anchors` 是否覆盖关键视觉线索
- `vocab_candidates` 是否适合英语口语练习
- `role + opener` 是否适合英语口语练习
- 脏样本是否会稳定落入 `unsupported_image`

## 入口

- 测试文件：`tests/modules/test_scene_engine_live.py`
- 评估模块：`api/modules/scene_engine/evaluation.py`
- 规则文件：`api/modules/scene_engine/evaluation_rules.py`
- 默认输出：`tmp/scene_engine_eval/results.jsonl`

## 样本文件格式

环境变量 `SCENE_EVAL_CASES_FILE` 指向一个 JSON 文件，内容是数组。每个元素格式如下：

```json
[
  {
    "sample_id": "office-001",
    "filename": "office-meeting.jpg",
    "signed_url": "https://signed.example/media/demo-user/office-meeting.jpg",
    "expected_scene": "office",
    "expected_visual_anchor_keywords": ["glass wall"],
    "expected_vocab_keywords": ["meeting"],
    "expected_role_keywords": ["coworker"],
    "sample_type": "normal",
    "expected_outcome": "analysis"
  }
]
```

## 通过线

- `normal` 样本：
  - `scene_match >= 80%`
  - `final_pass >= 80%`
  - `visual_anchor_match >= 70%`
  - `vocab_match >= 70%`
  - `vocab_value_pass >= 80%`
- `edge_case` 样本：
  - `expected_outcome=unsupported_image` 时，应稳定返回 `actual_outcome=unsupported_image`
  - 不允许再被算作正常场景分析成功

## 结果解释

每条 JSONL 记录包含：

- 样本标识与类型
- 当前视觉 provider / model
- `prompt_version`
- `prompt_hash`
- `expected_outcome`
- `actual_outcome`
- 原始/归一化输出
- `scene_match`
- `visual_anchor_match`
- `vocab_match`
- `vocab_value_pass`
- `final_pass`
- `failure_reason`
