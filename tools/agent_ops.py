from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

GENERATED_START = "<!-- agent-control:generated:start -->"
GENERATED_END = "<!-- agent-control:generated:end -->"
FACTS_PATH = Path("docs/control/agent-control-plane.json")
PROJECT_INDEX_PATH = Path("docs/control/project-index.md")

FEATURE_STATUSES = {"planned", "in_progress", "feature_test_passed", "merged_to_module", "closed"}
MODULE_STATUSES = {"planned", "building", "module_test_passed", "merged_to_integration", "closed"}
SYSTEM_STATUSES = {"idle", "integrating", "full_flow_test_passed", "releasable"}
TEST_LAYER_STATUSES = {"planned", "building", "passed"}
ARTIFACT_TYPES = {"feature", "bug", "module", "version"}


@dataclass(slots=True)
class CheckReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class AgentOpsError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EchoWhale agent governance tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate governance facts and docs")
    check_parser.add_argument("--root", type=Path, default=Path.cwd())

    render_parser = subparsers.add_parser("render", help="Render docs/control/project-index.md")
    render_parser.add_argument("--root", type=Path, default=Path.cwd())

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Bootstrap governance docs from templates")
    bootstrap_parser.add_argument("artifact_type", choices=sorted(ARTIFACT_TYPES))
    bootstrap_parser.add_argument("slug")
    bootstrap_parser.add_argument("--root", type=Path, default=Path.cwd())
    bootstrap_parser.add_argument("--module")
    bootstrap_parser.add_argument("--owner", default="unassigned")

    args = parser.parse_args(argv)

    if args.command == "check":
        report = check_workspace(args.root)
        for warning in report.warnings:
            print(f"WARNING: {warning}")
        for error in report.errors:
            print(f"ERROR: {error}")
        return 0 if report.ok else 1

    if args.command == "render":
        render_project_index(args.root)
        print(f"Rendered {PROJECT_INDEX_PATH.as_posix()}")
        return 0

    if args.command == "bootstrap":
        created = bootstrap_document(
            args.root,
            artifact_type=args.artifact_type,
            slug=args.slug,
            module=args.module,
            owner=args.owner,
        )
        print(created.as_posix())
        return 0

    raise AgentOpsError(f"Unsupported command: {args.command}")


def check_workspace(root: Path) -> CheckReport:
    report = CheckReport()
    facts_path = root / FACTS_PATH
    project_index_path = root / PROJECT_INDEX_PATH

    if not facts_path.exists():
        report.errors.append(f"Missing control facts file: {FACTS_PATH.as_posix()}")
        return report
    if not project_index_path.exists():
        report.errors.append(f"Missing project index: {PROJECT_INDEX_PATH.as_posix()}")
        return report

    facts = _load_facts(facts_path)
    _validate_facts(root, facts, report)

    rendered_block = _build_generated_block(facts)
    try:
        current_block = _extract_generated_block(project_index_path.read_text(encoding="utf-8"))
    except AgentOpsError as exc:
        report.errors.append(str(exc))
        return report

    if current_block.strip() != rendered_block.strip():
        report.errors.append(
            "docs/control/project-index.md generated block is out of date. Run `uv run python -m tools.agent_ops render`."
        )
    return report


def render_project_index(root: Path) -> Path:
    facts = _load_facts(root / FACTS_PATH)
    project_index_path = root / PROJECT_INDEX_PATH
    content = project_index_path.read_text(encoding="utf-8")
    rendered = _replace_generated_block(content, _build_generated_block(facts))
    project_index_path.write_text(rendered, encoding="utf-8")
    return project_index_path


def bootstrap_document(
    root: Path,
    *,
    artifact_type: str,
    slug: str,
    module: str | None,
    owner: str,
) -> Path:
    if artifact_type not in ARTIFACT_TYPES:
        raise AgentOpsError(f"Unsupported artifact type: {artifact_type}")

    template_path, output_path = _template_and_output_paths(root, artifact_type, slug)
    template = template_path.read_text(encoding="utf-8")
    today = date.today().isoformat()
    replacements = {
        "<feature_name>": slug,
        "<primary_module_name>": module or "platform_foundation",
        "<owner>": owner,
        "<YYYY-MM-DD>": today,
        "<bug_title>": slug,
        "<module or feature>": module or slug,
        "<module_name>": slug,
        "<version_name>": slug,
        "<major.minor.patch>": slug,
    }
    content = template
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    if "<" in content or ">" in content:
        raise AgentOpsError(f"Unresolved template placeholders remain in {template_path.as_posix()}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _template_and_output_paths(root: Path, artifact_type: str, slug: str) -> tuple[Path, Path]:
    if artifact_type == "feature":
        return (
            root / "docs/features/_template/feature.md",
            root / f"docs/features/{slug}/feature.md",
        )
    if artifact_type == "bug":
        return (
            root / "docs/bugs/_template/bug.md",
            root / f"docs/bugs/{slug}/bug.md",
        )
    if artifact_type == "module":
        return (
            root / "docs/modules/_template/status.md",
            root / f"docs/modules/{slug}/status.md",
        )
    return (
        root / "docs/versions/_template/version.md",
        root / f"docs/versions/{slug}.md",
    )


def _load_facts(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_facts(root: Path, facts: dict[str, Any], report: CheckReport) -> None:
    system = facts.get("system", {})
    if system.get("status") not in SYSTEM_STATUSES:
        report.errors.append(f"Invalid system status: {system.get('status')}")

    latest_snapshot = facts.get("latest_snapshot", {})
    latest_record = latest_snapshot.get("latest_record")
    if latest_record and not (root / latest_record).exists():
        report.errors.append(f"Missing latest snapshot record: {latest_record}")

    for module in facts.get("modules", []):
        if module.get("status") not in MODULE_STATUSES:
            report.errors.append(f"Invalid module status for {module.get('name')}: {module.get('status')}")
        docs_path = module.get("docs_path")
        if docs_path and not (root / docs_path).exists():
            report.errors.append(f"Missing module doc: {docs_path}")

    for feature in facts.get("features", []):
        if feature.get("status") not in FEATURE_STATUSES:
            report.errors.append(f"Invalid feature status for {feature.get('name')}: {feature.get('status')}")

    for layer in facts.get("test_layers", []):
        if layer.get("status") not in TEST_LAYER_STATUSES:
            report.errors.append(f"Invalid test layer status for {layer.get('name')}: {layer.get('status')}")


def _extract_generated_block(content: str) -> str:
    if GENERATED_START not in content or GENERATED_END not in content:
        raise AgentOpsError(
            "docs/control/project-index.md is missing generated markers."
        )
    start_index = content.index(GENERATED_START) + len(GENERATED_START)
    end_index = content.index(GENERATED_END)
    return content[start_index:end_index].strip("\n")


def _replace_generated_block(content: str, block: str) -> str:
    if GENERATED_START not in content or GENERATED_END not in content:
        raise AgentOpsError(
            "docs/control/project-index.md is missing generated markers."
        )
    start_index = content.index(GENERATED_START) + len(GENERATED_START)
    end_index = content.index(GENERATED_END)
    return f"{content[:start_index]}\n{block}\n{content[end_index:]}"


def _build_generated_block(facts: dict[str, Any]) -> str:
    lines: list[str] = []
    system = facts["system"]
    snapshot = facts["latest_snapshot"]

    lines.extend(
        [
            "## 当前总态",
            "",
            f"- `system`: `{system['status']}`",
            f"- 真实仓库状态：{system['repo_summary']}",
            f"- 当前策略：{system['strategy']}",
            "",
            "## 最新进度快照",
            "",
            f"- 最新归档：`{snapshot['latest_record']}`",
            f"- 本轮结论：{snapshot['summary']}",
            f"- 当前主要阻塞：{snapshot['blockers']}",
            f"- 补充进展：{snapshot['extra_progress']}",
            "",
            "## 模块看板",
            "",
            "| Area | Docs Path | Current Status | Exit Gate | Merge Target | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for module in facts["modules"]:
        lines.append(
            f"| `{module['name']}` | `{module['docs_path']}` | `{module['status']}` | `{module['exit_gate']}` | `{module['merge_target']}` | {module['notes']} |"
        )

    lines.extend(
        [
            "",
            "## 模块清单",
            "",
            "| Module | Owner File | Status | Branch Hint | Focus |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for module in facts["modules"]:
        owner_files = ", ".join(f"`{item}`" for item in module["owner_files"])
        lines.append(
            f"| `{module['name']}` | {owner_files} | `{module['status']}` | `{module['branch_hint']}` | {module['focus']} |"
        )

    lines.extend(
        [
            "",
            "## 关键 Feature",
            "",
            "| Feature | Scope | Status | Exit Gate | Merge Target |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for feature in facts["features"]:
        lines.append(
            f"| {feature['name']} | `{feature['scope']}` | `{feature['status']}` | `{feature['exit_gate']}` | `{feature['merge_target']}` |"
        )

    lines.extend(
        [
            "",
            "## 测试门",
            "",
            "| Test Layer | What to Prove | Status | Exit Criteria |",
            "| --- | --- | --- | --- |",
        ]
    )
    for layer in facts["test_layers"]:
        lines.append(
            f"| {layer['name']} | {layer['what_to_prove']} | `{layer['status']}` | {layer['exit_criteria']} |"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
