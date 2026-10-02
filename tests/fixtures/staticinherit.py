"""Fixture for static scanning of function-scope attachments used as
class members (inheritance, overriding, staticmethod, classmethod)."""

from tests.fixtures import decorator


def super_method(self, request):  # pragma: no cover
    return request


def sub_method(self, request):  # pragma: no cover
    return request


def static_function(request):  # pragma: no cover
    return request


def class_function(cls, request):  # pragma: no cover
    return request


# function-scope attachments: the callbacks live on the functions
# themselves rather than in a class namespace
decorator()(super_method)
decorator()(static_function)
decorator()(class_function)


class Super(object):
    method = super_method
    sm = staticmethod(static_function)
    cm = classmethod(class_function)


class Sub(Super):
    # overrides Super.method statically; the override itself carries no
    # attachment, so no callback of Super.method may fire for Sub
    method = sub_method
