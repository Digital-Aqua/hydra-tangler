""" Parser behaviour: fences, headings, links, and unclosed fences. """

from pathlib import Path

from tests.books import fence

from hydra_tangler.parse import parse_document

FENCE = "`" * 3


def test_nested_backticks_stay_inside_the_outer_fence() -> None:
    text = (
        "intro\n"
        + fence("python file=a.py", "x = '''", FENCE, "'''", ticks=4)
        + fence("text", "plain")
    )
    parsed = parse_document(text, Path("c.md"))
    fences = parsed.document.fences
    assert parsed.diagnostics == ()
    assert len(fences) == 2
    assert fences[0].body_lines == ("x = '''", FENCE, "'''")
    assert fences[0].language == "python"
    assert fences[0].attrs["file"] == "a.py"
    assert fences[0].open_line == 2
    assert fences[0].body_line == 3
    assert fences[1].language == "text"
    assert "file" not in fences[1].attrs


def test_quoted_attributes_keep_spaces() -> None:
    text = fence("rust file=a.rs comment='// ' tangler=text", "fn main() {}")
    parsed = parse_document(text, Path("c.md"))
    attrs = parsed.document.fences[0].attrs
    assert parsed.diagnostics == ()
    assert attrs["file"] == "a.rs"
    assert attrs["comment"] == "// "
    assert attrs["tangler"] == "text"


def test_unbalanced_quote_skips_the_fence() -> None:
    text = fence("python file=m.py comment='//", "x = 1")
    parsed = parse_document(text, Path("c.md"))
    assert parsed.document.fences == ()
    problem = parsed.diagnostics[0]
    assert problem.code == "bad-fence-attrs"
    assert problem.severity == "warning"
    assert problem.line == 1


def test_unclosed_fence_is_a_diagnostic() -> None:
    parsed = parse_document(f"{FENCE}python\nx\n", Path("c.md"))
    assert len(parsed.diagnostics) == 1
    problem = parsed.diagnostics[0]
    assert problem.path == Path("c.md")
    assert problem.line == 1
    assert problem.severity == "error"
    assert problem.code == "unclosed-fence"
    assert parsed.document.fences[0].body_lines == ("x",)


def test_headings_and_links_keep_line_numbers_and_slugs() -> None:
    text = (
        "# Hello World\n\n"
        "See [Docs](guide.md#hello-world).\n\n"
        "## Hello World\n"
    )
    parsed = parse_document(text, Path("a.md"))
    headings = parsed.document.headings
    assert headings[0].line == 1
    assert headings[0].level == 1
    assert headings[0].slug == "hello-world"
    assert headings[1].slug == "hello-world-1"
    link = parsed.document.links[0]
    assert link.line == 3
    assert link.target == "guide.md#hello-world"
    assert link.text == "Docs"
