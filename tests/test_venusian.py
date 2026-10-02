import contextlib
import os
import re
import sys
import unittest


@contextlib.contextmanager
def with_entry_in_sys_path(entry):
    """Context manager that temporarily puts an entry at head of sys.path"""
    sys.path.insert(0, entry)
    yield
    sys.path.remove(entry)


def zip_file_in_sys_path():
    """Context manager that puts zipped.zip at head of sys.path"""
    zip_pkg_path = os.path.join(os.path.dirname(__file__), "fixtures", "zipped.zip")
    return with_entry_in_sys_path(zip_pkg_path)


class _Test(object):
    def __init__(self):
        self.registrations = []

    def __call__(self, **kw):
        self.registrations.append(kw)


class TestScanner(unittest.TestCase):
    def _makeOne(self, **kw):
        from venusian import Scanner

        return Scanner(**kw)

    def test_package(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one)
        self.assertEqual(len(test.registrations), 6)
        test.registrations.sort(key=lambda x: (x["name"], x["ob"].__module__))
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1
        from tests.fixtures.one.module2 import Class as Class2
        from tests.fixtures.one.module2 import function as func2
        from tests.fixtures.one.module2 import inst as inst2

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "Class")
        self.assertEqual(test.registrations[1]["ob"], Class2)
        self.assertEqual(test.registrations[1]["method"], True)

        self.assertEqual(test.registrations[2]["name"], "function")
        self.assertEqual(test.registrations[2]["ob"], func1)
        self.assertEqual(test.registrations[2]["function"], True)

        self.assertEqual(test.registrations[3]["name"], "function")
        self.assertEqual(test.registrations[3]["ob"], func2)
        self.assertEqual(test.registrations[3]["function"], True)

        self.assertEqual(test.registrations[4]["name"], "inst")
        self.assertEqual(test.registrations[4]["ob"], inst1)
        self.assertEqual(test.registrations[4]["instance"], True)

        self.assertEqual(test.registrations[5]["name"], "inst")
        self.assertEqual(test.registrations[5]["ob"], inst2)
        self.assertEqual(test.registrations[5]["instance"], True)

    def test_module_in_zip(self):
        with zip_file_in_sys_path():
            import moduleinzip
        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(moduleinzip)
        self.assertEqual(len(test.registrations), 3)
        test.registrations.sort(key=lambda x: (x["name"], x["ob"].__module__))
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1
        from tests.fixtures.one.module2 import Class as Class2
        from tests.fixtures.one.module2 import function as func2
        from tests.fixtures.one.module2 import inst as inst2

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], moduleinzip.Class)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], moduleinzip.function)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], moduleinzip.inst)
        self.assertEqual(test.registrations[2]["instance"], True)

    def test_package_in_zip(self):
        with zip_file_in_sys_path():
            import packageinzip
        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(packageinzip)

    def test_package_with_orphaned_pyc_file(self):
        # There is a module2.pyc file in the "pycfixtures" package; it
        # has no corresponding .py source file.  Such orphaned .pyc
        # files should be ignored during scanning.
        from tests.fixtures import pyc

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(pyc)
        self.assertEqual(len(test.registrations), 4)
        test.registrations.sort(key=lambda x: (x["name"], x["ob"].__module__))
        from tests.fixtures.pyc import subpackage
        from tests.fixtures.pyc.module import Class as Class1
        from tests.fixtures.pyc.module import function as func1
        from tests.fixtures.pyc.module import inst as inst1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], inst1)
        self.assertEqual(test.registrations[2]["instance"], True)

        self.assertEqual(test.registrations[3]["name"], "pkgfunction")
        self.assertEqual(test.registrations[3]["ob"], subpackage.pkgfunction)
        self.assertEqual(test.registrations[3]["function"], True)

    def test_module(self):
        from tests.fixtures.one import module

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(module)
        self.assertEqual(len(test.registrations), 3)
        test.registrations.sort(key=lambda x: (x["name"], x["ob"].__module__))
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], inst1)
        self.assertEqual(test.registrations[2]["instance"], True)

    def test_ignore_imported(self):
        # even though "twofunction" is imported into "one", it should not
        # be registered, because it's only imported in one and not defined
        # there
        from tests.fixtures.importonly import one, two

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one)
        self.assertEqual(len(test.registrations), 1)
        scanner.scan(two)
        self.assertEqual(len(test.registrations), 2)

    def test_dont_ignore_legit_decorators(self):
        # make sure venusian picks up other decorated things from
        # imported modules when the whole package is scanned
        from tests.fixtures import import_and_scan

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(import_and_scan)
        self.assertEqual(len(test.registrations), 2)

    def test_one_category(self):
        from tests.fixtures import category

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(category, categories=("mycategory",))
        self.assertEqual(len(test.registrations), 1)
        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], category.function)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_all_categories_implicit(self):
        from tests.fixtures import category

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(category)
        self.assertEqual(len(test.registrations), 2)
        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], category.function)
        self.assertEqual(test.registrations[0]["function"], True)
        self.assertEqual(test.registrations[1]["name"], "function2")
        self.assertEqual(test.registrations[1]["ob"], category.function2)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_all_categories_explicit(self):
        from tests.fixtures import category

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(category, categories=("mycategory", "mycategory2"))
        self.assertEqual(len(test.registrations), 2)
        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], category.function)
        self.assertEqual(test.registrations[0]["function"], True)
        self.assertEqual(test.registrations[1]["name"], "function2")
        self.assertEqual(test.registrations[1]["ob"], category.function2)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_decorations_arent_inherited(self):
        from tests.fixtures import inheritance

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(inheritance)
        self.assertEqual(
            test.registrations,
            [
                dict(name="Parent", ob=inheritance.Parent),
            ],
        )

    def test_classdecorator(self):
        from tests.fixtures import classdecorator

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(classdecorator)
        test.registrations.sort(key=lambda x: (x["name"], x["ob"].__module__))
        self.assertEqual(len(test.registrations), 2)
        self.assertEqual(test.registrations[0]["name"], "SubClass")
        self.assertEqual(test.registrations[0]["ob"], classdecorator.SubClass)
        self.assertEqual(test.registrations[0]["subclass"], True)
        self.assertEqual(test.registrations[1]["name"], "SuperClass")
        self.assertEqual(test.registrations[1]["ob"], classdecorator.SuperClass)
        self.assertEqual(test.registrations[1]["superclass"], True)

    def test_class_and_method_decorator(self):
        from tests.fixtures import class_and_method

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(class_and_method)
        self.assertEqual(len(test.registrations), 2)
        self.assertEqual(test.registrations[0]["name"], "ClassWithMethod")
        self.assertEqual(test.registrations[0]["ob"], class_and_method.ClassWithMethod)
        self.assertEqual(test.registrations[0]["method"], True)
        self.assertEqual(test.registrations[1]["name"], "ClassWithMethod")
        self.assertEqual(test.registrations[1]["ob"], class_and_method.ClassWithMethod)
        self.assertEqual(test.registrations[1]["class_"], True)

    def test_scan_only_finds_classdecoration_once(self):
        from tests.fixtures import two
        from tests.fixtures.two.mod1 import Class

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(two)
        self.assertEqual(
            test.registrations,
            [
                dict(name="Class", ob=Class),
            ],
        )

    def test_importerror_during_scan_default_onerror(self):
        from tests.fixtures import importerror

        test = _Test()
        scanner = self._makeOne(test=test)
        # without a custom onerror, scan will propagate the importerror from
        # will_cause_import_error
        self.assertRaises(ImportError, scanner.scan, importerror)

    def test_importerror_during_scan_default_onerror_with_ignore(self):
        from tests.fixtures import importerror

        test = _Test()
        scanner = self._makeOne(test=test)
        # scan will ignore the errors from will_cause_import_error due
        # to us choosing to ignore that package
        scanner.scan(
            importerror, ignore="tests.fixtures.importerror.will_cause_import_error"
        )

    def test_importerror_during_scan_custom_onerror(self):
        from tests.fixtures import importerror

        test = _Test()
        scanner = self._makeOne(test=test)

        # with this custom onerror, scan will not propagate the importerror
        # from will_raise_importerror
        def onerror(name):
            if not issubclass(sys.exc_info()[0], ImportError):
                raise

        scanner.scan(importerror, onerror=onerror)
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.importerror import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_importerror_in_package_during_scan_custom_onerror(self):
        from tests.fixtures import importerror_package

        md("tests.fixtures.importerror_package.will_cause_import_error")
        test = _Test()
        scanner = self._makeOne(test=test)

        # with this custom onerror, scan will not propagate the importerror
        # from will_raise_importerror
        def onerror(name):
            raise ValueError

        self.assertRaises(
            ValueError, scanner.scan, importerror_package, onerror=onerror
        )
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.importerror_package import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_attrerror_during_scan_custom_onerror(self):
        from tests.fixtures import attrerror

        test = _Test()
        scanner = self._makeOne(test=test)

        # with this custom onerror, scan will not propagate the importerror
        # from will_raise_importerror
        def onerror(name):
            if not issubclass(sys.exc_info()[0], ImportError):
                raise

        self.assertRaises(AttributeError, scanner.scan, attrerror, onerror=onerror)
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.attrerror import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_attrerror_in_package_during_scan_custom_onerror(self):
        from tests.fixtures import attrerror_package

        md("tests.fixtures.attrerror_package.will_cause_import_error")
        test = _Test()
        scanner = self._makeOne(test=test)

        # with this custom onerror, scan will not propagate the importerror
        # from will_raise_importerror
        def onerror(name):
            if not issubclass(sys.exc_info()[0], ImportError):
                raise

        self.assertRaises(
            AttributeError, scanner.scan, attrerror_package, onerror=onerror
        )
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.attrerror_package import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_attrerror_in_package_during_scan_no_custom_onerror(self):
        from tests.fixtures import attrerror_package

        md("tests.fixtures.attrerror_package.will_cause_import_error")
        test = _Test()
        scanner = self._makeOne(test=test)
        self.assertRaises(AttributeError, scanner.scan, attrerror_package)
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.attrerror_package import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_onerror_used_to_swallow_all_exceptions(self):
        from tests.fixtures import subpackages

        test = _Test()
        scanner = self._makeOne(test=test)
        # onerror can also be used to skip errors while scanning submodules
        # e.g.: test modules under a given library
        swallowed = []

        def ignore_child(name):
            swallowed.append(name)

        scanner.scan(subpackages, onerror=ignore_child)
        self.assertEqual(
            swallowed,
            [
                "tests.fixtures.subpackages.childpackage.will_cause_import_error",
                "tests.fixtures.subpackages.mod2",
            ],
        )
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.subpackages import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_ignore_by_full_dotted_name(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one, ignore=["tests.fixtures.one.module2"])
        self.assertEqual(len(test.registrations), 3)
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], inst1)
        self.assertEqual(test.registrations[2]["instance"], True)

    def test_ignore_by_full_dotted_name2(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(nested, ignore=["tests.fixtures.nested.sub1"])
        self.assertEqual(len(test.registrations), 3)
        from tests.fixtures.nested import function as func1
        from tests.fixtures.nested.sub2 import function as func2
        from tests.fixtures.nested.sub2.subsub2 import function as func3

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func2)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "function")
        self.assertEqual(test.registrations[2]["ob"], func3)
        self.assertEqual(test.registrations[2]["function"], True)

    def test_ignore_by_full_dotted_name3(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            nested, ignore=["tests.fixtures.nested.sub1", "tests.fixtures.nested.sub2"]
        )
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.nested import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_ignore_by_full_dotted_name4(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            nested,
            ignore=["tests.fixtures.nested.sub1", "tests.fixtures.nested.function"],
        )
        self.assertEqual(len(test.registrations), 2)
        from tests.fixtures.nested.sub2 import function as func2
        from tests.fixtures.nested.sub2.subsub2 import function as func3

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func2)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func3)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_ignore_by_relative_dotted_name(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one, ignore=[".module2"])
        self.assertEqual(len(test.registrations), 3)
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], inst1)
        self.assertEqual(test.registrations[2]["instance"], True)

    def test_ignore_by_relative_dotted_name2(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(nested, ignore=[".sub1"])
        self.assertEqual(len(test.registrations), 3)
        from tests.fixtures.nested import function as func1
        from tests.fixtures.nested.sub2 import function as func2
        from tests.fixtures.nested.sub2.subsub2 import function as func3

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func2)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "function")
        self.assertEqual(test.registrations[2]["ob"], func3)
        self.assertEqual(test.registrations[2]["function"], True)

    def test_ignore_by_relative_dotted_name3(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(nested, ignore=[".sub1", ".sub2"])
        self.assertEqual(len(test.registrations), 1)
        from tests.fixtures.nested import function as func1

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

    def test_ignore_by_relative_dotted_name4(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(nested, ignore=[".sub1", ".function"])
        self.assertEqual(len(test.registrations), 2)
        from tests.fixtures.nested.sub2 import function as func2
        from tests.fixtures.nested.sub2.subsub2 import function as func3

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func2)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func3)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_ignore_by_function(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            one, ignore=[re.compile("Class").search, re.compile("inst").search]
        )
        self.assertEqual(len(test.registrations), 2)
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module2 import function as func2

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func1)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func2)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_ignore_by_function_nested(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(nested, ignore=[re.compile(".function$").search])
        self.assertEqual(len(test.registrations), 0)

    def test_ignore_by_function_nested2(self):
        from tests.fixtures import nested

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            nested,
            ignore=[re.compile("sub2$").search, re.compile("nested.function$").search],
        )
        self.assertEqual(len(test.registrations), 2)

        from tests.fixtures.nested.sub1 import function as func2
        from tests.fixtures.nested.sub1.subsub1 import function as func3

        self.assertEqual(test.registrations[0]["name"], "function")
        self.assertEqual(test.registrations[0]["ob"], func2)
        self.assertEqual(test.registrations[0]["function"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func3)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_ignore_as_string(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one, ignore="tests.fixtures.one.module2")
        self.assertEqual(len(test.registrations), 3)
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1
        from tests.fixtures.one.module import inst as inst1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

        self.assertEqual(test.registrations[2]["name"], "inst")
        self.assertEqual(test.registrations[2]["ob"], inst1)
        self.assertEqual(test.registrations[2]["instance"], True)

    def test_ignore_mixed_string_and_func(self):
        import re

        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            one, ignore=["tests.fixtures.one.module2", re.compile("inst").search]
        )
        self.assertEqual(len(test.registrations), 2)
        from tests.fixtures.one.module import Class as Class1
        from tests.fixtures.one.module import function as func1

        self.assertEqual(test.registrations[0]["name"], "Class")
        self.assertEqual(test.registrations[0]["ob"], Class1)
        self.assertEqual(test.registrations[0]["method"], True)

        self.assertEqual(test.registrations[1]["name"], "function")
        self.assertEqual(test.registrations[1]["ob"], func1)
        self.assertEqual(test.registrations[1]["function"], True)

    def test_ignore_mixed_string_abs_rel_and_func(self):
        import re

        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(
            one,
            ignore=["tests.fixtures.one.module2", ".module", re.compile("inst").search],
        )
        self.assertEqual(len(test.registrations), 0)

    def test_lifting1(self):
        from tests.fixtures import lifting1

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting1)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 11)

        self.assertEqual(test.registrations[0]["attr"], "boo")
        self.assertEqual(test.registrations[0]["name"], "Sub")
        self.assertEqual(test.registrations[0]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[1]["attr"], "classname")
        self.assertEqual(test.registrations[1]["name"], "Sub")
        self.assertEqual(test.registrations[1]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[2]["attr"], "hiss")
        self.assertEqual(test.registrations[2]["name"], "Sub")
        self.assertEqual(test.registrations[2]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[3]["attr"], "jump")
        self.assertEqual(test.registrations[3]["name"], "Sub")
        self.assertEqual(test.registrations[3]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[4]["attr"], "ram")
        self.assertEqual(test.registrations[4]["name"], "Sub")
        self.assertEqual(test.registrations[4]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[5]["attr"], "smack")
        self.assertEqual(test.registrations[5]["name"], "Sub")
        self.assertEqual(test.registrations[5]["ob"], lifting1.Sub)

        self.assertEqual(test.registrations[6]["attr"], "boo")
        self.assertEqual(test.registrations[6]["name"], "Super1")
        self.assertEqual(test.registrations[6]["ob"], lifting1.Super1)

        self.assertEqual(test.registrations[7]["attr"], "classname")
        self.assertEqual(test.registrations[7]["name"], "Super1")
        self.assertEqual(test.registrations[7]["ob"], lifting1.Super1)

        self.assertEqual(test.registrations[8]["attr"], "ram")
        self.assertEqual(test.registrations[8]["name"], "Super1")
        self.assertEqual(test.registrations[8]["ob"], lifting1.Super1)

        self.assertEqual(test.registrations[9]["attr"], "hiss")
        self.assertEqual(test.registrations[9]["name"], "Super2")
        self.assertEqual(test.registrations[9]["ob"], lifting1.Super2)

        self.assertEqual(test.registrations[10]["attr"], "jump")
        self.assertEqual(test.registrations[10]["name"], "Super2")
        self.assertEqual(test.registrations[10]["ob"], lifting1.Super2)

    def test_lifting2(self):
        from tests.fixtures import lifting2

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting2)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 6)

        self.assertEqual(test.registrations[0]["attr"], "boo")
        self.assertEqual(test.registrations[0]["name"], "Sub")
        self.assertEqual(test.registrations[0]["ob"], lifting2.Sub)

        self.assertEqual(test.registrations[1]["attr"], "classname")
        self.assertEqual(test.registrations[1]["name"], "Sub")
        self.assertEqual(test.registrations[1]["ob"], lifting2.Sub)

        self.assertEqual(test.registrations[2]["attr"], "hiss")
        self.assertEqual(test.registrations[2]["name"], "Sub")
        self.assertEqual(test.registrations[2]["ob"], lifting2.Sub)

        self.assertEqual(test.registrations[3]["attr"], "jump")
        self.assertEqual(test.registrations[3]["name"], "Sub")
        self.assertEqual(test.registrations[3]["ob"], lifting2.Sub)

        self.assertEqual(test.registrations[4]["attr"], "ram")
        self.assertEqual(test.registrations[4]["name"], "Sub")
        self.assertEqual(test.registrations[4]["ob"], lifting2.Sub)

        self.assertEqual(test.registrations[5]["attr"], "smack")
        self.assertEqual(test.registrations[5]["name"], "Sub")
        self.assertEqual(test.registrations[5]["ob"], lifting2.Sub)

    def test_lifting3(self):
        from tests.fixtures import lifting3

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting3)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 8)

        self.assertEqual(test.registrations[0]["attr"], "boo")
        self.assertEqual(test.registrations[0]["name"], "Sub")
        self.assertEqual(test.registrations[0]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[1]["attr"], "classname")
        self.assertEqual(test.registrations[1]["name"], "Sub")
        self.assertEqual(test.registrations[1]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[2]["attr"], "hiss")
        self.assertEqual(test.registrations[2]["name"], "Sub")
        self.assertEqual(test.registrations[2]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[3]["attr"], "jump")
        self.assertEqual(test.registrations[3]["name"], "Sub")
        self.assertEqual(test.registrations[3]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[4]["attr"], "ram")
        self.assertEqual(test.registrations[4]["name"], "Sub")
        self.assertEqual(test.registrations[4]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[5]["attr"], "smack")
        self.assertEqual(test.registrations[5]["name"], "Sub")
        self.assertEqual(test.registrations[5]["ob"], lifting3.Sub)

        self.assertEqual(test.registrations[6]["attr"], "hiss")
        self.assertEqual(test.registrations[6]["name"], "Super2")
        self.assertEqual(test.registrations[6]["ob"], lifting3.Super2)

        self.assertEqual(test.registrations[7]["attr"], "jump")
        self.assertEqual(test.registrations[7]["name"], "Super2")
        self.assertEqual(test.registrations[7]["ob"], lifting3.Super2)

    def test_lifting4(self):
        from tests.fixtures import lifting4

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting4)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 2)

        self.assertEqual(test.registrations[0]["attr"], "hiss")
        self.assertEqual(test.registrations[0]["name"], "Sub")
        self.assertEqual(test.registrations[0]["ob"], lifting4.Sub)

        self.assertEqual(test.registrations[1]["attr"], "smack")
        self.assertEqual(test.registrations[1]["name"], "Sub")
        self.assertEqual(test.registrations[1]["ob"], lifting4.Sub)

    def test_lifting5(self):
        from tests.fixtures import lifting5

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting5)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 15)

        self.assertEqual(test.registrations[0]["attr"], "boo")
        self.assertEqual(test.registrations[0]["name"], "Sub")
        self.assertEqual(test.registrations[0]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[1]["attr"], "classname")
        self.assertEqual(test.registrations[1]["name"], "Sub")
        self.assertEqual(test.registrations[1]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[2]["attr"], "hiss")
        self.assertEqual(test.registrations[2]["name"], "Sub")
        self.assertEqual(test.registrations[2]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[3]["attr"], "jump")
        self.assertEqual(test.registrations[3]["name"], "Sub")
        self.assertEqual(test.registrations[3]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[4]["attr"], "ram")
        self.assertEqual(test.registrations[4]["name"], "Sub")
        self.assertEqual(test.registrations[4]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[5]["attr"], "smack")
        self.assertEqual(test.registrations[5]["name"], "Sub")
        self.assertEqual(test.registrations[5]["ob"], lifting5.Sub)

        self.assertEqual(test.registrations[6]["attr"], "boo")
        self.assertEqual(test.registrations[6]["name"], "Super1")
        self.assertEqual(test.registrations[6]["ob"], lifting5.Super1)

        self.assertEqual(test.registrations[7]["attr"], "classname")
        self.assertEqual(test.registrations[7]["name"], "Super1")
        self.assertEqual(test.registrations[7]["ob"], lifting5.Super1)

        self.assertEqual(test.registrations[8]["attr"], "jump")
        self.assertEqual(test.registrations[8]["name"], "Super1")
        self.assertEqual(test.registrations[8]["ob"], lifting5.Super1)

        self.assertEqual(test.registrations[9]["attr"], "ram")
        self.assertEqual(test.registrations[9]["name"], "Super1")
        self.assertEqual(test.registrations[9]["ob"], lifting5.Super1)

        self.assertEqual(test.registrations[10]["attr"], "boo")
        self.assertEqual(test.registrations[10]["name"], "Super2")
        self.assertEqual(test.registrations[10]["ob"], lifting5.Super2)

        self.assertEqual(test.registrations[11]["attr"], "classname")
        self.assertEqual(test.registrations[11]["name"], "Super2")
        self.assertEqual(test.registrations[11]["ob"], lifting5.Super2)

        self.assertEqual(test.registrations[12]["attr"], "hiss")
        self.assertEqual(test.registrations[12]["name"], "Super2")
        self.assertEqual(test.registrations[12]["ob"], lifting5.Super2)

        self.assertEqual(test.registrations[13]["attr"], "jump")
        self.assertEqual(test.registrations[13]["name"], "Super2")
        self.assertEqual(test.registrations[13]["ob"], lifting5.Super2)

        self.assertEqual(test.registrations[14]["attr"], "ram")
        self.assertEqual(test.registrations[14]["name"], "Super2")
        self.assertEqual(test.registrations[14]["ob"], lifting5.Super2)

    def test_subclassing(self):
        from tests.fixtures import subclassing

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(subclassing)
        test.registrations.sort(
            key=lambda x: (x["name"], x["attr"], x["ob"].__module__)
        )
        self.assertEqual(len(test.registrations), 2)

        self.assertEqual(test.registrations[0]["attr"], "boo")
        self.assertEqual(test.registrations[0]["name"], "Super")
        self.assertEqual(test.registrations[0]["ob"], subclassing.Super)

        self.assertEqual(test.registrations[1]["attr"], "classname")
        self.assertEqual(test.registrations[1]["name"], "Super")
        self.assertEqual(test.registrations[1]["ob"], subclassing.Super)


class TestScanDiagnostics(unittest.TestCase):
    def _makeOne(self, **kw):
        from venusian import Scanner

        return Scanner(**kw)

    def _makeDiagnostics(self, **kw):
        from venusian import ScanDiagnostics

        return ScanDiagnostics(**kw)

    def _records_for(self, diagnostics, name):
        return [r for r in diagnostics.records if r.name == name]

    def test_reexported_object_explained(self):
        from tests.fixtures import two

        test = _Test()
        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne(test=test)
        scanner.scan(two, diagnostics=diagnostics)
        # the Class re-exported by tests.fixtures.two.mod2 is skipped
        # because its callback was defined in tests.fixtures.two.mod1
        skipped = [
            r
            for r in self._records_for(diagnostics, "Class")
            if r.outcome == "skipped"
        ]
        self.assertEqual(len(skipped), 1)
        record = skipped[0]
        self.assertEqual(record.module, "tests.fixtures.two.mod2")
        self.assertEqual(record.reason, "foreign-callback")
        self.assertEqual(record.defined_in, "tests.fixtures.two.mod1")
        # the original in mod1 was invoked
        invoked = [
            r
            for r in self._records_for(diagnostics, "Class")
            if r.outcome == "invoked"
        ]
        self.assertEqual(len(invoked), 1)
        self.assertEqual(invoked[0].module, "tests.fixtures.two.mod1")
        report = diagnostics.explain()
        self.assertIn("foreign-callback", report)
        self.assertIn("tests.fixtures.two.mod1", report)

    def test_ignored_module_explained(self):
        from tests.fixtures import one

        test = _Test()
        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne(test=test)
        scanner.scan(one, ignore=[".module2"], diagnostics=diagnostics)
        module_records = [r for r in diagnostics.records if r.name is None]
        self.assertEqual(len(module_records), 1)
        record = module_records[0]
        self.assertEqual(record.module, "tests.fixtures.one.module2")
        self.assertEqual(record.outcome, "skipped")
        self.assertEqual(record.reason, "ignored")
        # no object from the ignored module was considered
        self.assertEqual(
            [
                r
                for r in diagnostics.records
                if r.module == "tests.fixtures.one.module2" and r.name
            ],
            [],
        )
        report = diagnostics.explain()
        self.assertIn("ignored", report)
        self.assertIn("tests.fixtures.one.module2", report)

    def test_inherited_callback_explained(self):
        from tests.fixtures import subclassing

        test = _Test()
        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne(test=test)
        scanner.scan(subclassing, diagnostics=diagnostics)
        # Sub inherits Super's venusian callbacks; they are not attached
        # to Sub itself, so Sub is skipped
        sub_records = self._records_for(diagnostics, "Sub")
        self.assertEqual(len(sub_records), 1)
        record = sub_records[0]
        self.assertEqual(record.outcome, "skipped")
        self.assertEqual(record.reason, "attached-elsewhere")
        self.assertIn("Super", record.detail)
        # Super's own callbacks were invoked
        super_records = self._records_for(diagnostics, "Super")
        self.assertTrue(super_records)
        self.assertTrue(all(r.outcome == "invoked" for r in super_records))
        report = diagnostics.explain()
        self.assertIn("attached-elsewhere", report)

    def test_lifted_methods_recorded_as_lifted(self):
        from tests.fixtures import lifting1

        test = _Test()
        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne(test=test)
        scanner.scan(lifting1, diagnostics=diagnostics)
        sub_records = [
            r
            for r in self._records_for(diagnostics, "Sub")
            if r.outcome == "invoked"
        ]
        self.assertTrue(sub_records)
        self.assertTrue(all(r.lifted for r in sub_records))
        super_records = [
            r
            for r in self._records_for(diagnostics, "Super1")
            if r.outcome == "invoked"
        ]
        self.assertTrue(super_records)
        self.assertTrue(all(not r.lifted for r in super_records))

    def test_category_mismatch_explained(self):
        from tests.fixtures import category

        test = _Test()
        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne(test=test)
        scanner.scan(category, categories=("mycategory",), diagnostics=diagnostics)
        skipped = [
            r
            for r in self._records_for(diagnostics, "function2")
            if r.outcome == "skipped"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].reason, "category-mismatch")
        self.assertEqual(skipped[0].category, "mycategory2")
        invoked = [
            r
            for r in self._records_for(diagnostics, "function")
            if r.outcome == "invoked"
        ]
        self.assertEqual(len(invoked), 1)

    def test_callback_exception_not_conflated_with_skipped(self):
        from tests.fixtures import raising

        diagnostics = self._makeDiagnostics()
        scanner = self._makeOne()
        self.assertRaises(RuntimeError, scanner.scan, raising, diagnostics=diagnostics)
        records = self._records_for(diagnostics, "function")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.outcome, "error")
        self.assertEqual(record.reason, "callback-raised")
        self.assertIn("boom", record.detail)
        self.assertNotEqual(record.outcome, "skipped")
        report = diagnostics.explain()
        self.assertIn("error", report)
        self.assertIn("boom", report)

    def test_limit_truncates_and_marks(self):
        from tests.fixtures import one

        test = _Test()
        diagnostics = self._makeDiagnostics(limit=1)
        scanner = self._makeOne(test=test)
        scanner.scan(one, diagnostics=diagnostics)
        self.assertEqual(len(diagnostics.records), 1)
        self.assertTrue(diagnostics.truncated)
        self.assertTrue(diagnostics.dropped > 0)
        report = diagnostics.explain()
        self.assertIn("truncated", report)
        # scanning still worked despite truncation
        self.assertEqual(len(test.registrations), 6)

    def test_no_diagnostics_by_default(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        scanner.scan(one)
        self.assertEqual(len(test.registrations), 6)

    def test_record_repr_and_fullname(self):
        from venusian import ScanRecord

        record = ScanRecord(
            module="m",
            name="n",
            category="c",
            outcome="invoked",
            reason="invoked",
        )
        self.assertEqual(record.fullname, "m.n")
        self.assertIn("m.n", repr(record))
        mod_record = ScanRecord(
            module="m",
            name=None,
            category=None,
            outcome="skipped",
            reason="ignored",
        )
        self.assertEqual(mod_record.fullname, "m")


class Test_lift(unittest.TestCase):
    def _makeOne(self, categories=None):
        from venusian import lift

        return lift(categories)

    def test_not_class(self):
        inst = self._makeOne()
        self.assertRaises(RuntimeError, inst, None)


class Test_onlyliftedfrom(unittest.TestCase):
    def _makeOne(self):
        from venusian import onlyliftedfrom

        return onlyliftedfrom()

    def test_not_class(self):
        inst = self._makeOne()
        self.assertRaises(RuntimeError, inst, None)


def md(name):  # pragma: no cover
    if name in sys.modules:
        del sys.modules[name]
