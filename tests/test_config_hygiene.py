import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_contains_no_realistic_api_key():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"(?:gsk_|sk-)[A-Za-z0-9_-]{20,}", example) is None


def test_env_file_is_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in {line.strip() for line in gitignore.splitlines()}
