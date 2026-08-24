from zxro.contract import M1Capabilities
from .home import resolve_home
from .registry import LocalRegistry
from .turn import LocalTurnStore
from .work import LocalWorkStore
from .durable import LocalDurableLoop


def m1_capabilities(home, registry, turn, artifacts=None) -> M1Capabilities:
    return LocalDurableLoop(home, turn, registry, artifacts)


def artifact_migration_capability(home, registry, turn):
    return LocalDurableLoop(home, turn, registry)


def providers(home):
    registry = LocalRegistry(home)
    work = LocalWorkStore(home, registry)
    turn = LocalTurnStore(home, work)
    return registry, work, turn


__all__ = ["resolve_home", "providers", "m1_capabilities", "artifact_migration_capability", "LocalRegistry", "LocalWorkStore", "LocalTurnStore", "LocalDurableLoop"]
