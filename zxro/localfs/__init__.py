from zxro.contract import M1Capabilities, M2Capabilities
from .home import resolve_home
from .registry import LocalRegistry
from .turn import LocalTurnStore
from .work import LocalWorkStore
from .durable import LocalDurableLoop


def m1_capabilities(home, registry, turn) -> M1Capabilities:
    return LocalDurableLoop(home, turn, registry=registry)


def m2_capabilities(home, registry, work, turn) -> M2Capabilities:
    return LocalDurableLoop(home, turn, registry=registry, work=work)


def providers(home):
    registry = LocalRegistry(home)
    work = LocalWorkStore(home, registry)
    turn = LocalTurnStore(home, work)
    return registry, work, turn


__all__ = ["resolve_home", "providers", "m1_capabilities", "m2_capabilities", "LocalRegistry", "LocalWorkStore", "LocalTurnStore", "LocalDurableLoop"]
