import venusian


def raiser(wrapped):
    def callback(scanner, name, ob):  # pragma: no cover
        raise RuntimeError("boom")

    venusian.attach(wrapped, callback, category="raising")
    return wrapped


@raiser
def function(request):  # pragma: no cover
    return request
