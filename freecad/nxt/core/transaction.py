"""One undo step for a block of document changes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def transaction(doc: Any, name: str) -> Iterator[None]:
    """Commit the block's changes as `name`, or abort them if it raises."""
    doc.openTransaction(name)
    try:
        yield
    except BaseException:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
