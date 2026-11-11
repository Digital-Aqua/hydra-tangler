# Hydra Tangler

Literate programming in Markdown.

> TODO proper readme (incorporating notes below)

---

Assorted notes (as a guide ONLY):

## VSCode/Cursor Installation (Dev Mode)

To install the extension to VSCode in dev mode, run the following commands:

```bash
cd ide-extension
uv run npm install
uv run npm run build
mkdir -p "$HOME/.vscode/extensions"
ln -sfn "$(pwd)" "$HOME/.vscode/extensions/digital-aqua.hydra-tangler-0.1.0"
```

- Reload the IDE after linking or rebuilding.
- `uv` must be on `PATH`.
- For Cursor, replace `.vscode` with `.cursor`.


## Example

Input:
`my-project/index.md`:
```markdown
# My Project

```python file=hello.py&nbsp;
print("Hello, World!")
```&nbsp;
```

Command:
```bash
my-project/$ hydra tangle
```

Outputs:
`my-project/_build/hello.py`:
```python
print("Hello, World!")
```
`my-project/_build/docs/index.html`:
```html
...
<h1>My Project</h1>
<pre><code>print("Hello, World!")</code></pre>
...
```

# CLI

| Command | Description |
|---------|-------------|
| `hydra tangle [--output=<output>]... [<source> [<target>]]` | Tangle Markdown in the source directory. |
| `hydra watch [--output=<output>]... [<source> [<target>]]` | Re-tangle when Markdown under the source directory changes. |
| `hydra check [--pyright-command=<argv>] [--ruff-command=<argv>] [<source>]` | Report dead links and lint findings. |

`<source>` defaults to `./` (the working directory). There is no config file.
`<target>` defaults to `./_build`. A fence `file=mypackage/myfile.py` is written to `_build/mypackage/myfile.py`. HTML docs land under `_build/docs/`. The combined source map is `_build/sourcemap.json` (skip it with `--no-sourcemap`).
`--output` may be repeated. With none given, every registered output runs.
`--pyright-command` and `--ruff-command` are shell-style argument strings. When omitted, each checker runs as `uv run --project <root> ...`.

## No Bootstrapping

Hydra is not written in literate style. Don't suggest bootstrapping `hydra` with `hydra` - my brain can't handle the recursion.

## TODOs

> TODO: hydra self-contained executable
> TODO: 

