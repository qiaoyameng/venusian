from tests.fixtures import decorator


@decorator(function=True)
def ignored_function(request):  # pragma: no cover
    return request
