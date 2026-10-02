"""Fixture for testing detachment of venusian attachments.

The helpers in this module perform their ``venusian.attach`` and
``lift`` calls from within this module, so that a scan of this module
will find the resulting attachments.
"""
import venusian
from venusian import lift


def attach(wrapped, callback, category=None, name=None):
    """Attach ``callback`` to ``wrapped`` as if the attachment was made
    from this module.  Return the resulting ``AttachInfo``."""
    return venusian.attach(wrapped, callback, category=category, name=name, depth=0)


class _InfoCapturingDecorator(object):
    def __init__(self, callback, category, infos):
        self.callback = callback
        self.category = category
        self.infos = infos

    def __call__(self, wrapped):
        info = venusian.attach(wrapped, self.callback, category=self.category)
        self.infos.append(info)
        return wrapped


def make_double_decorated_class(callback, category):
    """Return ``(cls, infos)`` where ``cls`` has two methods, each
    decorated (a class-scope attach) with the same ``callback``."""
    infos = []
    decorator = _InfoCapturingDecorator(callback, category, infos)

    class Klass(object):
        @decorator
        def method_one(self):  # pragma: no cover
            pass

        @decorator
        def method_two(self):  # pragma: no cover
            pass

    return Klass, infos


def make_lifted_classes(callback, category):
    """Return ``(Super, Sub, infos)`` where ``Super`` has a method
    decorated with ``callback`` and ``Sub`` inherits the decoration via
    the ``lift`` class decorator."""
    infos = []
    decorator = _InfoCapturingDecorator(callback, category, infos)

    class Super(object):
        @decorator
        def method(self):  # pragma: no cover
            pass

    @lift()
    class Sub(Super):
        pass

    return Super, Sub, infos
