import sys
from inspect import getmembers, getmro, isclass
from pkgutil import iter_modules

from venusian.advice import getFrameInfo
from venusian.compat import compat_find_loader

ATTACH_ATTR = "__venusian_callbacks__"
LIFTONLY_ATTR = "__venusian_liftonly_callbacks__"


def _raw_namespace(ob):
    """Return the *real* namespace mapping of ``ob`` without invoking any
    descriptor protocol, ``__getattr__`` hook or other user code.

    For modules this is the module ``__dict__`` in which imports and module
    globals live; for classes it is the ``mappingproxy`` of the class body.
    Both expose a dictionary-like ``.get``.  Returns ``None`` when the object
    has no usable namespace (for example a built-in object).
    """
    try:
        return object.__getattribute__(ob, "__dict__")
    except AttributeError:
        return None


def _unwrap_descriptor(ob):
    """Unwrap a bare ``staticmethod``/``classmethod`` object.

    Only exact descriptor types are unwrapped.  A subclass may have overridden
    ``__func__`` to be an arbitrary descriptor, so retrieving it through the
    normal attribute protocol could execute user code; the subclass instance
    is therefore returned untouched.
    """
    if type(ob) is staticmethod or type(ob) is classmethod:
        try:
            return object.__getattribute__(ob, "__func__")
        except AttributeError:  # pragma: no cover
            return ob
    return ob


def _static_attached_categories(ob):
    """Discover Venusian categories attached to ``ob`` using only static
    namespace inspection.

    No attribute of ``ob`` is read through the normal attribute protocol, so
    neither data descriptors (including hostile metaclass descriptors) nor a
    module-level ``__getattr__`` (see :pep:`562`) are ever invoked.

    Only bindings that genuinely exist in the object's own namespace are
    considered: inherited ``__venusian_callbacks__`` mappings are deliberately
    ignored, matching the ordinary scan, which only processes attachments
    whose identity matches the resolved object.  Attachments placed on a
    function later wrapped by :func:`functools.wraps`-style decorators are
    still found by walking the ``__wrapped__`` chain, but the chain is read
    strictly from each hop's own namespace and loops terminate.

    Returns a ``(categories, resolved)`` tuple, or ``(None, ob)`` when no
    attachment was found.
    """
    ob = _unwrap_descriptor(ob)

    # Classes already carry the merged categories of their method-level
    # decorations in their own namespace (see ``attach`` and ``lift``);
    # walking __wrapped__ on a class would risk following a data descriptor
    # defined on the metaclass.
    if isclass(ob):
        namespace = _raw_namespace(ob)
        if namespace is not None:
            categories = namespace.get(ATTACH_ATTR, None)
            if categories is not None:
                return categories, ob
        return None, ob

    seen = set()
    current = ob
    while id(current) not in seen:
        seen.add(id(current))
        namespace = _raw_namespace(current)
        if namespace is None:
            break
        categories = namespace.get(ATTACH_ATTR, None)
        if categories is not None:
            return categories, current
        # Read __wrapped__ only from this hop's own namespace.  A descriptor
        # inherited from the type (or supplied by __getattr__) is never
        # invoked.
        current = namespace.get("__wrapped__", None)
        if current is None:
            break
    return None, ob


def _static_namespace_members(module):
    """Yield ``(name, value)`` pairs from a module's real namespace.

    This replaces :func:`inspect.getmembers` for static scans: it never calls
    ``dir()`` nor performs attribute access, so module ``__getattr__`` hooks
    and descriptors stored as module globals are never triggered.
    """
    namespace = _raw_namespace(module)
    if namespace is None:
        return
    try:
        items = list(namespace.items())
    except Exception:  # pragma: no cover - pathological module dict
        return
    for name, value in items:
        yield name, value


class Scanner(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def scan(self, package, categories=None, onerror=None, ignore=None, static=False):
        """Scan a Python package and any of its subpackages.  All
        top-level objects will be considered; those marked with
        venusian callback attributes related to ``category`` will be
        processed.

        The ``package`` argument should be a reference to a Python
        package or module object.

        The ``categories`` argument should be sequence of Venusian
        callback categories (each category usually a string) or the
        special value ``None`` which means all Venusian callback
        categories.  The default is ``None``.

        The ``onerror`` argument should either be ``None`` or a callback
        function which behaves the same way as the ``onerror`` callback
        function described in
        http://docs.python.org/library/pkgutil.html#pkgutil.walk_packages .
        By default, during a scan, Venusian will propagate all errors that
        happen during its code importing process, including
        :exc:`ImportError`.  If you use a custom ``onerror`` callback, you
        can change this behavior.

        Here's an example ``onerror`` callback that ignores
        :exc:`ImportError`::

            import sys
            def onerror(name):
                if not issubclass(sys.exc_info()[0], ImportError):
                    raise # reraise the last exception

        The ``name`` passed to ``onerror`` is the module or package dotted
        name that could not be imported due to an exception.

        .. versionadded:: 1.0
           the ``onerror`` callback

        The ``ignore`` argument allows you to ignore certain modules,
        packages, or global objects during a scan.  It should be a sequence
        containing strings and/or callables that will be used to match
        against the full dotted name of each object encountered during a
        scan.  The sequence can contain any of these three types of objects:

        - A string representing a full dotted name.  To name an object by
          dotted name, use a string representing the full dotted name.  For
          example, if you want to ignore the ``my.package`` package *and any
          of its subobjects or subpackages* during the scan, pass
          ``ignore=['my.package']``.

        - A string representing a relative dotted name.  To name an object
          relative to the ``package`` passed to this method, use a string
          beginning with a dot.  For example, if the ``package`` you've
          passed is imported as ``my.package``, and you pass
          ``ignore=['.mymodule']``, the ``my.package.mymodule`` mymodule *and
          any of its subobjects or subpackages* will be omitted during scan
          processing.

        - A callable that accepts a full dotted name string of an object as
          its single positional argument and returns ``True`` or ``False``.
          For example, if you want to skip all packages, modules, and global
          objects with a full dotted path that ends with the word "tests", you
          can use ``ignore=[re.compile('tests$').search]``.  If the callable
          returns ``True`` (or anything else truthy), the object is ignored,
          if it returns ``False`` (or anything else falsy) the object is not
          ignored.  *Note that unlike string matches, ignores that use a
          callable don't cause submodules and subobjects of a module or
          package represented by a dotted name to also be ignored, they match
          individual objects found during a scan, including packages,
          modules, and global objects*.

        You can mix and match the three types of strings in the list.  For
        example, if the package being scanned is ``my``,
        ``ignore=['my.package', '.someothermodule',
        re.compile('tests$').search]`` would cause ``my.package`` (and all
        its submodules and subobjects) to be ignored, ``my.someothermodule``
        to be ignored, and any modules, packages, or global objects found
        during the scan that have a full dotted name that ends with the word
        ``tests`` to be ignored.

        Note that packages and modules matched by any ignore in the list will
        not be imported, and their top-level code will not be run as a result.

        A string or callable alone can also be passed as ``ignore`` without a
        surrounding list.

        When ``static`` is true (it defaults to ``False`` for backwards
        compatibility), members are discovered *statically*: Venusian reads
        the real namespace dictionaries of modules and classes and the
        controlled method-resolution order instead of performing generic
        attribute access.  Consequently a module-level ``__getattr__`` (see
        :pep:`562`), data descriptors stored as module globals and hostile
        metaclass descriptors are never triggered just to enumerate objects.
        Genuine bindings, dynamically generated attributes and inherited
        members are distinguished the same way Python's own static lookup
        would: only attachments actually present on the resolved object's own
        namespace (or on a function reachable through a non-cyclic
        ``__wrapped__`` chain) are processed.  ``staticmethod`` and
        ``classmethod`` wrappers are unwrapped, and ``lift`` metadata already
        merged into a subclass is honored.

        Static scanning changes *how members are enumerated*, not how the
        package is loaded: submodules and packages are still imported so that
        their module code executes and their decorators run.  Objects of
        modules that are never imported cannot be discovered in either mode.

        .. versionadded:: 3.2.0
           the ``static`` argument

        .. versionadded:: 1.0a3
           the ``ignore`` argument
        """

        pkg_name = package.__name__

        if ignore is not None and (
            isinstance(ignore, str) or not hasattr(ignore, "__iter__")
        ):
            ignore = [ignore]
        elif ignore is None:
            ignore = []

        # non-leading-dotted name absolute object name
        str_ignores = [ign for ign in ignore if isinstance(ign, str)]
        # leading dotted name relative to scanned package
        rel_ignores = [ign for ign in str_ignores if ign.startswith(".")]
        # non-leading dotted names
        abs_ignores = [ign for ign in str_ignores if not ign.startswith(".")]
        # functions, e.g. re.compile('pattern').search
        callable_ignores = [ign for ign in ignore if callable(ign)]

        def _ignore(fullname):
            for ign in rel_ignores:
                if fullname.startswith(pkg_name + ign):
                    return True
            for ign in abs_ignores:
                # non-leading-dotted name absolute object name
                if fullname.startswith(ign):
                    return True
            for ign in callable_ignores:
                if ign(fullname):
                    return True
            return False

        def invoke(mod_name, name, ob):
            fullname = mod_name + "." + name

            if _ignore(fullname):
                return

            category_keys = categories
            try:
                # Some metaclasses do insane things when asked for an
                # ``ATTACH_ATTR``, like not raising an AttributeError but
                # some other arbitary exception.  Some even shittier
                # introspected code lets us access ``ATTACH_ATTR`` far but
                # barfs on a second attribute access for ``attached_to``
                # (still not raising an AttributeError, but some other
                # arbitrary exception).  Finally, the shittiest code of all
                # allows the attribute access of the ``ATTACH_ATTR`` *and*
                # ``attached_to``, (say, both ``ob.__getattr__`` and
                # ``attached_categories.__getattr__`` returning a proxy for
                # any attribute access), which either a) isn't callable or b)
                # is callable, but, when called, shits its pants in an
                # potentially arbitrary way (although for b, only TypeError
                # has been seen in the wild, from PyMongo).  Thus the
                # catchall except: return here, which in any other case would
                # be high treason.
                attached_categories = getattr(ob, ATTACH_ATTR)
                if not attached_categories.attached_to(mod_name, name, ob):
                    return
            except:
                return
            if category_keys is None:
                category_keys = list(attached_categories.keys())
                try:
                    # When metaclasses return proxies for any attribute access
                    # the list may contain keys of different types which might
                    # not be sortable.  In that case we can just return,
                    # because we're not dealing with a proper venusian
                    # callback.
                    category_keys.sort()
                except TypeError:  # pragma: no cover
                    return
            for category in category_keys:
                callbacks = attached_categories.get(category, [])
                try:
                    # Metaclasses might trick us by reaching this far and then
                    # fail with too little values to unpack.
                    for callback, cb_mod_name, liftid, scope in callbacks:
                        if cb_mod_name != mod_name:
                            # avoid processing objects that were imported into
                            # this module but were not actually defined there
                            continue
                        callback(self, name, ob)
                except ValueError:  # pragma: nocover
                    continue

        def static_invoke(mod_name, name, ob):
            fullname = mod_name + "." + name

            if _ignore(fullname):
                return

            attached_categories, resolved = _static_attached_categories(ob)
            if attached_categories is None:
                return
            try:
                if not attached_categories.attached_to(
                    mod_name, name, resolved
                ):
                    return
            except Exception:
                return

            category_keys = categories
            if category_keys is None:
                category_keys = list(attached_categories.keys())
                try:
                    category_keys.sort()
                except TypeError:  # pragma: no cover
                    return
            for category in category_keys:
                callbacks = attached_categories.get(category, [])
                try:
                    # As with the dynamic path, malformed callback tuples are
                    # ignored.
                    for callback, cb_mod_name, liftid, scope in callbacks:
                        if cb_mod_name != mod_name:
                            # avoid processing objects that were imported into
                            # this module but were not actually defined there
                            continue
                        callback(self, name, resolved)
                except ValueError:  # pragma: nocover
                    continue

        if static:
            invoke_members = _static_namespace_members
            invoke = static_invoke
        else:
            def invoke_members(namespace):
                return getmembers(namespace, None)

        for name, ob in invoke_members(package):
            # whether it's a module or a package, we need to scan its
            # members; walk_packages only iterates over submodules and
            # subpackages
            invoke(pkg_name, name, ob)

        package_namespace = _raw_namespace(package)
        package_path = (
            package_namespace.get("__path__", None)
            if package_namespace is not None
            else None
        )
        if static:
            is_package = package_path is not None
        else:
            is_package = hasattr(package, "__path__")  # package, not module

        if is_package:
            results = walk_packages(
                package_path if static else package.__path__,
                pkg_name + ".",
                onerror=onerror,
                ignore=_ignore,
            )

            for importer, modname, ispkg in results:
                loader = compat_find_loader(importer, modname)
                if loader is not None:  # happens on pypy with orphaned pyc
                    try:
                        get_filename = getattr(loader, "get_filename", None)
                        if get_filename is None:  # pragma: nocover
                            get_filename = loader._get_filename
                        try:
                            fn = get_filename(modname)
                        except TypeError:  # pragma: nocover
                            fn = get_filename()

                        # NB: use __import__(modname) rather than
                        # loader.load_module(modname) to prevent
                        # inappropriate double-execution of module code
                        try:
                            __import__(modname)
                        except Exception:
                            if onerror is not None:
                                onerror(modname)
                            else:
                                raise
                        module = sys.modules.get(modname)
                        if module is not None:
                            for name, ob in invoke_members(module):
                                invoke(modname, name, ob)
                    finally:
                        if hasattr(loader, "file") and hasattr(
                            loader.file, "close"
                        ):  # pragma: nocover
                            loader.file.close()


class AttachInfo(object):
    """
    An instance of this class is returned by the
    :func:`venusian.attach` function.  It has the following
    attributes:

    ``scope``

      One of ``exec``, ``module``, ``class``, ``function call`` or
      ``unknown`` (each a string).  This is the scope detected while
      executing the decorator which runs the attach function.

    ``module``

      The module in which the decorated function was defined.

    ``locals``

      A dictionary containing decorator frame's f_locals.

    ``globals``

      A dictionary containing decorator frame's f_globals.

    ``category``

      The ``category`` argument passed to ``attach`` (or ``None``, the
      default).

    ``codeinfo``

      A tuple in the form ``(filename, lineno, function, sourceline)``
      representing the context of the venusian decorator used.  Eg.
      ``('/home/chrism/projects/venusian/tests/test_advice.py', 81,
      'testCallInfo', 'add_handler(foo, bar)')``

    """

    def __init__(self, **kw):
        self.__dict__.update(kw)


class Categories(dict):
    def __init__(self, attached_to):
        super(dict, self).__init__()
        if isinstance(attached_to, tuple):
            self.attached_id = attached_to
        else:
            self.attached_id = id(attached_to)
        self.lifted = False

    def attached_to(self, mod_name, name, obj):
        if isinstance(self.attached_id, int):
            return self.attached_id == id(obj)
        return self.attached_id == (mod_name, name)


def attach(wrapped, callback, category=None, depth=1, name=None):
    """Attach a callback to the wrapped object.  It will be found
    later during a scan.  This function returns an instance of the
    :class:`venusian.AttachInfo` class.

    ``category`` should be ``None`` or a string representing a decorator
    category name.

    ``name`` should be ``None`` or a string representing a subcategory within
    the category.  This will be used by the ``lift`` class decorator to
    determine if decorations of a method should be inherited or overridden.
    """

    frame = sys._getframe(depth + 1)
    scope, module, f_locals, f_globals, codeinfo = getFrameInfo(frame)
    module_name = getattr(module, "__name__", None)
    wrapped_name = getattr(wrapped, "__name__", None)
    class_name = codeinfo[2]

    liftid = "%s %s" % (wrapped_name, name)

    if scope == "class":
        # we're in the midst of a class statement
        categories = f_locals.get(ATTACH_ATTR, None)
        if categories is None or not categories.attached_to(
            module_name, class_name, None
        ):
            categories = Categories((module_name, class_name))
            f_locals[ATTACH_ATTR] = categories
        callbacks = categories.setdefault(category, [])
    else:
        categories = getattr(wrapped, ATTACH_ATTR, None)
        if categories is None or not categories.attached_to(
            module_name, wrapped_name, wrapped
        ):
            # if there aren't any attached categories, or we've retrieved
            # some by inheritance, we need to create new ones
            categories = Categories(wrapped)
            setattr(wrapped, ATTACH_ATTR, categories)
        callbacks = categories.setdefault(category, [])

    callbacks.append((callback, module_name, liftid, scope))

    return AttachInfo(
        scope=scope,
        module=module,
        locals=f_locals,
        globals=f_globals,
        category=category,
        codeinfo=codeinfo,
    )


def walk_packages(path=None, prefix="", onerror=None, ignore=None):
    """Yields (module_loader, name, ispkg) for all modules recursively
    on path, or, if path is None, all accessible modules.

    'path' should be either None or a list of paths to look for
    modules in.

    'prefix' is a string to output on the front of every module name
    on output.

    Note that this function must import all *packages* (NOT all
    modules!) on the given path, in order to access the __path__
    attribute to find submodules.

    'onerror' is a function which gets called with one argument (the name of
    the package which was being imported) if any exception occurs while
    trying to import a package.  If no onerror function is supplied, any
    exception is exceptions propagated, terminating the search.

    'ignore' is a function fed a fullly dotted name; if it returns True, the
    object is skipped and not returned in results (and if it's a package it's
    not imported).

    Examples:

    # list all modules python can access
    walk_packages()

    # list all submodules of ctypes
    walk_packages(ctypes.__path__, ctypes.__name__+'.')

    # NB: we can't just use pkgutils.walk_packages because we need to ignore
    # things
    """

    def seen(p, m={}):
        if p in m:  # pragma: no cover
            return True
        m[p] = True

    # iter_modules is nonrecursive
    for importer, name, ispkg in iter_modules(path, prefix):
        if ignore is not None and ignore(name):
            # if name is a package, ignoring here will cause
            # all subpackages and submodules to be ignored too
            continue

        # do any onerror handling before yielding

        if ispkg:
            try:
                __import__(name)
            except Exception:
                if onerror is not None:
                    onerror(name)
                else:
                    raise
            else:
                yield importer, name, ispkg
                path = getattr(sys.modules[name], "__path__", None) or []

                # don't traverse path items we've seen before
                path = [p for p in path if not seen(p)]

                for item in walk_packages(path, name + ".", onerror, ignore):
                    yield item
        else:
            yield importer, name, ispkg


class lift(object):
    """
    A class decorator which 'lifts' superclass venusian configuration
    decorations into subclasses.  For example::

      from venusian import lift
      from somepackage import venusian_decorator

      class Super(object):
          @venusian_decorator()
          def boo(self): pass

          @venusian_decorator()
          def hiss(self): pass

          @venusian_decorator()
          def jump(self): pass

      @lift()
      class Sub(Super):
          def boo(self): pass

          def hiss(self): pass

          @venusian_decorator()
          def smack(self): pass

    The above configuration will cause the callbacks of seven venusian
    decorators.  The ones attached to Super.boo, Super.hiss, and Super.jump
    *plus* ones attached to Sub.boo, Sub.hiss, Sub.hump and Sub.smack.

    If a subclass overrides a decorator on a method, its superclass decorators
    will be ignored for the subclass.  That means that in this configuration::

      from venusian import lift
      from somepackage import venusian_decorator

      class Super(object):
          @venusian_decorator()
          def boo(self): pass

          @venusian_decorator()
          def hiss(self): pass

      @lift()
      class Sub(Super):

          def boo(self): pass

          @venusian_decorator()
          def hiss(self): pass

    Only four, not five decorator callbacks will be run: the ones attached to
    Super.boo and Super.hiss, the inherited one of Sub.boo and the
    non-inherited one of Sub.hiss.  The inherited decorator on Super.hiss will
    be ignored for the subclass.

    The ``lift`` decorator takes a single argument named 'categories'.  If
    supplied, it should be a tuple of category names.  Only decorators
    in this category will be lifted if it is suppled.

    """

    def __init__(self, categories=None):
        self.categories = categories

    def __call__(self, wrapped):
        if not isclass(wrapped):
            raise RuntimeError(
                '"lift" only works as a class decorator; you tried to use '
                "it against %r" % wrapped
            )
        frame = sys._getframe(1)
        scope, module, f_locals, f_globals, codeinfo = getFrameInfo(frame)
        module_name = getattr(module, "__name__", None)
        newcategories = Categories(wrapped)
        newcategories.lifted = True
        for cls in getmro(wrapped):
            attached_categories = cls.__dict__.get(ATTACH_ATTR, None)
            if attached_categories is None:
                attached_categories = cls.__dict__.get(LIFTONLY_ATTR, None)
            if attached_categories is not None:
                for cname, category in attached_categories.items():
                    if cls is not wrapped:
                        if self.categories and not cname in self.categories:
                            continue
                    callbacks = newcategories.get(cname, [])
                    newcallbacks = []
                    for cb, _, liftid, cscope in category:
                        append = True
                        toappend = (cb, module_name, liftid, cscope)
                        if cscope == "class":
                            for ncb, _, nliftid, nscope in callbacks:
                                if nscope == "class" and liftid == nliftid:
                                    append = False
                        if append:
                            newcallbacks.append(toappend)
                    newcategory = list(callbacks) + newcallbacks
                    newcategories[cname] = newcategory
                if attached_categories.lifted:
                    break
        if newcategories:  # if it has any keys
            setattr(wrapped, ATTACH_ATTR, newcategories)
        return wrapped


class onlyliftedfrom(object):
    """
    A class decorator which marks a class as 'only lifted from'.  Decorations
    made on methods of the class won't have their callbacks called directly,
    but classes which inherit from only-lifted-from classes which also use the
    ``lift`` class decorator will use the superclass decoration callbacks.

    For example::

      from venusian import lift, onlyliftedfrom
      from somepackage import venusian_decorator

      @onlyliftedfrom()
      class Super(object):
          @venusian_decorator()
          def boo(self): pass

          @venusian_decorator()
          def hiss(self): pass

      @lift()
      class Sub(Super):

          def boo(self): pass

          def hiss(self): pass

    Only two decorator callbacks will be run: the ones attached to Sub.boo and
    Sub.hiss.  The inherited decorators on Super.boo and Super.hiss will be
    not be registered.
    """

    def __call__(self, wrapped):
        if not isclass(wrapped):
            raise RuntimeError(
                '"onlyliftedfrom" only works as a class decorator; you tried '
                "to use it against %r" % wrapped
            )
        cats = getattr(wrapped, ATTACH_ATTR, None)
        class_name = wrapped.__name__
        module_name = wrapped.__module__
        key = (module_name, class_name, wrapped)
        if cats is None or not cats.attached_to(*key):
            # we either have no categories or our categories are defined
            # in a superclass
            return
        delattr(wrapped, ATTACH_ATTR)
        setattr(wrapped, LIFTONLY_ATTR, cats)
        return wrapped
