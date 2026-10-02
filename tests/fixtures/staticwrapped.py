"""Fixture for static scanning of __wrapped__ chains, including cycles."""

import functools

from tests.fixtures import decorator


def inner(request):  # pragma: no cover
    return request


decorator()(inner)


def wrapper(request):  # pragma: no cover
    return inner(request)


# not functools.wraps: the attachment is only reachable by statically
# following the __wrapped__ link in wrapper's own namespace
wrapper.__wrapped__ = inner


def cycle_a(request):  # pragma: no cover
    return request


def cycle_b(request):  # pragma: no cover
    return request


cycle_a.__wrapped__ = cycle_b
cycle_b.__wrapped__ = cycle_a


def self_cycle(request):  # pragma: no cover
    return request


self_cycle.__wrapped__ = self_cycle


def wrapped_orig(request):  # pragma: no cover
    return request


decorator()(wrapped_orig)


@functools.wraps(wrapped_orig)
def wraps_wrapper(request):  # pragma: no cover
    return wrapped_orig(request)


class WrapsHolder(object):
    # functools.wraps copies the categories object into the wrapper's
    # own namespace; the copy must not fire for the wrapper, but the
    # original attachment is reachable through __wrapped__
    m = wraps_wrapper
    n = wrapped_orig
