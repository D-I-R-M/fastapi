from functools import lru_cache

from app.adapters.datastore import BaseDatastoreAdapter, get_datastore_adapter
from app.adapters.llm import BaseLLMAdapter, get_llm_adapter
from app.services.journal import JournalService, ReflectionService


@lru_cache(maxsize=1)
def _cached_datastore() -> BaseDatastoreAdapter:
    return get_datastore_adapter()


@lru_cache(maxsize=1)
def _cached_llm() -> BaseLLMAdapter:
    return get_llm_adapter()


def get_journal_service() -> JournalService:
    return JournalService(adapter=_cached_datastore())


def get_reflection_service() -> ReflectionService:
    return ReflectionService(
        journal=get_journal_service(),
        llm=_cached_llm(),
    )
