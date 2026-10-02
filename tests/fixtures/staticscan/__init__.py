"""Fixtures exercising static namespace discovery.

The module deliberately exposes dynamic attribute hooks and descriptor
traps that explode when touched by a generic, attribute-based scan.  A
static scan must discover the ordinary Venusian attachments without ever
invoking any of those traps.  The ``subpkg`` subpackage is intentionally
*not* imported here so that package traversal (which does import it) is
exercised separately from root enumeration.
"""

from tests.fixtures import decorator

# Every time one of the traps below fires we record it here so that tests
# can assert static scanning never touched them.
TOUCHED = []


def __getattr__(name):
    TOUCHED.append(("module", name))
    raise RuntimeError("staticscan dynamic module attribute touched: %s" % name)


class ExplodingMeta(type):
    @property
    def __venusian_callbacks__(cls):
        TOUCHED.append(("metaclass", cls.__name__))
        raise RuntimeError("metaclass descriptor probed on %s" % cls.__name__)


@decorator()
def plain_function():  # pragma: no cover
    pass


@decorator()
class PlainClass(object):  # pragma: no cover
    @decorator()
    def method(self):
        pass

    @decorator()
    @staticmethod
    def static_impl():
        pass

    @decorator()
    @classmethod
    def class_impl(cls):
        pass


class Sheltered(metaclass=ExplodingMeta):  # pragma: no cover
    @decorator()
    def method(self):
        pass


# Module-scope bindings of staticmethod/classmethod wrappers: the attachment
# lives on the underlying function (the wrapper object has none in its own
# namespace), so an attribute-based scan misses it.
@decorator()
def static_bound_impl():  # pragma: no cover
    pass


static_bound = staticmethod(static_bound_impl)


@decorator()
def class_bound_impl():  # pragma: no cover
    pass


class_bound = classmethod(class_bound_impl)
