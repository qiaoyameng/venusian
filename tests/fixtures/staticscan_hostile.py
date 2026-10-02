"""A bare module (no ``__path__``) with an exploding PEP 562 hook.

A dynamic scan calls ``hasattr(module, '__path__')``; because the hook
raises something other than :class:`AttributeError`, that scan fails.  A
static scan reads the real namespace and never consults the hook.
"""

from tests.fixtures import decorator

TOUCHED = []


def __getattr__(name):
    TOUCHED.append(name)
    raise RuntimeError("hostile module attribute touched: %s" % name)


@decorator()
def hostile_function():  # pragma: no cover
    pass


@decorator()
class HostileClass(object):  # pragma: no cover
    pass
