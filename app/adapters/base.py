from abc import ABC, abstractmethod
from app.models.journal import JournalEntry, SearchQuery


class BaseDatastoreAdapter(ABC):
    @abstractmethod
    async def get_entry(self, uid: str) -> JournalEntry | None: ...

    @abstractmethod
    async def list_entries(self, query: SearchQuery) -> tuple[list[JournalEntry], int]: ...

    @abstractmethod
    async def delete_entry(self, uid: str) -> bool: ...

    @abstractmethod
    async def save_entry(self, entry: "JournalEntry") -> "JournalEntry": ...
