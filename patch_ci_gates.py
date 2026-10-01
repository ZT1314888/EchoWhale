# -*- coding: utf-8 -*-
"""coverage 脚本 + CI 更新（ruff 步骤 / coverage 运行 / actions v5）。跑完即删。"""
import yaml
from pathlib import Path

# ---------- package.json ----------
p = Path("frontend/package.json")
src = p.read_text(encoding="utf-8")
old = '"test": "vitest run",\n    "typecheck": "tsc --noEmit"'
new = '"test": "vitest run",\n    "typecheck": "tsc --noEmit",\n    "coverage": "vitest run --coverage"'
assert src.count(old) == 1, src.count(old)
p.write_text(src.replace(old, new, 1), encoding="utf-8", newline="")
print("OK package.json")

# ---------- .github/workflows/ci.yml ----------
p = Path(".github/workflows/ci.yml")
src = p.read_text(encoding="utf-8")

old = "- uses: actions/checkout@v4"
assert src.count(old) == 2
src = src.replace(old, "- uses: actions/checkout@v5", 2)

old = "- uses: actions/setup-node@v4"
assert src.count(old) == 1
src = src.replace(old, "- uses: actions/setup-node@v5", 1)

old = """      - name: Sync dependencies (frozen lockfile)
        run: uv sync --frozen

      - name: Prepare sqlite schema for app-level routes"""
new = """      - name: Sync dependencies (frozen lockfile)
        run: uv sync --frozen

      - name: Lint (ruff)
        run: uv run ruff check api tests tools

      - name: Prepare sqlite schema for app-level routes"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

old = """      - name: Unit tests
        run: npm test"""
new = """      - name: Unit tests (coverage thresholds)
        run: npm run coverage"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

p.write_text(src, encoding="utf-8", newline="")

# 校验结构
d = yaml.safe_load(p.read_text(encoding="utf-8"))
on = d[True] if True in d else d["on"]
backend_steps = [s.get("name") for s in d["jobs"]["backend"]["steps"]]
frontend_steps = [s.get("name") for s in d["jobs"]["frontend"]["steps"]]
print("push_branches:", on["push"]["branches"])
print("backend_steps:", backend_steps)
print("frontend_steps:", frontend_steps)
assert "Lint (ruff)" in backend_steps
assert any("coverage" in (n or "") for n in frontend_steps)
print("OK ci.yml")
