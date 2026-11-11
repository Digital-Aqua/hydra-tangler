""" One workspace's open files, options, and rebuild loop.

Handlers in the server call this. The blocking rebuild runs on the
server's thread pool. This module does not register LSP methods.
"""

import asyncio
from pathlib import Path
from typing import final

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path
from pygls.workspace import Workspace

from hydra_tangler.check.lint import Runner
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.pipeline import source_directory
from hydra_tangler.serve.analysis import Analysis, analyse
from hydra_tangler.serve.documents import DocumentStore
from hydra_tangler.serve.navigate import Navigation
from hydra_tangler.serve.options import ServeOptions, read_options
from hydra_tangler.serve.publish import DiagnosticPublisher
from hydra_tangler.serve.schedule import RebuildRequest, RebuildScheduler
from hydra_tangler.serve.status import (
    HYDRA_STATUS,
    StatusReport,
    status_payload,
)


@final
class Session:
    """ Track buffers and turn them into published diagnostics. """

    def __init__(self, server: LanguageServer, run: Runner | None) -> None:
        self._server = server
        self._run = run
        self._documents = DocumentStore()
        self._publisher = DiagnosticPublisher(server)
        self._options = ServeOptions()
        self._root: Path | None = None
        self._source: Path | None = None
        self._status = StatusReport("idle", 0, 0)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._navigation = Navigation(self._report, self._alert)
        self._scheduler = RebuildScheduler(
            self._perform,
            self._notify,
            self._alert,
        )

    def configure(self, options: object) -> None:
        """ Store the workspace root and initialization options. """
        self._options = read_options(options)
        self._loop = asyncio.get_running_loop()
        self._scheduler.start()
        for message in self._options.rejected:
            self._alert(message)
        root = _project_root(self._server.workspace)
        if root is None:
            self._alert("hydra serve needs a workspace root")
            return
        self._root = root
        self._navigation.bind(root, self._options.pyright_server)
        self._remember_source(root)

    def open_document(self, uri: str, text: str) -> None:
        """ Rebuild immediately from this open buffer. """
        self._edit(uri, text, immediate=True, write=False)

    def change_document(self, uri: str, text: str) -> None:
        """ Rebuild after the quiet period. """
        self._edit(uri, text, immediate=False, write=False)

    def save_document(self, uri: str, text: str) -> None:
        """ Rebuild immediately, and write outputs when asked. """
        self._edit(uri, text, immediate=True, write=self._options.write)

    def close_document(self, uri: str) -> None:
        """ Drop the buffer and rebuild from disk. """
        source = self._source
        if source is None:
            return
        if self._documents.forget(source, uri):
            _ = self._scheduler.request(immediate=True, write=False, wait=False)

    async def rebuild(self) -> StatusReport:
        """ Force a rebuild and wait until its result is published. """
        future = self._scheduler.request(
            immediate=True,
            write=False,
            wait=True,
        )
        if future is None:
            return self._status
        return await future

    def hover(self, uri: str, line: int, character: int) -> types.Hover | None:
        """ Hover, forwarded when the position is in a Python fence. """
        return self._navigation.hover(uri, line, character)

    def definition(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[types.Location] | None:
        """ Definition, forwarded when the position is in a Python fence. """
        return self._navigation.definition(uri, line, character)

    def completion(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> types.CompletionList | None:
        """ Completions, forwarded when the position is in a Python fence. """
        return self._navigation.completion(uri, line, character)

    async def stop(self) -> None:
        """ Stop accepting rebuilds and the pyright subprocess. """
        await self._scheduler.stop()
        await asyncio.to_thread(self._navigation.stop)

    def _edit(
        self,
        uri: str,
        text: str,
        *,
        immediate: bool,
        write: bool,
    ) -> None:
        source = self._source
        if source is None:
            return
        if not self._documents.remember(source, uri, text):
            return
        _ = self._scheduler.request(
            immediate=immediate,
            write=write,
            wait=False,
        )

    def _remember_source(self, root: Path) -> None:
        self._source = source_directory(root, None).resolve()

    async def _perform(self, job: RebuildRequest) -> StatusReport | None:
        root = self._root
        if root is None:
            return self._status
        analysis = await self._analyse(root, job)
        if job.started != self._scheduler.generation:
            return None
        return self._apply(analysis)

    async def _analyse(self, root: Path, job: RebuildRequest) -> Analysis:
        loop = asyncio.get_running_loop()
        # Copied here so the worker never reads the live buffer map.
        overlays = dict(self._documents.overrides())
        return await loop.run_in_executor(
            self._server.thread_pool,
            analyse,
            root,
            overlays,
            job.write,
            CheckerCommands(self._options.pyright, self._options.ruff),
            self._run,
        )

    def _apply(self, analysis: Analysis) -> StatusReport:
        if analysis.load_failure:
            self._alert(analysis.load_failure)
            return self._status
        if analysis.write_failure:
            self._alert(analysis.write_failure)
        if analysis.lint_failure:
            self._alert(analysis.lint_failure)
        report = self._publisher.publish(analysis, self._documents.uris())
        self._navigation.update(analysis.source, analysis.python)
        self._status = report
        return report

    def _notify(self, report: StatusReport) -> None:
        self._server.protocol.notify(HYDRA_STATUS, status_payload(report))

    def _report(self, message: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        _ = loop.call_soon_threadsafe(self._log, message)

    def _alert(self, message: str) -> None:
        self._log(message)
        self._server.window_show_message(
            types.ShowMessageParams(
                type=types.MessageType.Error,
                message=message,
            )
        )

    def _log(self, message: str) -> None:
        self._server.window_log_message(
            types.LogMessageParams(
                type=types.MessageType.Error,
                message=message,
            )
        )


def _project_root(workspace: Workspace) -> Path | None:
    raw = workspace.root_path
    if isinstance(raw, str) and raw:
        return Path(raw).resolve()
    for folder in workspace.folders.values():
        path = to_fs_path(folder.uri)
        if path:
            return Path(path).resolve()
    return None
