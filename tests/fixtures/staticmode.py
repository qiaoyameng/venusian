"""Fixture module for static member scanning.

Contains normal Venusian attachments alongside objects whose dynamic
attribute machinery (module ``__getattr__``, descriptors, metaclass
``__getattr__``) records accesses and raises when touched.  A static
scan must find the normal attachments without touching any of the
dynamic machinery.
"""

from tests.fixtures import decorator

dynamic_accesses = []
descriptor_accesses = []


@decorator(function=True)
def function(request):  # pragma: no cover
    return request


@decorator(class_=True)
class Class(object):
    @decorator(method=True)
    def method(self, request):  # pragma: no cover
        return request


class BoomDescriptor(object):
    """A descriptor which records and raises on any access."""

    def __get__(self, instance, owner=None):
        descriptor_accesses.append("descriptor")
        raise RuntimeError("descriptor was accessed")


class Exploding(object):
    __venusian_callbacks__ = BoomDescriptor()


exploding = Exploding()


class BoomMeta(type):
    def __getattr__(cls, name):
        descriptor_accesses.append("metaclass")
        raise RuntimeError("metaclass attribute %r was accessed" % name)


class MetaBoom(object, metaclass=BoomMeta):
    pass


def __getattr__(name):
    # PEP 562 module __getattr__: must never be triggered by a static
    # scan.  Dunder lookups behave normally so that e.g. the missing
    # __path__ of this module keeps raising AttributeError.
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    dynamic_accesses.append(name)
    raise RuntimeError("dynamic attribute %r was accessed" % name)


def __dir__():
    return sorted(list(globals().keys()) + ["dynamic_one", "dynamic_two"])
