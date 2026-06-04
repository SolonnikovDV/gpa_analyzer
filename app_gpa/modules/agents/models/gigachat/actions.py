"""GigaChat SQL-generation and discovery actions.

Each function opens a short-lived GigaChatClient session, calls the GigaChat
API, and returns a plain dict.  No HTTP framework knowledge here.

Delegates token tracking and caching to gigachat_agent (legacy) while we
incrementally migrate; the goal is to make this file the single source of
truth for all "what to ask GigaChat" logic.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .client import GigaChatClient


# ---------------------------------------------------------------------------
# Public SQL actions
# ---------------------------------------------------------------------------

def generate_sql(
    source_text: str,
    *,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    stack: str = "greenplum",
    code_revision_pass: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Generate SQL/function from natural-language description.

    Delegates to gigachat_agent.generate_sql_with_review (compat layer)
    until actions.py takes over fully.
    """
    from modules.agents.gigachat_agent import generate_sql_with_review

    return generate_sql_with_review(
        source_text,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        code_revision_pass=code_revision_pass,
        stack=stack,
        **kwargs,
    )


def revise_sql(
    source_text: str,
    sql_to_revise: str,
    *,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    stack: str = "greenplum",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Ask GigaChat to review and improve existing SQL code."""
    from modules.agents.gigachat_agent import revise_sql_code

    return revise_sql_code(
        source_text,
        sql_to_revise,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        stack=stack,
        **kwargs,
    )


def discover_objects(
    source_text: str,
    *,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Discover SQL objects (tables, views, functions) referenced in source."""
    from modules.agents.gigachat_agent import get_objects_from_sql_or_function

    return get_objects_from_sql_or_function(
        source_text,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        **kwargs,
    )


def get_embeddings(
    texts,
    *,
    credentials_override: Optional[str] = None,
    model_override: Optional[str] = None,
    scope_override: Optional[str] = None,
    **kwargs: Any,
):
    """Compute embeddings for a list of text chunks."""
    from modules.agents.gigachat_agent import get_embeddings as _get_embeddings

    return _get_embeddings(
        texts,
        credentials_override=credentials_override,
        model_override=model_override,
        scope_override=scope_override,
        **kwargs,
    )


class GigaChatActions:
    """Stateless facade grouping all GigaChat actions.

    Instantiate once (e.g. in AgentModule) with default credentials,
    or pass overrides per-call.
    """

    def __init__(
        self,
        *,
        credentials_override: Optional[str] = None,
        model_override: Optional[str] = None,
        scope_override: Optional[str] = None,
    ) -> None:
        self._creds = credentials_override
        self._model = model_override
        self._scope = scope_override

    def _defaults(self) -> Dict[str, Any]:
        return {
            "credentials_override": self._creds,
            "model_override": self._model,
            "scope_override": self._scope,
        }

    def generate_sql(self, source_text: str, **kwargs) -> Dict[str, Any]:
        return generate_sql(source_text, **{**self._defaults(), **kwargs})

    def revise_sql(self, source_text: str, sql_to_revise: str, **kwargs) -> Dict[str, Any]:
        return revise_sql(source_text, sql_to_revise, **{**self._defaults(), **kwargs})

    def discover_objects(self, source_text: str, **kwargs) -> Dict[str, Any]:
        return discover_objects(source_text, **{**self._defaults(), **kwargs})

    def get_embeddings(self, texts, **kwargs):
        return get_embeddings(texts, **{**self._defaults(), **kwargs})

    def check_connection(self) -> bool:
        return GigaChatClient.is_available(self._creds)
