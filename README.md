# Hydra Tangler

Literate programming in Markdown.

> TODO proper readme (incorporating notes below)

---

Assorted notes (as a guide ONLY):

## Installation

```bash

```


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
`my-project/_build/python/hello.py`:
```python
print("Hello, World!")
```
`my-project/_build/htmldocs/index.html`:
```html
...
<h1>My Project</h1>
<pre><code>print("Hello, World!")</code></pre>
...
```

# CLI

| Command | Description |
|---------|-------------|
| `hydra tangle [--output=<output>] [<source> [<target>]]` | Tangle all Markdown files in the source directory. |
| `hydra watch [--output=<output>] [<source> [<target>]]` | Watch for changes in the source directory and tangle the changed files. |

`<source>` defaults to `./src`, falls back to `./source`, then `./`.
`<target>` defaults to `./_build/<output/`.
`--output` can restrict to specific kinds of output (e.g. `python`, `htmldocs`).

## No Bootstrapping

Hydra is not written in literate style. Don't suggest bootstrapping `hydra` with `hydra` - my brain can't handle the recursion.

