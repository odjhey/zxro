from .home import resolve_home
from .registry import LocalRegistry
from .turn import LocalTurnStore
from .work import LocalWorkStore
from zxro.settle import LocalDurableLoop


def providers(home):
    registry = LocalRegistry(home)
    work = LocalWorkStore(home, registry)
    turn = LocalTurnStore(home, work)
    return registry, work, turn


__all__ = ["resolve_home", "providers", "LocalRegistry", "LocalWorkStore", "LocalTurnStore", "LocalDurableLoop"]
