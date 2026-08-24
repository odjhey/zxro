from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class Watchtower:
    id: str
    cwd: str
    agent: str | None = None
    session: str | None = None

    def to_dict(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class Work:
    id: str
    watchtower_id: str
    state: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Turn:
    id: str
    work_id: str
    watchtower_id: str
    runtime: str
    agent: str
    session: str
    cwd: str
    state: str
    native_session_id: str | None = None

    def to_dict(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


class Registry(Protocol):
    def create(self, id: str, cwd: str, agent: str | None = None, session: str | None = None) -> Watchtower: ...
    def get(self, id: str) -> Watchtower: ...
    def list(self) -> list[Watchtower]: ...


class WorkStore(Protocol):
    def create(self, id: str, watchtower_id: str) -> Work: ...
    def get(self, id: str) -> Work: ...
    def list(self, watchtower_id: str | None = None, state: str | None = None) -> list[Work]: ...
    def close(self, id: str) -> Work: ...


class TurnStore(Protocol):
    def create(self, work_id: str, agent: str, session: str, cwd: str, native_session_id: str | None = None) -> Turn: ...
    def get(self, id: str) -> Turn: ...
    def list(self, work_id: str | None = None, state: str | None = None) -> list[Turn]: ...
