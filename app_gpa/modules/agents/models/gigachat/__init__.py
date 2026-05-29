"""GigaChat model executor.

Public surface for the rest of the application:

    from modules.agents.models.gigachat import GigaChatClient, GigaChatActions

or via the provider shim (backwards-compat):

    from modules.agents.providers.gigachat_provider import GigaChatProvider
"""
from .client import GigaChatClient
from .actions import GigaChatActions

__all__ = ["GigaChatClient", "GigaChatActions"]
