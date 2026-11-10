""" Wire the Hydra language server to stdio.

Feature handlers update the session and return. They do not rebuild
inline, and they do not parse Markdown. Navigation queries run on a
worker thread so a basedpyright round trip does not block the loop.
"""

import asyncio
from typing import final

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from hydra_tangler.check.lint import Runner
from hydra_tangler.serve.session import Session
from hydra_tangler.serve.status import HYDRA_REBUILD, status_payload


@final
class HydraLanguageServer(LanguageServer):
    """ Pygls server for one Hydra workspace. """

    def __init__(self, run: Runner | None = None) -> None:
        # pygls leaves ``*args`` untyped, so the checker marks this
        # constructor partially unknown without the ignore.
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            "hydra-tangler",
            "0.1.0",
            text_document_sync_kind=types.TextDocumentSyncKind.Full,
        )
        self.session = Session(self, run)


def create_server(run: Runner | None = None) -> HydraLanguageServer:
    """ Build a server. ``run`` replaces the lint subprocess for tests. """
    server = HydraLanguageServer(run)
    _register(server)
    return server


def run_stdio() -> None:
    """ Serve on standard input and output until the client exits. """
    create_server().start_io()


def _register(server: HydraLanguageServer) -> None:
    _ = server.feature(types.INITIALIZE)(_initialize)
    _ = server.feature(types.TEXT_DOCUMENT_DID_OPEN)(_opened)
    _ = server.feature(types.TEXT_DOCUMENT_DID_CHANGE)(_changed)
    save = types.SaveOptions(include_text=True)
    _ = server.feature(types.TEXT_DOCUMENT_DID_SAVE, save)(_saved)
    _ = server.feature(types.TEXT_DOCUMENT_DID_CLOSE)(_closed)
    _ = server.feature(types.SHUTDOWN)(_shutdown)
    _ = server.feature(HYDRA_REBUILD)(_rebuild)
    _ = server.feature(types.TEXT_DOCUMENT_HOVER)(_hover)
    _ = server.feature(types.TEXT_DOCUMENT_DEFINITION)(_definition)
    triggers = types.CompletionOptions(trigger_characters=[".", "("])
    _ = server.feature(types.TEXT_DOCUMENT_COMPLETION, triggers)(_completion)


def _initialize(
    server: HydraLanguageServer,
    params: types.InitializeParams,
) -> None:
    server.session.configure(params.initialization_options)


def _opened(
    server: HydraLanguageServer,
    params: types.DidOpenTextDocumentParams,
) -> None:
    document = params.text_document
    server.session.open_document(document.uri, document.text)


def _changed(
    server: HydraLanguageServer,
    params: types.DidChangeTextDocumentParams,
) -> None:
    uri = params.text_document.uri
    server.session.change_document(uri, _source(server, uri))


def _saved(
    server: HydraLanguageServer,
    params: types.DidSaveTextDocumentParams,
) -> None:
    uri = params.text_document.uri
    text = params.text
    if text is None:
        text = _source(server, uri)
    server.session.save_document(uri, text)


def _closed(
    server: HydraLanguageServer,
    params: types.DidCloseTextDocumentParams,
) -> None:
    server.session.close_document(params.text_document.uri)


async def _shutdown(server: HydraLanguageServer, params: object | None) -> None:
    """ Stop the rebuild loop before the process exits. """
    _ = params
    await server.session.stop()


async def _rebuild(
    server: HydraLanguageServer,
    params: object | None,
) -> dict[str, str | int]:
    """ Force a rebuild and return the idle status it published. """
    _ = params
    return status_payload(await server.session.rebuild())


async def _hover(
    server: HydraLanguageServer,
    params: types.HoverParams,
) -> types.Hover | None:
    spot = params.position
    return await asyncio.to_thread(
        server.session.hover,
        params.text_document.uri,
        spot.line,
        spot.character,
    )


async def _definition(
    server: HydraLanguageServer,
    params: types.DefinitionParams,
) -> list[types.Location] | None:
    spot = params.position
    return await asyncio.to_thread(
        server.session.definition,
        params.text_document.uri,
        spot.line,
        spot.character,
    )


async def _completion(
    server: HydraLanguageServer,
    params: types.CompletionParams,
) -> types.CompletionList | None:
    spot = params.position
    return await asyncio.to_thread(
        server.session.completion,
        params.text_document.uri,
        spot.line,
        spot.character,
    )


def _source(server: HydraLanguageServer, uri: str) -> str:
    return server.workspace.get_text_document(uri).source
