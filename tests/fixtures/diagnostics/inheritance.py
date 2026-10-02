from tests.fixtures import decorator
from venusian import lift


class Parent(object):
    @decorator(attr="inherited")
    def inherited(self):  # pragma: no cover
        pass


@lift()
class Child(Parent):
    pass


class NotLifted(Parent):
    pass
