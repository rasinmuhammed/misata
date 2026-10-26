"""Each use-case recipe's page shows the files it runs, as they are."""

import re
from pathlib import Path

import pytest

RECIPES = sorted(p for p in (Path(__file__).parent.parent / "examples" / "usecases").iterdir()
                 if (p / "README.md").is_file())
SCHEMA_FILES = ("misata.yaml", "schema.sql", "course.yaml")
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)


def test_there_are_twelve_recipes():
    assert len(RECIPES) == 12


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_the_page_shows_its_schema_verbatim(recipe):
    page = (recipe / "README.md").read_text(encoding="utf-8")
    blocks = FENCE.findall(page)
    schemas = [recipe / name for name in SCHEMA_FILES if (recipe / name).is_file()]
    assert schemas, f"{recipe.name} ships no schema file"
    for schema in schemas:
        text = schema.read_text(encoding="utf-8")
        assert any(block.strip() == text.strip() for block in blocks), (
            f"{recipe.name}/README.md does not show {schema.name} as it is")


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_the_page_has_metadata_and_ends_with_a_check(recipe):
    page = (recipe / "README.md").read_text(encoding="utf-8")
    front = re.match(r"---\ntitle: (.+)\ndescription: (.+)\n---\n", page)
    assert front, f"{recipe.name}: missing title/description front matter"
    assert 50 <= len(front.group(2)) <= 300
    assert "## The check" in page
    assert "—" not in page, "no em dashes"
