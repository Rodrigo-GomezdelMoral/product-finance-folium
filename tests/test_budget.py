import ast
import io
import ipaddress
import re
import subprocess
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = ("docs/", "data/", "eval/datasets/", "web/node_modules/", "web/src/demo/runs/")
LOCK_FILES = ("package-lock.json",)
APP = ("app/", "eval/", "load/", "ops/")
LIMITS = {"files": 90, "python": 1400, "tests": 700, "bicep": 490, "typescript": 799, "comments": 5}
HASH_FILES = (".yml", ".yaml", ".toml", ".txt", ".sh", "Dockerfile", "Makefile")
HASH_COMMENT = re.compile(r"(?:^|\s)#(?!!)")
ACTION_PIN = re.compile(r"uses: \S+@[0-9a-f]{40} # v\d[\w.]*$")
BLIND = {"Exception", "BaseException"}
IDENTIFIERS = {
    "GUID": re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", re.IGNORECASE),
    "e-mail address": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.IGNORECASE),
    "Azure hostname": re.compile(
        r"[\w-]+\.(?:azurecontainerapps\.io|azurecr\.io|(?:services\.ai|cognitiveservices|openai|documents|vault"
        r"|applicationinsights)\.azure\.(?:com|net)|(?:(?:blob|queue|table|file|dfs)\.core|servicebus)\.windows\.net)",
        re.IGNORECASE,
    ),
    "tenant domain": re.compile(r"[\w-]+\.onmicrosoft\.com", re.IGNORECASE),
    "local user path": re.compile(r"[a-z]:[\\/]+users[\\/]+\w", re.IGNORECASE),
}
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def listed() -> list[str]:
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    names = subprocess.run(command, capture_output=True, text=True, check=True, cwd=ROOT).stdout.splitlines()
    return [name for name in names if (ROOT / name).is_file()]


def budgeted() -> list[str]:
    return [name for name in listed() if not name.startswith(EXCLUDED) and Path(name).name not in LOCK_FILES]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def non_blank(names: list[str]) -> int:
    return sum(1 for name in names for line in read(name).splitlines() if line.strip())


def comments(name: str) -> int:
    if name.endswith(".py"):
        tokens = tokenize.generate_tokens(io.StringIO(read(name)).readline)
        return sum(1 for token in tokens if token.type == tokenize.COMMENT)
    if name.endswith(HASH_FILES):
        return sum(1 for line in read(name).splitlines() if HASH_COMMENT.search(line) and not ACTION_PIN.search(line))
    return 0


def budget_counts() -> dict[str, int]:
    files = budgeted()
    python = [name for name in files if name.endswith(".py")]
    return {
        "files": len(files),
        "python": non_blank([name for name in python if name.startswith(APP)]),
        "tests": non_blank([name for name in python if name.startswith("tests/")]),
        "bicep": non_blank([name for name in files if name.endswith((".bicep", ".bicepparam"))]),
        "typescript": non_blank([name for name in files if name.endswith((".ts", ".tsx"))]),
        "comments": sum(comments(name) for name in files),
    }


def is_public_ip(candidate: str) -> bool:
    try:
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False


def test_budget() -> None:
    over = {name: count for name, count in budget_counts().items() if count > LIMITS[name]}
    assert not over, f"over budget: {over}"


def test_no_blind_except() -> None:
    for name in (name for name in budgeted() if name.endswith(".py")):
        for node in ast.walk(ast.parse(read(name))):
            if isinstance(node, ast.ExceptHandler):
                blind = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in BLIND)
                assert not blind, f"{name}:{node.lineno} catches everything"


def test_no_identifiers() -> None:
    found: list[str] = []
    for name in listed():
        raw = (ROOT / name).read_bytes()
        try:
            content = "" if b"\0" in raw else raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        found += [f"{name}: {kind}" for kind, pattern in IDENTIFIERS.items() if pattern.search(content)]
        found += [f"{name}: public IP address" for match in IPV4.findall(content) if is_public_ip(match)]
    assert not found, found


def test_supply_chain_is_pinned() -> None:
    for requirements in ("requirements.txt", "requirements-dev.txt"):
        for pin in (pin for pin in read(requirements).splitlines() if pin and not pin.startswith("-r")):
            assert re.fullmatch(r"[\w.-]+==[\w.]+", pin), f"{requirements}: {pin} is not pinned"
            assert not pin.startswith("agent-framework=="), "the agent-framework metapackage is not allowed"
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "uses:" in line and "uses: ./" not in line:
                assert ACTION_PIN.search(line), f"{workflow.name}: {line.strip()} is not pinned to a commit SHA"
    images = [line for line in read("Dockerfile").splitlines() if line.startswith("FROM ")]
    assert images and all("@sha256:" in line for line in images), "base images must be pinned by digest"
