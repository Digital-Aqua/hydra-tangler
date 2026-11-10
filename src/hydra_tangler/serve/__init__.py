""" Language server for Hydra Tangler.

The server keeps open Markdown buffers, rebuilds the book, and
publishes diagnostics. It does not tangle on its own schedule and
does not know about a particular editor.
"""
