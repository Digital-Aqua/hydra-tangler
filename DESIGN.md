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
mounting.py          mount outputs, merge files and maps, collisions
failures.py          the user-facing failure set (CLI and server)
outputs/             Book -> FileSet + SourceMap (files.py, htmldocs/)
fences/              fence classes: PlainText and thin subclasses
book.py              discover + order + assemble the Book
sourcemap.py         output line <-> Markdown line, sourcemap.json
parse.py             Markdown text -> Document (markdown-it-py tokens)
model.py             plain dataclasses shared by all layers
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
- Hydra never reads `pyproject.toml` or any config file. Source is the
  CLI argument or `./`; hidden directories, `_build`, `node_modules`
  and `__pycache__` are skipped. The target is one directory, default
  `./_build`, shared by every output. `--output` (repeatable) selects
  outputs.
- Each output has a `mount`: `files` is `.`, `htmldocs` is `docs`. The
  pipeline applies mounts, merges all outputs into one FileSet and one
  manifest, and writes `sourcemap.json` beside them. Two outputs
  claiming one path is an `output-collision` error.
- Source maps are not an output. Every output returns one with its
  files; the pipeline merges and serializes them.
- Fence classes: `PlainText` is the base (tag `text`, `#` comments);
  a language is a thin subclass that sets tags and comment markers.
  A subclass may set `exclusions`: a checker name plus that checker's
  rule codes that tangled fragments are not expected to satisfy. The
  lint pass for the language asks the checker to suppress them.
  Python drops ruff `I001` (import sorting). Add the next rule on the
  language class; teach a new checker how to spell the flag in
  `suppress`.
  Only `file=` fences are tangled. Per-fence attributes: `file`,
  `comment`, `comment_end`, `header=false`, `tangler=<tag>`. A
  `file=` fence with an unknown tag is an `unsupported-language`
  warning and is skipped. The `files` output has no language
  knowledge.
- Output paths stay inside the target: `vet_output_path` in `model.py`
  is the one rule, enforced by fences, `OutputFile`, mounts and the
  writer (which also refuses symlink escapes).
- Failures: problems in a book are Diagnostics. Missing tools, bad tool
  output, unreadable files and refused writes are exceptions listed in
  `failures.USER_FAILURES`; the CLI prints `error:` and exits 1, the
  server shows a message and keeps running.
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
