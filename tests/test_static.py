import unittest


class _Test(object):
    def __init__(self):
        self.registrations = []

    def __call__(self, **kw):
        self.registrations.append(kw)


def _signatures(registrations):
    """Order-independent identity of the callback set produced by a scan."""
    signatures = set()
    for reg in registrations:
        ob = reg["ob"]
        signatures.add(
            (
                reg["name"],
                reg.get("attr"),
                getattr(ob, "__module__", None),
                getattr(ob, "__name__", None),
            )
        )
    return signatures


class TestStaticScan(unittest.TestCase):
    def _makeScanner(self, test):
        from venusian import Scanner

        return Scanner(test=test)

    def test_scan_default_is_dynamic(self):
        # The default scan mode must remain attribute based for backwards
        # compatibility: scanning the hostile bare module raises because the
        # dynamic path calls hasattr(module, '__path__').
        from tests.fixtures import staticscan_hostile

        scanner = self._makeScanner(_Test())
        with self.assertRaises(RuntimeError):
            scanner.scan(staticscan_hostile)

    def test_static_scan_never_triggers_module_getattr(self):
        from tests.fixtures import staticscan_hostile

        touched_before = len(staticscan_hostile.TOUCHED)
        test = _Test()
        self._makeScanner(test).scan(staticscan_hostile, static=True)

        self.assertEqual(
            sorted(reg["name"] for reg in test.registrations),
            ["HostileClass", "hostile_function"],
        )
        self.assertEqual(
            len(staticscan_hostile.TOUCHED), touched_before
        )  # no dynamic lookup at all

    def test_static_scan_finds_attachments_without_touching_traps(self):
        from tests.fixtures import staticscan

        touched_before = list(staticscan.TOUCHED)
        test = _Test()
        self._makeScanner(test).scan(staticscan, static=True)

        names = sorted(
            (reg["name"], str(reg.get("attr")))
            for reg in test.registrations
        )
        # plain attachments
        self.assertIn(("plain_function", "None"), names)
        self.assertIn(("PlainClass", "None"), names)
        self.assertIn(("PlainClass", "method"), names)
        # staticmethod/classmethod attachments defined inside the class body
        self.assertIn(("PlainClass", "static_impl"), names)
        self.assertIn(("PlainClass", "class_impl"), names)
        # class whose metaclass raises when the magic attribute is read
        self.assertIn(("Sheltered", "method"), names)
        # module-scope staticmethod/classmethod wrappers
        self.assertIn(("static_bound", "None"), names)
        self.assertIn(("class_bound", "None"), names)
        # the unwrapped functions themselves are also plain globals
        self.assertIn(("static_bound_impl", "None"), names)
        self.assertIn(("class_bound_impl", "None"), names)
        # imported subpackage is still walked (module code does execute)
        self.assertIn(("sub_function", "None"), names)

        # not a single module hook or metaclass descriptor was invoked
        self.assertEqual(staticscan.TOUCHED, touched_before)

    def test_dynamic_scan_misses_what_static_scan_saves(self):
        from tests.fixtures import staticscan

        dynamic = _Test()
        # The dynamic scan survives the package-level hooks (they are only
        # reachable for names absent from the namespace) but silently loses the
        # objects hidden behind raising descriptors and staticmethod/
        # classmethod wrappers.
        self._makeScanner(dynamic).scan(staticscan)
        dynamic_names = {
            (reg["name"], reg.get("attr")) for reg in dynamic.registrations
        }
        self.assertNotIn(("Sheltered", "method"), dynamic_names)
        self.assertNotIn(("static_bound", None), dynamic_names)
        self.assertNotIn(("class_bound", None), dynamic_names)

    def test_static_and_dynamic_collect_identical_lift_callbacks(self):
        import venusian
        from tests.fixtures import lifting1

        static_test = _Test()
        dynamic_test = _Test()
        self._makeScanner(static_test).scan(lifting1, static=True)
        self._makeScanner(dynamic_test).scan(lifting1)

        static_sigs = _signatures(static_test.registrations)
        dynamic_sigs = _signatures(dynamic_test.registrations)
        self.assertEqual(static_sigs, dynamic_sigs)
        self.assertEqual(len(static_sigs), 11)

    def test_override_changes_callback_set_per_static_lookup(self):
        # Before the override, Super.boo's lifted callback is present on the
        # subclass; once Sub defines its own boo, the inherited callback must
        # be suppressed (Python name resolution / lift semantics).
        import importlib

        import venusian

        module_before = importlib.import_module("tests.fixtures.lifting3")

        static = _Test()
        dynamic = _Test()
        self._makeScanner(static).scan(module_before, static=True)
        self._makeScanner(dynamic).scan(module_before)
        before_static = {
            (reg["name"], reg.get("attr")) for reg in static.registrations
        }
        before_dynamic = {
            (reg["name"], reg.get("attr")) for reg in dynamic.registrations
        }
        self.assertEqual(before_static, before_dynamic)
        self.assertIn(("Sub", "boo"), before_static)

        # lifting1 overrides boo on Sub and adds more members; its lifted
        # Super2.hiss callback disappears because Sub redefines hiss without a
        # decoration.
        module_after = importlib.import_module("tests.fixtures.lifting1")
        static_after = _Test()
        dynamic_after = _Test()
        self._makeScanner(static_after).scan(module_after, static=True)
        self._makeScanner(dynamic_after).scan(module_after)
        after_static = _signatures(static_after.registrations)
        after_dynamic = _signatures(dynamic_after.registrations)
        self.assertEqual(after_static, after_dynamic)
        self.assertNotEqual(before_static, after_static)

    def test_parity_across_fixtures(self):
        import importlib

        for fixture in (
            "lifting2",
            "lifting3",
            "lifting4",
            "lifting5",
            "subclassing",
            "inheritance",
            "classdecorator",
            "class_and_method",
            "category",
        ):
            module = importlib.import_module("tests.fixtures." + fixture)
            static_test = _Test()
            dynamic_test = _Test()
            self._makeScanner(static_test).scan(module, static=True)
            self._makeScanner(dynamic_test).scan(module)
            self.assertEqual(
                _signatures(static_test.registrations),
                _signatures(dynamic_test.registrations),
                "callback set mismatch for %s" % fixture,
            )

    def test_static_respects_categories(self):
        from tests.fixtures import category

        test = _Test()
        self._makeScanner(test).scan(
            category, static=True, categories=("mycategory",)
        )
        self.assertEqual(len(test.registrations), 1)
        self.assertEqual(test.registrations[0]["name"], "function")

    def test_static_respects_ignore(self):
        from tests.fixtures import staticscan

        test = _Test()
        self._makeScanner(test).scan(
            staticscan,
            static=True,
            ignore=[".Sheltered", ".subpkg"],
        )
        names = {reg["name"] for reg in test.registrations}
        self.assertNotIn("Sheltered", names)
        self.assertNotIn("sub_function", names)
        # unrelated attachments remain
        self.assertIn("plain_function", names)


class TestStaticHelpers(unittest.TestCase):
    def test_wrapped_chain_finds_attachment_without_invocation(self):
        import venusian
        from venusian import _static_attached_categories

        def callback(*args):
            pass

        def decorate(wrapped):
            venusian.attach(wrapped, callback)
            return wrapped

        inner = decorate(lambda: None)
        middle = lambda: None
        middle.__wrapped__ = inner
        outer = lambda: None
        outer.__wrapped__ = middle
        inner.__wrapped__ = outer  # close the loop

        categories, resolved = _static_attached_categories(outer)
        self.assertIsNotNone(categories)
        self.assertIs(resolved, inner)

    def test_cyclic_wrapped_chain_without_attachment_terminates(self):
        from venusian import _static_attached_categories

        first = lambda: None
        second = lambda: None
        first.__wrapped__ = second
        second.__wrapped__ = first

        categories, resolved = _static_attached_categories(first)
        self.assertIsNone(categories)
        self.assertIs(resolved, first)

    def test_wrapped_descriptor_is_never_called(self):
        from venusian import _static_attached_categories

        class Trap(object):
            @property
            def __wrapped__(self):
                raise RuntimeError("__wrapped__ descriptor invoked")

        categories, resolved = _static_attached_categories(Trap())
        self.assertIsNone(categories)

    def test_staticmethod_and_classmethod_are_unwrapped(self):
        import venusian
        from venusian import _static_attached_categories

        def callback(*args):
            pass

        def decorate(wrapped):
            venusian.attach(wrapped, callback)
            return wrapped

        function = decorate(lambda: None)
        for descriptor in (staticmethod(function), classmethod(function)):
            categories, resolved = _static_attached_categories(descriptor)
            self.assertIsNotNone(categories)
            self.assertIs(resolved, function)

    def test_inherited_categories_are_ignored(self):
        import venusian
        from venusian import _static_attached_categories

        def callback(*args):
            pass

        def attach(wrapped):
            venusian.attach(wrapped, callback)
            return wrapped

        @attach
        class Base(object):
            pass

        class Derived(Base):
            pass

        # The Derived class resolves the magic name through inheritance, but it
        # has no binding in its own namespace; static discovery must skip it.
        categories, _ = _static_attached_categories(Derived)
        self.assertIsNone(categories)

        base_categories, _ = _static_attached_categories(Base)
        self.assertIsNotNone(base_categories)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
