from __future__ import annotations

"""Shared loader error utilities."""

import os
from typing import Iterable, Optional

from pydantic import ValidationError


class LoaderError(RuntimeError):
    """Wraps loader failures with file path context."""

    def __init__(self, file_path: str, message: str, *, cause: Exception | None = None):
        self.file_path = file_path
        self.message = message
        self.cause = cause
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        path = self._relative_path(self.file_path)
        base = f"{self.message} ({path})"
        if isinstance(self.cause, ValidationError):
            detail = self._format_validation_errors(self.cause.errors())
            return f"{base}: {detail}"
        if self.cause:
            return f"{base}: {self.cause}"
        return base

    @staticmethod
    def _relative_path(path: str) -> str:
        try:
            return os.path.relpath(path)
        except Exception:  # pragma: no cover
            return path

    @staticmethod
    def _format_validation_errors(errors: Iterable[dict]) -> str:
        error_list = list(errors)
        snippets = []
        for err in error_list:
            loc = ".".join(str(entry) for entry in err.get("loc", [])) or "<root>"
            msg = err.get("msg") or err.get("type") or "validation error"
            snippets.append(f"{loc}: {msg}")
            if len(snippets) >= 3:
                break
        remaining = len(error_list) - len(snippets)
        if remaining > 0:
            snippets.append(f"... ({remaining} more)")
        return "; ".join(snippets)

    def __str__(self) -> str:
        return self._build_message()
