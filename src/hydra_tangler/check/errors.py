""" Failures while running a checker.

Callers turn this into a command error. It is not a diagnostic:
the checker never produced findings to map.
"""


class LintError(Exception):
    """ A checker did not run, or its output was not JSON. """
