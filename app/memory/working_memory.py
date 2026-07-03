"""Working memory: in-memory dict per session."""


class WorkingMemory:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def start_session(self, session_id: str) -> None:
        self._store[session_id] = {}

    def set(self, session_id: str, key: str, value) -> None:
        self._store.setdefault(session_id, {})[key] = value

    def get(self, session_id: str, key: str):
        return self._store.get(session_id, {}).get(key)

    def clear_session(self, session_id: str) -> None:
        self._store.pop(session_id, None)
