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
        ("feature", "agent_governance_control_plane", "docs/features/agent_governance_control_plane/feature.md"),
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


def _create_minimal_workspace(workspace: Path) -> Path:
    _write(
        workspace / "docs" / "control" / "project-index.md",
        "\n".join(
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
        "# Feature: `<feature_name>`\n- `feature`: `<feature_name>`\n- `module`: `<primary_module_name>`\n- `owner`: `<owner>`\n- `updated_at`: `<YYYY-MM-DD>`\n",
    )
    _write(
        workspace / "docs" / "bugs" / "_template" / "bug.md",
        "# Bug: `<bug_title>`\n- `bug`: `<bug_title>`\n- `affected_area`: `<module or feature>`\n- `owner`: `<owner>`\n- `reported_at`: `<YYYY-MM-DD>`\n",
    )
    _write(
        workspace / "docs" / "modules" / "_template" / "status.md",
        "# Module Status: `<module_name>`\n- `module`: `<module_name>`\n- `owner`: `<owner>`\n- `updated_at`: `<YYYY-MM-DD>`\n",
    )
    _write(
        workspace / "docs" / "versions" / "_template" / "version.md",
        "# Version: `<version_name>`\n- `version`: `<version_name>`\n- `created_at`: `<YYYY-MM-DD>`\n",
    )
    _write(
        workspace / "docs" / "modules" / "platform_foundation" / "status.md",
        "# Module Status: `platform_foundation`\n- `module`: `platform_foundation`\n",
    )
    return workspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
