"""galley turns the PDF of a mostly-text book into an EPUB.

gilguard is imported before anything else, so that any import that turns
the GIL back on raises gilguard.GILEnabledError at that import, naming the
module and the line, instead of letting galley run on one core with only a
warning. galley's per-page work relies on free-threaded Python.
"""

import gilguard  # noqa: F401  (must stay the first import of the package)
