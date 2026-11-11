# Hydra Tangler

VS Code client for the Hydra Tangler language server. The extension starts `hydra serve` over stdio and shows its status. Tangling, checks, diagnostics, hover, definition, and completion all live in `hydra serve`.

The client attaches to Markdown files in the first workspace folder. Saving a Markdown file tangles outputs only when `hydra.write` is on.

## Build

From the `hydra-tangler` directory:

```sh
cd ide-extension && uv run --project .. npm install
uv run --project .. npm run build
uv run --project .. npm test
uv run --project .. npm run package
```

`package` writes `hydra-tangler-0.1.0.vsix`.

## Install

In VS Code, run **Extensions: Install from VSIX…** and choose that file. `uv` must be on `PATH` for the default server command. The workspace should be the project `hydra serve` will tangle.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `hydra.serverCommand` | `[]` | Command and arguments that start the server. Empty uses `uv run --project <workspace> hydra serve`. The working directory is the first workspace folder. |
| `hydra.write` | `false` | When true, a save tangles into the build directory. |
| `hydra.pyrightCommand` | `[]` | Command and arguments for the basedpyright checker, sent as `pyrightCommand`. Empty uses `uv run --project <workspace> basedpyright --outputjson`. |
| `hydra.pyrightServerCommand` | `[]` | Command and arguments for the basedpyright language server, sent as `pyrightServerCommand`. Empty uses `uv run --project <workspace> basedpyright-langserver --stdio`. |
| `hydra.ruffCommand` | `[]` | Command and arguments for the ruff checker, sent as `ruffCommand`. Empty uses `uv run --project <workspace> ruff check --output-format json`. |
| `hydra.trace.server` | `off` | Trace traffic with the language server: `off`, `messages`, or `verbose`. |

A command that is present but not a list of non-empty strings is rejected; the server keeps that command's default and reports `bad-checker-command`. Changing `hydra.serverCommand`, `hydra.write`, `hydra.pyrightCommand`, `hydra.pyrightServerCommand`, or `hydra.ruffCommand` restarts the server. **Hydra: Rebuild** asks the running server to rebuild now. **Hydra: Restart Server** starts it again. The status bar shows `Hydra` while idle with no diagnostics, `Hydra: N errors, M warnings` when there are diagnostics, and a spinner while a rebuild is in progress. Click the status item to rebuild.
