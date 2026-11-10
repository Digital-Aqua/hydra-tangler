""" HTML documentation: one static page per Markdown document.

Registered as the ``htmldocs`` output. Returns a FileSet and does not
write the output directory, tangle code, or check links.
"""

from hydra_tangler.model import Book
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.outputs.htmldocs.site import render_book


class HtmlDocsOutput:
    """ The ``htmldocs`` output: a static site for a book. """

    name: str = "htmldocs"

    def render(self, book: Book) -> Rendered:
        """ Return the site pages, stylesheet, and an empty source map. """
        return render_book(book)


output = HtmlDocsOutput()
