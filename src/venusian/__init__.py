import sys
from inspect import getmembers, getmro, isclass
from pkgutil import iter_modules

from venusian.advice import getFrameInfo
from venusian.compat import compat_find_loader

ATTACH_ATTR = "__venusian_callbacks__"
LIFTONLY_ATTR = "__venusian_liftonly_callbacks__"


def _own_namespace(ob):
    """Return the object's own namespace (its ``__dict__``) without
    triggering any dynamic attribute machinery such as ``__getattr__``,
    ``__getattribute__`` overrides, or descriptors.  Returns ``None``
    when the object has no own namespace."""
    try:
        return object.__getattribute__(ob, "__dict__")
    except Exception:
        return None


def _static_mro(cls):
    """Return the MRO of ``cls`` without going through any metaclass
    ``__getattribute__`` hook."""
    try:
        return object.__getattribute__(cls, "__mro__")
    except Exception:  # pragma: nocover
        return (cls,)


def _static_unwrap_chain(ob):
    """Yield ``ob`` and each object it statically wraps.

    ``staticmethod`` and ``classmethod`` objects are unwrapped via their
    ``__func__`` (this is what the descriptor protocol would do when the
    member is accessed on a class).  ``__wrapped__`` links are followed
    only when they are present in the object's *own* namespace; arbitrary
    attribute access on the chain is never performed.  Cycles in the
    wrapping chain terminate the iteration instead of looping forever.
    """
    seen = set()
    current = ob
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        if isinstance(current, (staticmethod, classmethod)):
            try:
                current = current.__func__
            except Exception:  # pragma: nocover
                current = None
        else:
            namespace = _own_namespace(current)
            if namespace is None:
                current = None
            else:
                current = namespace.get("__wrapped__")


def _static_attached_categories(ob):
    """Statically look up Venusian attach categories on ``ob``.

    This mirrors what ``getattr(ob, ATTACH_ATTR)`` would find, but only
    consults real namespaces: for a class, the MRO is walked and the
    first class dictionary containing the attribute wins (Python's
    static lookup rule for same-name overrides); for any other object,
    only its own namespace is consulted.  Metaclass hooks, instance
    ``__getattr__`` and descriptors are never triggered.  Returns
    ``None`` when no categories are found.
    """
    if isclass(ob):
        # Inherited categories are found through the MRO exactly like
        # ``getattr`` would find them; the ``attached_to`` check performed
        # by the caller rejects categories that belong to a superclass,
        # just as it does in the default (dynamic) scan mode.  Categories
        # stored by ``onlyliftedfrom`` under LIFTONLY_ATTR are deliberately
        # not returned here: they must not fire for the class itself.
        for klass in _static_mro(ob):
            namespace = _own_namespace(klass)
            if namespace is not None and ATTACH_ATTR in namespace:
                return namespace[ATTACH_ATTR]
        return None
    namespace = _own_namespace(ob)
    if namespace is None:
        return None
    return namespace.get(ATTACH_ATTR)


def _static_class_members(cls):
    """Statically enumerate the members of a class.

    Members are collected from the class dictionaries of the MRO; the
    first definition of a name wins, which mirrors Python's static
    attribute lookup rules for same-name overrides.  Neither descriptors
    nor ``__getattr__`` hooks are triggered, and attributes contributed
    by the metaclass are not included.
    """
    members = []
    seen = set()
    for klass in _static_mro(cls):
        namespace = _own_namespace(klass)
        if namespace is None:  # pragma: nocover
            continue
        for name, member in namespace.items():
            if name in seen:
                continue
            seen.add(name)
            members.append((name, member))
    return members


class Scanner(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def scan(
        self,
        package,
        categories=None,
        onerror=None,
        ignore=None,
        static_members=False,
    ):
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

        .. versionadded:: 1.0a3
           the ``ignore`` argument

        The ``static_members`` argument switches member enumeration into
        a "static" mode.  When it is true, members of each scanned module
        are collected from the module's real namespace (its ``__dict__``)
        instead of via :func:`inspect.getmembers`, and Venusian
        attachments are discovered from actual namespaces and controlled
        MRO information rather than via :func:`getattr`.  This means the
        scan will not trigger module-level ``__getattr__`` hooks (PEP
        562), metaclass ``__getattr__`` hooks, or arbitrary descriptors
        while enumerating objects.  As a consequence, attributes that are
        generated dynamically (e.g. by a module ``__getattr__``) are not
        visible to a static scan; only real bindings are considered.

        In static mode, classes found in a module namespace additionally
        have their members enumerated statically: the MRO is walked and
        class dictionaries are merged with the first definition of a name
        winning (Python's static lookup rule for same-name overrides).
        ``staticmethod`` and ``classmethod`` objects are unwrapped to
        their underlying function, and ``__wrapped__`` links are followed
        only through real namespaces (never through arbitrary attribute
        access) with cycles terminating the chain.  Attachments made
        directly to methods (rather than during class body execution) can
        be found this way; existing ``lift``/``onlyliftedfrom`` metadata
        is honored exactly as in the default mode.

        Note that static member enumeration does not make imports static:
        modules and packages are still imported during the scan, and
        their top-level code still executes.  Only the enumeration of
        members and the lookup of Venusian attachments avoid dynamic
        attribute access.  The default (``static_members=False``) keeps
        the historical behavior.

        .. versionadded:: 3.2.0
           the ``static_members`` argument
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

        def invoke(mod_name, name, ob, attached_categories=None):
            fullname = mod_name + "." + name

            if _ignore(fullname):
                return False

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
                if attached_categories is None:
                    attached_categories = getattr(ob, ATTACH_ATTR)
                if not attached_categories.attached_to(mod_name, name, ob):
                    return False
            except:
                return False
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
                    return False
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
            return True

        if static_members:
            # Categories objects already fired for class members, so that
            # a member inherited through the MRO (or bound under several
            # names) does not fire its callbacks more than once per scan.
            fired_member_categories = set()
            enumerated_classes = set()

            def invoke_static(mod_name, name, ob):
                if _ignore(mod_name + "." + name):
                    return
                for unwrapped in _static_unwrap_chain(ob):
                    attached_categories = _static_attached_categories(unwrapped)
                    if attached_categories is not None:
                        invoke(mod_name, name, unwrapped, attached_categories)
                    if isclass(unwrapped):
                        if id(unwrapped) in enumerated_classes:
                            continue
                        enumerated_classes.add(id(unwrapped))
                        invoke_static_members(mod_name, name, unwrapped)

            def invoke_static_members(mod_name, class_name, cls):
                for member_name, member in _static_class_members(cls):
                    for unwrapped in _static_unwrap_chain(member):
                        attached_categories = _static_attached_categories(unwrapped)
                        if attached_categories is None:
                            continue
                        if id(attached_categories) in fired_member_categories:
                            continue
                        fullname = "%s.%s" % (class_name, member_name)
                        if invoke(mod_name, fullname, unwrapped, attached_categories):
                            fired_member_categories.add(id(attached_categories))

            def members_of(module):
                # Only real bindings of the module namespace are
                # considered; attributes generated dynamically through a
                # module __getattr__ are not enumerated.
                namespace = _own_namespace(module)
                if namespace is None:  # pragma: nocover
                    return []
                # snapshot: callbacks may mutate the module namespace
                return list(namespace.items())
        else:

            def invoke_static(mod_name, name, ob):
                invoke(mod_name, name, ob)

            def members_of(module):
                return getmembers(module)

        for name, ob in members_of(package):
            # whether it's a module or a package, we need to scan its
            # members; walk_packages only iterates over submodules and
            # subpackages
            invoke_static(pkg_name, name, ob)

        if hasattr(package, "__path__"):  # package, not module
            results = walk_packages(
                package.__path__,
                package.__name__ + ".",
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
                            for name, ob in members_of(module):
                                invoke_static(modname, name, ob)
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
