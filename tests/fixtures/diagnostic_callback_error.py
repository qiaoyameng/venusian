import venusian


def failing_callback(scanner, name, ob):
    raise RuntimeError("callback failed")


def attach(wrapped):
    venusian.attach(wrapped, failing_callback)
    return wrapped


@attach
def function(request):  # pragma: no cover
    return request
