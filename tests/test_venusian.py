import contextlib
import os
import re
import sys
import tempfile
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

    def _make_fresh_module(self, name, source):
        """Import a module written to a private temporary directory.

        Using a real source file (instead of ``exec``) lets
        ``venusian.attach`` recognise the module scope correctly.
        """
        import importlib
        import shutil

        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, name + ".py"), "w") as f:
            f.write(source)
        sys.path.insert(0, tmpdir)

        def cleanup():
            sys.modules.pop(name, None)
            sys.path.remove(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.addCleanup(cleanup)
        return importlib.import_module(name)

    _COLLECT_SOURCE = (
        "import venusian\n"
        "class register(object):\n"
        "    def __init__(self, marker):\n"
        "        self.marker = marker\n"
        "    def __call__(self, wrapped):\n"
        "        marker = self.marker\n"
        "        def callback(scanner, name, ob):\n"
        "            scanner.marks.append(marker)\n"
        "        venusian.attach(wrapped, callback)\n"
        "        return wrapped\n"
        "@register('first')\n"
        "def registered_function():\n"
        "    pass\n"
    )

    def test_collect_does_not_invoke_callbacks(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        plan = scanner.collect(one)
        self.assertEqual(test.registrations, [])
        self.assertGreater(len(plan), 0)

    def test_collect_then_execute_matches_scan(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        plan = scanner.collect(one)
        scanner.execute(plan)

        test2 = _Test()
        scanner2 = self._makeOne(test=test2)
        scanned_plan = scanner2.scan(one)

        self.assertEqual(len(plan), len(test.registrations))
        self.assertEqual(len(plan), len(scanned_plan))
        self.assertEqual(
            [e.fullname for e in plan], [e.fullname for e in scanned_plan]
        )
        self.assertEqual(test.registrations, test2.registrations)

    def test_collect_uses_categories(self):
        from tests.fixtures import category

        scanner = self._makeOne()
        plan = scanner.collect(category, categories=("mycategory",))
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].name, "function")
        self.assertEqual(plan[0].category, "mycategory")
        self.assertEqual(plan[0].cb_mod_name, category.__name__)
        self.assertEqual(plan[0].ob, category.function)
        self.assertIn(category.__name__ + ".function", repr(plan[0]))

    def test_collect_respects_ignore(self):
        from tests.fixtures import one

        scanner = self._makeOne()
        plan = scanner.collect(
            one, ignore=[re.compile("module2$").search]
        )
        fullnames = [e.fullname for e in plan]
        self.assertTrue(fullnames)
        self.assertTrue(
            all("module2" not in fullname for fullname in fullnames), fullnames
        )

    def test_collect_still_imports_modules(self):
        marker = os.path.join(tempfile.mkdtemp(), "imported.marker")
        import shutil

        self.addCleanup(shutil.rmtree, os.path.dirname(marker), True)
        source = (
            "import os\n"
            "import venusian\n"
            "class noop(object):\n"
            "    def __call__(self, wrapped):\n"
            "        venusian.attach(wrapped, lambda s, n, o: None)\n"
            "        return wrapped\n"
            "open(%r, 'w').close()\n"
            "@noop()\n"
            "def imported_function():\n"
            "    pass\n"
        )
        source = source % marker
        module = self._make_fresh_module(
            "venusian_collect_import_sideeffect", source
        )
        scanner = self._makeOne()
        plan = scanner.collect(module)
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(len(plan), 1)

    def test_later_attach_does_not_change_collected_plan(self):
        name = "venusian_collect_late_attach_test"
        module = self._make_fresh_module(name, self._COLLECT_SOURCE)

        scanner = self._makeOne(marks=[])
        plan = scanner.collect(module)
        self.assertEqual(len(plan), 1)

        # emulate more decoration of an additional object within the
        # scanned module (the callback's source module must be the scanned
        # module itself, as with normal decorator usage)
        late_source = (
            "def late_function():\n"
            "    pass\n"
            "late_function = register('late')(late_function)\n"
        )
        exec(compile(late_source, "<late:%s>" % name, "exec"), module.__dict__)

        scanner.execute(plan)
        self.assertEqual(scanner.marks, ["first"])

        rescanned = scanner.collect(module)
        self.assertEqual(len(rescanned), 2)
        scanner.execute(rescanned)
        self.assertEqual(sorted(scanner.marks), ["first", "first", "late"])

    def test_execute_uses_snapshotted_binding_and_skips_stale_object(self):
        from venusian import StaleCallbackError

        name = "venusian_collect_stale_object_test"
        module = self._make_fresh_module(name, self._COLLECT_SOURCE)
        original = module.registered_function

        scanner = self._makeOne(marks=[])
        plan = scanner.collect(module)

        def replacement():
            pass

        module.registered_function = replacement

        # default: stale entries are skipped
        scanner.execute(plan)
        self.assertEqual(scanner.marks, [])

        # explicit skip policy behaves the same way
        scanner.execute(plan, onstale="skip")
        self.assertEqual(scanner.marks, [])

        # raise policy surfaces the stale binding
        with self.assertRaises(StaleCallbackError) as cm:
            scanner.execute(plan, onstale="raise")
        self.assertIs(cm.exception.entry, plan[0])
        self.assertIn("replaced", cm.exception.reason)

        # a callable policy may force execution with the snapshot anyway
        scanner.execute(plan, onstale=lambda entry, reason: False)
        self.assertEqual(scanner.marks, ["first"])

        # restoring the original binding makes the entry current again
        module.registered_function = original
        scanner.execute(plan)
        self.assertEqual(scanner.marks, ["first", "first"])

    def test_execute_skips_entry_when_module_removed(self):
        from venusian import StaleCallbackError

        name = "venusian_collect_missing_module_test"
        module = self._make_fresh_module(name, self._COLLECT_SOURCE)

        scanner = self._makeOne(marks=[])
        plan = scanner.collect(module)
        del sys.modules[name]

        scanner.execute(plan)
        self.assertEqual(scanner.marks, [])

        stale_entries = []

        def record(entry, reason):
            stale_entries.append((entry, reason))
            return True

        scanner.execute(plan, onstale=record)
        self.assertEqual(len(stale_entries), 1)
        self.assertIs(stale_entries[0][0], plan[0])
        self.assertIn("removed", stale_entries[0][1])
        with self.assertRaises(StaleCallbackError):
            scanner.execute(plan, onstale="raise")

    def test_execute_rejects_bad_onstale(self):
        from tests.fixtures import one

        scanner = self._makeOne(test=_Test())
        plan = scanner.collect(one)
        self.assertRaises(ValueError, scanner.execute, plan, "bogus")

    def test_scan_returns_executed_plan(self):
        from tests.fixtures import one

        test = _Test()
        scanner = self._makeOne(test=test)
        plan = scanner.scan(one)
        self.assertEqual(len(plan), len(test.registrations))
        self.assertEqual(
            [e.fullname for e in plan],
            sorted(
                "%s.%s" % (kw["ob"].__module__, kw["name"])
                for kw in test.registrations
            ),
        )

    def test_collect_lift_matches_scan(self):
        from tests.fixtures import lifting1

        test = _Test()
        scanner = self._makeOne(test=test)
        plan = scanner.collect(lifting1)
        scanner.execute(plan)
        self.assertEqual(len(plan), 11)
        self.assertEqual(len(test.registrations), 11)


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
