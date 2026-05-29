from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BaseLinter
from ..sql_completion import complete_sql
from ..sql_validator import validate_sql_advisory


class PostgresLinter(BaseLinter):
    stack = "greenplum"

    def validate(
        self,
        source_text: str,
        *,
        scenario: str,
        metadata_provider: Any = None,
    ) -> Dict[str, Any]:
        return validate_sql_advisory(source_text, metadata_provider=metadata_provider)

    def complete(
        self,
        source_text: str,
        cursor_index: int,
        *,
        scenario: str,
        conn_string: Optional[str] = None,
    ) -> Dict[str, Any]:
        return complete_sql(
            source_text,
            cursor_index,
            validation_mode=scenario,
            conn_string=conn_string,
        )
