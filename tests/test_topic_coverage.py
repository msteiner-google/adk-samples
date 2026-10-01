"""Checks that the topic-coverage map still describes the repository.

A map claiming a topic is covered by a file that no longer exists is worse
than no map: it answers the question wrongly and confidently. This extracts
every repo path mentioned in the docs and asserts it exists, which is the
part that can be checked mechanically.

It cannot check that a file does what the map says it does. That still needs
a reader.

`docs/delivery-log.md` is deliberately not checked. It is a record of what
each PR changed, so it legitimately names things that were deleted, and
pinning it to the current tree would force a historical document to be
rewritten whenever the present moves. Its paths were verified once, when it
was written.
"""

import pathlib
import re

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = PROJECT_ROOT / "docs"

COVERAGE_MAP = DOCS / "topic-coverage.md"
TOPICS = DOCS / "topics.md"
PATTERNS = DOCS / "patterns" / "nl2sql.md"

#: Backtick-quoted spans that look like a repo path: they contain a slash and
#: start with a known top-level directory, or they end in a source extension.
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_TOP_LEVEL = ("src/", "tests/", "scripts/", "data/", "docs/", ".github/")
_SOURCE_SUFFIXES = (".py", ".json", ".sql", ".md", ".yml", ".toml")

#: Paths written with a glob, which cannot be checked by existence.
_GLOB = re.compile(r"[*?\[\]]")


def documented_paths(document: pathlib.Path) -> set[str]:
    """Returns the repo paths a document mentions in backticks."""
    found = set()
    for span in _INLINE_CODE.findall(document.read_text(encoding="utf-8")):
        candidate = span.strip()
        if _GLOB.search(candidate) or " " in candidate:
            continue
        if candidate.startswith(_TOP_LEVEL) or (
            "/" in candidate and candidate.endswith(_SOURCE_SUFFIXES)
        ):
            found.add(candidate.rstrip("/"))
    return found


@pytest.mark.parametrize("document", [COVERAGE_MAP, TOPICS, PATTERNS])
def test_documented_paths_exist(document: pathlib.Path):
    """Every path a doc points at must resolve."""
    missing = sorted(
        path
        for path in documented_paths(document)
        if not (PROJECT_ROOT / path).exists()
    )
    assert missing == [], f"{document.name} references missing paths: {missing}"


def test_coverage_map_mentions_every_topic():
    """A new topic added upstream must not go unmapped."""
    topics = re.findall(r"^### (Topic \d+):", TOPICS.read_text(encoding="utf-8"), re.M)
    assert topics, "no topics parsed from topics.md"

    coverage = COVERAGE_MAP.read_text(encoding="utf-8")
    missing = [t for t in topics if t.split(":")[0].replace("Topic ", "") not in
               re.findall(r"^## Topic (\d+):", coverage, re.M)]
    assert missing == [], f"topic-coverage.md does not cover: {missing}"


def test_coverage_map_lists_every_final_deliverable():
    """The four named deliverables are what the project is judged on."""
    coverage = COVERAGE_MAP.read_text(encoding="utf-8")
    for deliverable in (
        "Prompt Evolution Engine",
        "Metrics Library",
        "NL2SQL Template",
        "Cost Analysis Framework",
    ):
        assert deliverable in coverage, deliverable


def test_coverage_map_is_honest_about_what_has_run():
    """The evidence section is the part most likely to be quietly dropped.

    It is also the part a reader most needs, so its absence should break
    the build rather than go unnoticed.
    """
    coverage = COVERAGE_MAP.read_text(encoding="utf-8")
    assert "## What has actually run" in coverage
    assert "## Known gaps" in coverage


def test_every_make_target_in_the_docs_exists():
    """A documented command that does not run is a broken promise."""
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    defined = set(re.findall(r"^([a-z0-9][a-z0-9-]*):", makefile, re.M))

    documented = set()
    for document in (COVERAGE_MAP, PROJECT_ROOT / "README.md", PATTERNS):
        text = document.read_text(encoding="utf-8")
        documented.update(re.findall(r"`make ([a-z0-9-]+)", text))
        documented.update(re.findall(r"^\s*make ([a-z0-9-]+)", text, re.M))

    assert documented, "no make targets found in the docs"
    assert documented <= defined, f"documented but undefined: {documented - defined}"
