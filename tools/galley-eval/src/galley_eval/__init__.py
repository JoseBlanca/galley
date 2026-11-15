"""galley-eval compares galley's output for a book with the Project
Gutenberg edition made from the same scan (docs/specs/evaluation.md).

It is a development tool: galley never imports it. gilguard is imported
first, as in galley, so that an import that turns the GIL back on fails
at that import.
"""

import gilguard  # noqa: F401  (must stay the first import of the package)
