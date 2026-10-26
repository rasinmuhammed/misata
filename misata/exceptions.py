"""
Custom exceptions for Misata.

Provides a hierarchy of exception classes for better error handling
and more informative error messages.
"""

import os
import sys
import warnings
from typing import Any, Dict, List, Optional, Type

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep


class MisataError(Exception):
    """Base exception for all Misata errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class MisataWarning(UserWarning):
    """Base category for every warning Misata emits.

    On its own it marks advice that leaves every declaration intact: a
    provider retry, an inferred relationship that was dropped, an optional
    dependency that is missing. ``warnings.simplefilter("error",
    misata.MisataWarning)`` turns all of them into exceptions.
    """


class ConformanceWarning(MisataWarning):
    """Part of what was declared will not hold exactly as written.

    The declaration was skipped, met only partly, or met at a cost to another
    one: a period total that needs more rows than ``max_transactions_per_period``
    allows keeps its total and changes the row size; a share that cannot fit a
    column's bounds holds and pushes rows past them. The message names the
    declaration and what happened to it.
    ``warnings.simplefilter("error", misata.ConformanceWarning)`` is the
    setting for CI that should only fail on these.
    """


def warn(message: str, category: Type[MisataWarning] = MisataWarning) -> None:
    """Emit a Misata warning attributed to the first frame outside the package.

    Generation runs several layers deep, so a fixed ``stacklevel`` would name
    an engine module. Walking out of the package names the user's own call to
    ``generate`` or ``generate_from_schema`` instead, which is the line a
    warning filter or a traceback should point at.
    """
    level = 2
    frame = sys._getframe(1)
    while frame.f_back is not None and frame.f_code.co_filename.startswith(_PACKAGE_DIR):
        frame = frame.f_back
        level += 1
    warnings.warn(message, category, stacklevel=level)


# ============ Schema Errors ============

class SchemaError(MisataError):
    """Base class for schema-related errors."""
    pass


class SchemaValidationError(SchemaError):
    """Raised when schema validation fails."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        suggestion: Optional[str] = None,
    ):
        self.field = field
        self.value = value
        self.suggestion = suggestion
        details: Dict[str, Any] = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate long values
        if suggestion:
            details["suggestion"] = suggestion
        super().__init__(message, details)
    
    def __str__(self) -> str:
        msg = self.message
        if self.field:
            msg = f"[{self.field}] {msg}"
        if self.suggestion:
            msg += f"\n  → Suggestion: {self.suggestion}"
        return msg


class SchemaParseError(SchemaError):
    """Raised when schema parsing fails (YAML, JSON, etc.)."""
    
    def __init__(self, message: str, source: Optional[str] = None, line: Optional[int] = None):
        self.source = source
        self.line = line
        details: Dict[str, Any] = {}
        if source:
            details["source"] = source
        if line:
            details["line"] = line
        super().__init__(message, details)


class RelationshipError(SchemaError):
    """Raised when relationship definition is invalid."""
    
    def __init__(
        self,
        message: str,
        parent_table: Optional[str] = None,
        child_table: Optional[str] = None,
    ):
        self.parent_table = parent_table
        self.child_table = child_table
        details: Dict[str, Any] = {}
        if parent_table:
            details["parent_table"] = parent_table
        if child_table:
            details["child_table"] = child_table
        super().__init__(message, details)


# ============ Generation Errors ============

class GenerationError(MisataError):
    """Base class for data generation errors."""
    pass


class ColumnGenerationError(GenerationError):
    """Raised when column generation fails."""
    
    def __init__(
        self,
        message: str,
        table: Optional[str] = None,
        column: Optional[str] = None,
        column_type: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        self.table = table
        self.column = column
        self.column_type = column_type
        self.suggestion = suggestion
        details: Dict[str, Any] = {}
        if table:
            details["table"] = table
        if column:
            details["column"] = column
        if column_type:
            details["column_type"] = column_type
        super().__init__(message, details)
    
    def __str__(self) -> str:
        location = ""
        if self.table and self.column:
            location = f"[{self.table}.{self.column}] "
        elif self.table:
            location = f"[{self.table}] "
        msg = f"{location}{self.message}"
        if self.suggestion:
            msg += f"\n  → Suggestion: {self.suggestion}"
        return msg


class ConstraintError(GenerationError):
    """Raised when constraint application fails."""
    
    def __init__(
        self,
        message: str,
        constraint_type: Optional[str] = None,
        affected_columns: Optional[List[str]] = None,
    ):
        self.constraint_type = constraint_type
        self.affected_columns = affected_columns or []
        details: Dict[str, Any] = {}
        if constraint_type:
            details["constraint_type"] = constraint_type
        if affected_columns:
            details["affected_columns"] = affected_columns
        super().__init__(message, details)


class CircularDependencyError(GenerationError):
    """Raised when circular dependencies are detected in table relationships."""
    
    def __init__(self, message: str, tables: Optional[List[str]] = None):
        self.tables = tables or []
        details = {"tables": tables} if tables else {}
        super().__init__(message, details)


class ReferentialIntegrityError(GenerationError):
    """Raised when foreign key references cannot be satisfied."""
    
    def __init__(
        self,
        message: str,
        parent_table: Optional[str] = None,
        child_table: Optional[str] = None,
        missing_ids: Optional[int] = None,
    ):
        self.parent_table = parent_table
        self.child_table = child_table
        self.missing_ids = missing_ids
        details: Dict[str, Any] = {}
        if parent_table:
            details["parent_table"] = parent_table
        if child_table:
            details["child_table"] = child_table
        if missing_ids:
            details["missing_ids"] = missing_ids
        super().__init__(message, details)


# ============ LLM Errors ============

class LLMError(MisataError):
    """Base class for LLM-related errors."""
    pass


class LLMConnectionError(LLMError):
    """Raised when LLM API connection fails."""
    
    def __init__(self, message: str, provider: Optional[str] = None):
        self.provider = provider
        details = {"provider": provider} if provider else {}
        super().__init__(message, details)


class LLMParseError(LLMError):
    """Raised when LLM response cannot be parsed."""
    
    def __init__(self, message: str, raw_response: Optional[str] = None):
        self.raw_response = raw_response[:500] if raw_response else None
        details: Dict[str, Any] = {}
        if self.raw_response:
            details["raw_response_preview"] = self.raw_response
        super().__init__(message, details)


class LLMQuotaError(LLMError):
    """Raised when LLM API quota is exceeded."""
    
    def __init__(self, message: str, provider: Optional[str] = None, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        details: Dict[str, Any] = {}
        if provider:
            details["provider"] = provider
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, details)


# ============ Configuration Errors ============

class ConfigurationError(MisataError):
    """Raised when configuration is invalid."""
    pass


class MissingAPIKeyError(ConfigurationError):
    """Raised when required API key is missing."""
    
    def __init__(self, provider: str, env_var: str):
        self.provider = provider
        self.env_var = env_var
        message = f"API key for {provider} not found"
        suggestion = f"Set {env_var} environment variable or pass api_key parameter"
        details = {"provider": provider, "env_var": env_var, "suggestion": suggestion}
        super().__init__(message, details)


# ============ Export Errors ============

class ExportError(MisataError):
    """Base class for export-related errors."""
    pass


class FileWriteError(ExportError):
    """Raised when file writing fails."""
    
    def __init__(self, message: str, path: Optional[str] = None):
        self.path = path
        details = {"path": path} if path else {}
        super().__init__(message, details)


class InvalidOutputFormatError(ExportError):
    """Raised when export format is not supported."""
    
    def __init__(self, format: str, supported_formats: Optional[List[str]] = None):
        self.format = format
        self.supported_formats = supported_formats or ["csv", "parquet", "json"]
        message = f"Unsupported export format: {format}"
        details = {
            "format": format,
            "supported_formats": self.supported_formats,
        }
        super().__init__(message, details)
