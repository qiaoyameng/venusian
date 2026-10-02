from venusian import attach


def callback(scanner, name, ob):  # pragma: no cover
    scanner.test(name=name, ob=ob, callback="callback")


def late_callback(scanner, name, ob):  # pragma: no cover
    scanner.test(name=name, ob=ob, callback="late_callback")


def function(request):  # pragma: no cover
    return request


attach(function, callback, category="test", depth=0)


def attach_late():
    # attach an extra callback to ``function`` from within this module so
    # that the callback's module name matches this module during a scan
    attach(function, late_callback, category="test", depth=0)
