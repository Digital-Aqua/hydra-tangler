# Hydra Tangler: design brief

Hydra turns Markdown files into code and docs. Fences tagged `file=<path>`
are concatenated into output files. A source map records which Markdown
line produced each output line. This file is the contract between the
modules. Read it before changing any of them.

Hydra is NOT written in literate style. It knows nothing about Auriga.

## Environment

- All commands run through uv: `uv run pytest`, `uv run ruff check`,
  `uv run basedpyright`, `uv run hydra ...`. Node: `uv run npm ...`.
- Python 3.14. Source is in `src/hydra_tangler/`, tests in `tests/`.
- Reference implementation (behaviour only, do NOT copy its structure):
  `/home/aaron/Documents/Code/Digital Aqua/Projects/AurigaProto1/scripts/tangle.py`
  `/home/aaron/Documents/Code/Digital Aqua/Projects/AurigaProto1/scripts/htmldocs.py`
  and its tests in `.../AurigaProto1/tests/auriga-lit/`.

## Layers (dependencies point downward only)

```
main.py              Typer CLI: tangle | watch | check | where | serve
serve/               LSP server (pygls)
check/               lint + link checks -> Diagnostics
outputs/             Book -> FileSet   (python.py, htmldocs.py)
fences/              what a fence means (python.py, pytest.py)
book.py              discover + order + assemble the Book
sourcemap.py         output line <-> Markdown line
parse.py             Markdown text -> Document (markdown-it-py tokens)
model.py             plain dataclasses shared by all layers
config.py            [tool.hydra] in pyproject.toml
```

## Core types (`model.py`)

- `Fence(path, info, language, attrs, body_lines, open_line, body_line)`
  Lines are 1-based Markdown line numbers.
- `Link(path, line, target, text)` and `Heading(path, line, level, slug)`.
- `Document(path, fences, headings, links)`: one parsed Markdown file.
- `Diagnostic(path, line, severity, code, message)`: the one type for
  tangle errors, link warnings, and lint findings. Severity is
  `error | warning`.
- `FileSet`: mapping of relative output path to bytes. Pure data.
- `Book(root, documents, ...)`: all documents in order.

## Rules of the design

- Parsing does no file I/O. Discovery reads files. Outputs return a
  `FileSet`. Only `writer.py` touches the output directory.
- Ordering of documents is alphabetical by relative path. No index
  files, no numbered-name parsing. Ordering is a replaceable function.
- The writer skips files whose bytes are unchanged and removes stale
  files that a previous run produced. It never rewrites identical files
  (a watcher must not retrigger itself).
- Fence handlers and outputs are discovered through entry points in
  the groups `hydra_tangler.fences` and `hydra_tangler.outputs`, with
  built-ins registered the same way, so external packages can add more.
- Source dir default: `./src`, then `./source`, then `./`. Target
  default: `./_build/<output>/`. `--output` selects outputs.
- The heading slug function lives in one place and is used by both
  link checking and htmldocs.
- Link checking: relative links to a missing file, or to a missing
  anchor in an existing file, are `warning` diagnostics with
  code `dead-link`.

## Code style (every contributor, human or model)

- Each function does one thing, fits on one screen (about 30 lines),
  and has a name that says what it does. Avoid more than 3 levels of
  nesting; use early returns.
- Every module starts with a docstring saying what it is for and what
  it does NOT do. Public classes and functions have docstrings that
  state purpose, not restate the signature.
- Use dataclasses (frozen where possible) and Protocols for structure.
  No dicts or tuples passed around where a named type belongs.
- Full type annotations. `basedpyright` and `ruff` must pass clean.
- No dead code, no compatibility shims, no speculative options, no
  broad `except Exception`, no clever one-liners, no god modules.
- Comments explain why, not what.
- Tests: pytest, small fixture books written to `tmp_path`, snapshots
  with syrupy where output is large.
