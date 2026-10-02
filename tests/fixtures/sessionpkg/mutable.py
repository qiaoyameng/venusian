from tests.fixtures import decorator


@decorator(function=True)
def function(request):  # pragma: no cover
    return request


@decorator(function=True)
def flaky(request):  # pragma: no cover
    return request
