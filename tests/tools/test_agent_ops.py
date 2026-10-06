from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.agent_ops import (
    GENERATED_END,
    GENERATED_START,
    bootstrap_document,
    check_workspace,
    render_project_index,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_project_index_updates_generated_block_and_preserves_manual_content(
    tmp_path: Path,
) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    project_index_path = workspace / "docs" / "control" / "project-index.md"

    render_project_index(workspace)

    rendered = project_index_path.read_text(encoding="utf-8")
    assert "Manual intro" in rendered
    assert "## 模块看板" in rendered
    assert "| `platform_foundation` |" in rendered
    assert "## 测试门" in rendered
    assert "Manual footer" in rendered


def test_check_workspace_reports_invalid_status_value(tmp_path: Path) -> None:
    workspace = _create_minimal_workspace(tmp_path)
    facts_path = workspace / "docs" / "control" / "agent-control-plane.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    facts["modules"][0]["status"] = "broken"
    facts_path.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = check_workspace(workspace)

    assert report.errors
    assert any("broken" in error for error in report.errors)


@pytest.mark.parametrize(
    ("artifact_type", "slug", "expected_path"),
    [
        (
            "feature",
            "agent_governance_control_plane",
            "docs/features/agent_governance_control_plane/feature.md",
        ),
        ("bug", "control-plane-drift", "docs/bugs/control-plane-drift/bug.md"),
    ],
)
def test_bootstrap_document_creates_docs_from_template(
    tmp_path: Path,
    artifact_type: str,
    slug: str,
    expected_path: str,
) -> None:
    workspace = _create_minimal_workspace(tmp_path)

    created = bootstrap_document(
        workspace,
        artifact_type=artifact_type,
        slug=slug,
        module="platform_foundation",
        owner="codex",
    )

    assert created == workspace / expected_path
    content = created.read_text(encoding="utf-8")
    assert slug in content
    assert "<" not in content


def test_current_workspace_control_plane_is_consistent() -> None:
    report = check_workspace(REPO_ROOT)

    assert report.errors == []


@pytest.mark.parametrize(
    ("artifact_type", "slug", "expected_path"),
    [
        (
            "feature",
            "resilience-closing-batch",
            "docs/features/resilience-closing-batch/feature.md",
        ),
        ("bug", "bootstrap-placeholder-gap", "docs/bugs/bootstrap-placeholder-gap/bug.md"),
        ("module", "observability", "docs/modules/observability/status.md"),
        ("version", "0.6.0", "docs/versions/0.6.0.md"),
    ],
)
def test_bootstrap_four_subcommands_render_without_residual_placeholders(
    tmp_path: Path,
    artifact_type: str,
    slug: str,
    expected_path: str,
) -> None:
    """bootstrap 四种子命令回归：渲染产物无残留占位符，关键行替换正确。

    module=None 走默认值路径：分支行的 <module-name> 与 <primary_module_name>
    同落 platform_foundation；version 的 published_at 未发布诚实留空。
    """
    workspace = _create_minimal_workspace(tmp_path)

    created = bootstrap_document(
        workspace,
        artifact_type=artifact_type,
        slug=slug,
        module=None,
        owner="codex",
    )

    assert created == workspace / expected_path
    content = created.read_text(encoding="utf-8")
    assert "<" not in content
    assert ">" not in content
    assert slug in content

    if artifact_type == "feature":
        assert "- `branch`: `feature/platform_foundation/resilience-closing-batch`" in content
        assert "- `merge_target`: `module/platform_foundation`" in content
        assert "- `module`: `platform_foundation`" in content
    elif artifact_type == "bug":
        assert "- `branch`: `bugfix/platform_foundation/bootstrap-placeholder-gap`" in content
        assert "- `merge_target`: `module/platform_foundation`" in content
        assert "- `affected_area`: `bootstrap-placeholder-gap`" in content
    elif artifact_type == "module":
        assert "- `branch`: `module/platform_foundation`" in content
    else:
        assert "- `published_at`: ``" in content


def _create_minimal_workspace(workspace: Path) -> Path:
    _write(
        workspace / "docs" / "control" / "project-index.md",
        "\n".join(  # noqa: FLY002 - 模板按行列举更贴近产出文件的可读性
            [
                "# Control",
                "",
                "Manual intro",
                "",
                GENERATED_START,
                "stale",
                GENERATED_END,
                "",
                "Manual footer",
                "",
            ]
        ),
    )
    _write(
        workspace / "docs" / "control" / "agent-control-plane.json",
        json.dumps(
            {
                "system": {
                    "status": "integrating",
                    "repo_summary": "backend 已成型，前端与测试持续补齐",
                    "strategy": "先稳控制面，再持续补模块与系统验证",
                },
                "latest_snapshot": {
                    "latest_record": "docs/features/auth_email_code_verification/feature.md",
                    "summary": "邮箱验证码链路已切真",
                    "blockers": "真实 Redis / SMTP smoke 仍待补齐",
                    "extra_progress": "live provider 配置门禁已收紧",
                },
                "modules": [
                    {
                        "name": "platform_foundation",
                        "docs_path": "docs/modules/platform_foundation/status.md",
                        "status": "building",
                        "exit_gate": "module_test_passed",
                        "merge_target": "integration/system",
                        "notes": "控制面和共享底座",
                        "owner_files": ["api/main.py", "api/core/"],
                        "branch_hint": "module/platform_foundation",
                        "focus": "共享能力",
                    }
                ],
                "features": [
                    {
                        "name": "控制面治理",
                        "scope": "platform_foundation",
                        "status": "in_progress",
                        "exit_gate": "feature_test_passed",
                        "merge_target": "module/platform_foundation",
                    }
                ],
                "test_layers": [
                    {
                        "name": "smoke",
                        "what_to_prove": "应用能启动",
                        "status": "planned",
                        "exit_criteria": "入口稳定",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    _write(
        workspace / "docs" / "features" / "_template" / "feature.md",
        "# Feature: `<feature_name>`\n"
        "- `feature`: `<feature_name>`\n"
        "- `branch`: `feature/<module-name>/<feature-name>`\n"
        "- `module`: `<primary_module_name>`\n"
        "- `owner`: `<owner>`\n"
        "- `updated_at`: `<YYYY-MM-DD>`\n"
        "- `merge_target`: `module/<module-name>`\n",
    )
    _write(
        workspace / "docs" / "bugs" / "_template" / "bug.md",
        "# Bug: `<bug_title>`\n"
        "- `bug`: `<bug_title>`\n"
        "- `branch`: `bugfix/<module-name>/<bug-name>`\n"
        "- `owner`: `<owner>`\n"
        "- `reported_at`: `<YYYY-MM-DD>`\n"
        "- `affected_area`: `<module or feature>`\n"
        "- `merge_target`: `module/<module-name>`\n",
    )
    _write(
        workspace / "docs" / "modules" / "_template" / "status.md",
        "# Module Status: `<module_name>`\n"
        "- `module`: `<module_name>`\n"
        "- `branch`: `module/<module-name>`\n"
        "- `owner`: `<owner>`\n"
        "- `updated_at`: `<YYYY-MM-DD>`\n",
    )
    _write(
        workspace / "docs" / "versions" / "_template" / "version.md",
        "# Version: `<version_name>`\n"
        "- `version`: `<version_name>`\n"
        "- `created_at`: `<YYYY-MM-DD>`\n"
        "- `published_at`: `<YYYY-MM-DD or blank>`\n",
    )
    _write(
        workspace / "docs" / "modules" / "platform_foundation" / "status.md",
        "# Module Status: `platform_foundation`\n- `module`: `platform_foundation`\n",
    )
    return workspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
