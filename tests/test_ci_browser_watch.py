"""The `browser-tests` job can't pass without testing (team.md Testing Posture).

The job in .github/workflows/ci.yml skips its browser run on a pull request
that changes no watched file. These tests keep that watch list complete: every
browser test file, and every project source file one of them imports or
launches, must be on it, so a change to any of them runs the browser tests.
They also check that no test is marked both `perf` and `browser`.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
# The paths the team rule names, plus the dashboard the browser tests launch.
REQUIRED = (
    "scripts/postdeploy_check.py",
    "dashboard/markers.py",
    "dashboard/auth_gate.py",
    "dashboard/app.py",
    "agents/build_info.py",
    "tests/test_any_browser.py",
    "requirements-dev.txt",
    ".github/workflows/ci.yml",
    # pytest loads it for every browser test: the signing secret and audit path.
    "tests/conftest.py",
)


def watch_pattern(text=None):
    """The `grep -Eq '<pattern>'` the browser-tests job matches changed paths against."""
    text = CI.read_text() if text is None else text
    job = text[text.index("\n  browser-tests:") :]
    match = re.search(r"grep -Eq '([^']+)'", job)
    assert match, "browser-tests job has no grep -Eq watch list"
    return re.compile(match.group(1))


def browser_files():
    return sorted(p for p in (ROOT / "tests").glob("*browser*") if p.suffix == ".py")


def _module_file(module):
    base = ROOT.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _path_chain(node):
    """``ROOT / "dashboard" / "app.py"`` as ["dashboard", "app.py"]."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _path_chain(node.left)
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            return [*left, node.right.value]
        return left
    return []


def _absolute_module(node, path):
    """The dotted module an ImportFrom names, with relative imports resolved."""
    if node.level == 0:
        return node.module
    package = list(path.relative_to(ROOT).parent.parts)
    package = package[: len(package) - (node.level - 1)]
    return ".".join([*package, *([node.module] if node.module else [])])


def direct_sources(path):
    """Project files ``path`` imports, or names as a ``.py`` path to launch."""
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(_module_file(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and (node.module or node.level):
            module = _absolute_module(node, path)
            # `from dashboard import markers` uses the submodule; the package
            # file counts only when a name comes from the package itself.
            submodules = [_module_file(f"{module}.{alias.name}") for alias in node.names]
            found.update(submodules)
            if not all(submodules):
                found.add(_module_file(module))
        elif isinstance(node, ast.BinOp):
            parts = _path_chain(node)
            if parts and parts[-1].endswith(".py"):
                found.add(ROOT.joinpath(*parts) if ROOT.joinpath(*parts).is_file() else None)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py"):
            candidate = ROOT / node.value
            found.add(candidate if "/" in node.value and candidate.is_file() else None)
    found.discard(None)
    return {p.resolve() for p in found}


def project_sources(path):
    """Every project file ``path`` reaches: its imports and the scripts it
    launches, followed transitively through those files' own imports (so a
    change to, say, dashboard/secrets_bridge.py runs the browser tests)."""
    seen, todo = set(), [path.resolve()]
    while todo:
        for found in direct_sources(todo.pop()):
            if found not in seen:
                seen.add(found)
                todo.append(found)
    return {p.relative_to(ROOT).as_posix() for p in seen}


@pytest.mark.parametrize("path", REQUIRED)
def test_required_paths_are_watched(path):
    assert watch_pattern().search(path), f"{path} is not on the browser-tests watch list"


def test_there_are_browser_test_files():
    names = {p.name for p in browser_files()}
    assert {"test_postdeploy_browser.py", "browser_app.py"} <= names


@pytest.mark.parametrize("path", browser_files(), ids=lambda p: p.name)
def test_every_browser_test_file_is_watched(path):
    rel = path.relative_to(ROOT).as_posix()
    assert watch_pattern().search(rel), f"{rel} is not on the browser-tests watch list"


@pytest.mark.parametrize("path", browser_files(), ids=lambda p: p.name)
def test_every_source_a_browser_test_imports_or_launches_is_watched(path):
    pattern = watch_pattern()
    missing = sorted(src for src in project_sources(path) if not pattern.search(src))
    assert missing == [], f"{path.name} uses files off the browser-tests watch list: {missing}"


def test_the_source_finder_follows_imports_transitively():
    found = project_sources(ROOT / "tests" / "browser_app.py")
    # browser_app.py -> dashboard/auth_gate.py -> secrets_bridge -> mock_hsm/auth.py
    assert {"dashboard/secrets_bridge.py", "dashboard/session.py", "mock_hsm/auth.py", "mock_hsm/embedded.py"} <= found


def test_the_source_finder_sees_imports_and_launched_scripts():
    found = project_sources(ROOT / "tests" / "browser_app.py")
    assert {"dashboard/auth_gate.py", "dashboard/app.py"} <= found
    found = project_sources(ROOT / "tests" / "test_postdeploy_browser.py")
    assert {"scripts/postdeploy_check.py", "tests/browser_app.py", "dashboard/markers.py"} <= found


# ------------------------------------------------------- perf and browser
def _marks(decorators):
    names = set()
    for node in decorators:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Attribute) and sub.value.attr == "mark":
                names.add(sub.attr)
    return names


def doubly_marked(source):
    """Tests in ``source`` that carry both `perf` and `browser`, counting
    module-level ``pytestmark`` and class decorators."""
    tree = ast.parse(source)
    module = _marks(n.value for n in tree.body if isinstance(n, ast.Assign) and _is_pytestmark(n))
    clashes = []

    def visit(body, inherited):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, inherited | _marks(node.decorator_list))
            elif (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test")
                and {"perf", "browser"} <= inherited | _marks(node.decorator_list)
            ):
                clashes.append(node.name)

    visit(tree.body, module)
    return clashes


def _is_pytestmark(node):
    return any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)


def test_the_mark_check_finds_a_test_marked_both_ways():
    source = "import pytest\npytestmark = pytest.mark.browser\n@pytest.mark.perf\ndef test_x():\n    pass\n"
    assert doubly_marked(source) == ["test_x"]


def test_no_test_is_both_perf_and_browser():
    clashes = {p.name: doubly_marked(p.read_text()) for p in sorted((ROOT / "tests").glob("test_*.py"))}
    assert {name: tests for name, tests in clashes.items() if tests} == {}
