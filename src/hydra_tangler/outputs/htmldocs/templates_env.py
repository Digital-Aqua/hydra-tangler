""" Jinja environment for the HTML docs templates.

Templates live in this package. Callers pass context objects and
receive a string. This module does not decide page content.
"""

from functools import lru_cache

from jinja2 import Environment, PackageLoader, StrictUndefined


@lru_cache(maxsize=1)
def environment() -> Environment:
    """ Return the shared autoescaping environment. """
    return Environment(
        loader=PackageLoader("hydra_tangler.outputs.htmldocs", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(name: str, **context: object) -> str:
    """ Render one template with ``context``. """
    return environment().get_template(name).render(**context)
