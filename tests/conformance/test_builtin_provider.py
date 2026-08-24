import unittest
from tests.conformance.base import ProviderConformance
from zxro.localfs import providers


class BuiltinProviderConformance(ProviderConformance, unittest.TestCase):
    factory = staticmethod(providers)
