# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLIF Python extension module files generator.

Given a fully resolved (where resolver filled in C++ names) AST proto
Module can produces 3 output streams:
- base.cc with the bulk of wrapped code
- init.cc with .so initmodule function
- module.h with type conversion declarations to wrapped types
"""
# As this program translates from Python to C++ and presents it back to
# Python, it constantly operates in 3 realms:
# - Python language realm, where object has a Python name (pyname),
# - C++ language realm, where object has a fully qualified C++ name ([fq]cname)
# - Wrapper realm, where Python object has a C++ program name (wname)
# Keeping all 3 in mind while reading the code may be hard but neccesary.
# AST provides matched names from the first two realms and the code below
# creates a C++ output where the third realm emerges.
#
# Generate() traverse AST depth first, keeping nested C++ structures in
# self.nested stack. Each class creates a C++ namespace where the nessesary
# tables (methods, properties aka GetSet), structures (PyObject, PyTypeObject),
# and wrapper functions are created.
# So header m.h as
#   class A {
#     struct B { int x; };
#     void M();
#   };
# can create C++ module m as follows
#   namespace A {
#     struct wrapper { PyObject_HEAD std::shared_ptr<A> cpp; };
#     namespace B {
#       struct wrapper { PyObject_HEAD std::shared_ptr<B> cpp; };
#       _ get_x(_) { ... }
#       _ set_x(_) { ... }
#       PyGetSetDef Properties = {
#         {"x", get_x, set_x, ""},
#         {} };
#       PyTypeObject wrapper_Type = { ..., "_.A.B", ..., Properties, ... };
#     }  // B
#     _ wrapM(_ self, _ args) { ... }
#     PyMethodDef Methods = {
#       {"M", wrapM, METH_VARARGS, ""},
#       {} };
#     PyTypeObject wrapper_Type = { ..., "_.A", ..., Methods, ... };
#   } // A
#   Ready() {
#     PyType_Ready(A::B::wrapper_Type);
#     PyType_Ready(A::wrapper_Type);
#   }
#   Init(m) {
#     PyDict_SetItemString(A::wrapper_Type, "B", A::B::wrapper_Type);
#     PyModule_AddObject(m, "A", A::wrapper_Type);
#   }
#   initm() {
#     Ready();
#     m = PyModule_Create(...);
#     Init(m);
#   }
# and export a header file for other CLIF modules to use A and A.B
#   Clif_PyObjFrom(const A&);
#   Clif_PyObjFrom(const A::B&):
#   Clif_PyObjAs(_, A*);
#   Clif_PyObjAs(_, A::B*);
# to covert from Python classes A and A.B to/from C++ A, A::B.

import itertools
from clif.python import astutils
from clif.python import gen
from clif.python import postconv
from clif.python import slots
from clif.python import types

I = '  '  # Updated to match the desired value by the Module() constructor.
VARARGS = 'METH_VARARGS | METH_KEYWORDS'
NOARGS = 'METH_NOARGS'
VIRTUAL_OVERRIDER_CLASS = 'Overrider'
WRAPPER_CLASS_NAME = 'wrapper'
_ClassNamespace = lambda pyname: 'py' + pyname  # pylint: disable=invalid-name
_ITER_KW = '__iter__'


class Context(object):
  """Reflection of C++ [nested] class/struct."""
  WRAPPER_CLASS_NAME = 'wrapper'

  def __init__(self, cpp_class_name, python_user_class_name, fqclassname):
    self.name = cpp_class_name
    self.fqname = fqclassname
    self.pyname = python_user_class_name
    self.class_namespace = _ClassNamespace(self.pyname)
    self.methods = []  # (pyname, wrapper_name, METH_)
    self.properties = []  # var/const (pyname, wrapper, 'nullptr', '')
    self.dict = []  # (pyname, nested_pywrapper_cpp_name)
    self.final = False


def _GetCppObj(get='cpp', py='self'):
  """Get C++ member |get| from PyObject |py| which is a CLIF wrapper."""
  return 'reinterpret_cast<%s*>(%s)->%s' % (WRAPPER_CLASS_NAME, py, get)


class Module(object):
  """Extended context for module namespace."""

  def __init__(self, full_dotted_modname, typemap=(), for_py3=None, indent=I):
    global I
    if I != indent: I = gen.I = types.I = slots.I = indent
    if for_py3 is None:  # Get the value via our runtime environment.
      self.py3output = gen.PY3OUTPUT
    else:
      self.py3output = gen.PY3OUTPUT = for_py3
    self.path = full_dotted_modname
    self.modname = full_dotted_modname.rsplit('.', 1)[-1]
    assert self.modname, 'Module name should be a full.path.name'
    # Do a SWIG-like name mangling.
    uniq_name = full_dotted_modname.replace('_', '__').replace('.', '_')
    self.wrap_namespace = uniq_name + '_clifwrap'  # Allow static linking.
    self.typemap = {t.lang_type: t.postconversion
                    for t in typemap if t.postconversion}
    self.types_init = []  # _Type table (cppname, base class PyTypeObject, dict)
    self.types = set()    # types we wrap here (dups can arise from ie.
                          # wrapping std::function return params)
    self.enums = False    # enums are present
    self.init = []        # Extra init lines
    self.nested = []      # Stack of nested Context's
    self.catch_cpp_exceptions = False
    # common with Context
    self._dict = []       # constants, types, enums as (name, obj)
    self._methods = []
    self.ast_wrapper = {
        # pylint: disable=bad-whitespace
        'class_': self.WrapClass,
        'enum':   self.WrapEnum,
        'var':    self.WrapVar,
        'const':  self.WrapConst,
        'func':   self.WrapFunc,
        'fdecl':  self.WrapCapsule,
        }

  def __getattr__(self, name):
    if self.nested:
      return getattr(self.nested[-1], name)
    if name in ['methods', 'dict']:
      return getattr(self, '_'+name)
    raise AttributeError(self.__class__.__name__+' has no '+name)

  def Add(self, ctx):
    assert isinstance(ctx, Context), 'Add() got %s, wants Context' % type(ctx)
    self.nested.append(ctx)

  def DropContext(self):
    self.nested.pop()

  def CppName(self, name=None):
    if name:
      # Get FQ name in wrapper.
      fqn = [_ClassNamespace(f.pyname) for f in self.nested] + [name]
    else:
      # Get FQ current class name.
      fqn = (f.name for f in self.nested)
    return '::'.join(fqn)

  def WrapDecl(self, decl, parent_ns=''):
    """Process AST.Decl decl."""
    decl_type = decl.WhichOneof('decl')
    assert decl_type, 'decl_type not set in AST.Decl:\n' + str(decl)
    for s in (
        self.ast_wrapper[decl_type](getattr(decl, decl_type), decl.line_number,
                                    decl.namespace_ or parent_ns)
        ): yield s

  def WrapFunc(self, f, ln, unused_ns):
    """Process AST.FuncDecl f."""
    cname = Ident(f.name.cpp_name)
    assert cname, 'cpp_name is empty for ' + f.name.native
    pyname = f.name.native.rstrip('#')
    if pyname.endswith('@'):
      ctxmgr = pyname
      pyname = pyname[:-1]
    else:
      ctxmgr = None
    if self.nested and cname.startswith('operator'):
      wrapper_name = 'wrap' + pyname
    elif pyname == '__init__':
      wrapper_name = 'wrap' + types.Mangle(self.name) + '_as___init__'
    else:
      wrapper_name = 'wrap' + types.Mangle(cname)
      if pyname != cname:
        wrapper_name += '_as_' + pyname
    if f.ignore_return_value:
      assert len(f.returns) < 2, ('Func with ignore_return_value has too many'
                                  ' returns (%d)' % len(f.returns))
      del f.returns[:]
    for i, r in enumerate(f.returns):
      if r.type.HasField('callable'):
        for s in (
            self.WrapCallable(r.type, cname, i, ln)
            ): yield s
    self_param = f.params.pop(0) if f.cpp_opfunction else None
    if ctxmgr:
      assert not f.classmethod, "Context manager methods can't be static"
      # Force context manager args API.
      meth = VARARGS if ctxmgr == '__exit__@' else NOARGS
    else:
      meth = VARARGS if len(f.params) else NOARGS
    for s in gen.FunctionCall(
        # Keep '@' in method name to distinguish a ctxmgr.
        f.name.native.rstrip('#'), wrapper_name, func_ast=f, lineno=ln,
        call=self._FunctionCallExpr(f, cname, pyname),
        doc=next(astutils.Docstring(f)), prepend_self=self_param,
        catch=self.catch_cpp_exceptions and not f.cpp_noexcept,
        postcall_init=None, typepostconversion=self.typemap):
      yield s
    if f.classmethod:
      meth += ' | METH_CLASS'
    # Keep '#' in method name to distinguish map/seq slots.
    self.methods.append((f.name.native.rstrip('@'), wrapper_name, meth,
                         '\\n'.join(astutils.Docstring(f))))

  def _FunctionCallExpr(self, f, cname, pyname):
    """Find function call/postcall C++ expression."""
    call = f.name.cpp_name
    if self.nested and not f.classmethod:
      cpp = _GetCppObj()
      if f.constructor:
        assert not f.returns, cname+' ctor must return void'
        ctor = VIRTUAL_OVERRIDER_CLASS if f.virtual else self.fqname
        # Call Init(self) later in f.virtual _ctor to ensure we have GIL. It may
        # be released during __init__ C++ call.
        if pyname == '__init__':
          call = '%s = ::clif::MakeShared<%s>' % (cpp, ctor)
          # C++ constructors do not return anything.
          f.cpp_void_return = True
        else:  # additional ctors
          f.classmethod = True
          call = '::gtl::MakeUnique<%s>' % ctor
          # Pretend we're returning a new instance.
          r = f.returns.add()
          r.type.lang_type = self.pyname
          r.type.cpp_type = 'std::unique_ptr<%s>' % ctor
          f.cpp_void_return = False
      elif not f.cpp_opfunction:
        if self.final:
          call = cpp + '->' + cname
        else:
          call = ['%s* c = ThisPtr(self);' % self.fqname,
                  'if (!c) return nullptr;',
                  'c->' + (self.name + '::' if f.virtual else '') + cname]
    return call

  def WrapCallable(self, c, fname, retnum, line_number):
    """Process callable return type AST.Type c."""
    assert c.HasField('callable'), ('WrapCallable called on AST that has no'
                                    ' "callable":\n' + str(c))
    cname = Ident(c.callable.name.cpp_name) or fname+'_ret%d_lambda' % retnum
    wname = 'lambda_'+cname
    for i, r in enumerate(c.callable.returns):
      if r.type.HasField('callable'):
        for s in self.WrapCallable(r.type, cname, i, line_number):
          yield s
    if not c.cpp_type:
      assert c.callable, 'Non-callable param has empty cpp_type'
      c.cpp_type = 'std::function<%s>' % astutils.StdFuncParamStr(c.callable)
    for s in gen.FunctionCall(
        '', wname, doc=c.lang_type,
        catch=self.catch_cpp_exceptions and not c.callable.cpp_noexcept,
        call=['void* fp = PyCapsule_GetPointer(self, typeid(%s).name());'
              % c.cpp_type,
              'if (fp == nullptr) return nullptr;',
              '(*static_cast<%s*>(fp))' % c.cpp_type],
        postcall_init=None, typepostconversion=self.typemap,
        func_ast=c.callable, lineno=line_number): yield s
    defname = wname + '_def'
    yield gen.FromFunctionDef(c.cpp_type, defname, wname,
                              VARARGS if len(c.callable.params) else NOARGS,
                              'Calls '+c.cpp_type)
    self.types.add(types.CallableType(c.cpp_type, c.lang_type, defname))

  def WrapConst(self, c, unused_ln, unused_ns):
    """Process AST.ConstDecl c."""
    self.dict.append((c.name.native, 'Clif_PyObjFrom(%s, %s)' % (
        types.AsType(c.type.cpp_type, c.name.cpp_name),
        postconv.Initializer(c.type, self.typemap))))
    return []

  def WrapVar(self, v, unused_ln, unused_ns):
    """Process AST.VarDecl v."""
    assert self.nested, 'C++ global vars not allowed, use const'
    assert '::' not in v.name.cpp_name
    vname = v.name.cpp_name
    if v.cpp_set and not v.cpp_get:
      raise NameError('Property %s has setter, but no getter' % v.name.native)
    getter = 'get_' + vname
    setter = 'set_' + vname
    if self.final:
      base = None
      cobj = _GetCppObj() + '->'
    else:
      base = 'auto cpp = ThisPtr(self); if (!cpp) '
      cobj = 'cpp->'
    is_property = False
    if v.cpp_get.name.cpp_name:
      # It's a property var (with cpp only `getter`, `setter`).
      assert not v.cpp_get.name.native
      is_property = True
      if v.cpp_get.classmethod or v.cpp_set.classmethod:
        raise ValueError('Static properties not supported')
      if v.cpp_set.name.cpp_name:
        assert not v.cpp_set.name.native
      else:
        setter = 'nullptr'
      vname = Ident(v.cpp_get.name.cpp_name) + '()'
    cvar = cobj + vname
    unproperty = False
    if v.cpp_get.name.native:
      # It's an unproperty var (@getter pyname / @setter pyname).
      assert not v.cpp_get.name.cpp_name
      unproperty = True
      if v.cpp_get.docstring != '':
        docstring = '%s()->%s\\n\\n%s' % (v.cpp_get.name.native,
                                          v.type.lang_type, v.cpp_get.docstring)
      else:
        docstring = '%s()->%s  C++ %s.%s getter' % (
            v.cpp_get.name.native, v.type.lang_type, self.name, v.name.cpp_name)
      self.methods.append((v.cpp_get.name.native, getter, NOARGS, docstring))
      if v.cpp_set.name.native:
        assert not v.cpp_set.name.cpp_name
        if v.cpp_set.docstring != '':
          docstring = '%s(%s)\\n\\n%s' % (v.cpp_set.name.native,
                                          v.type.lang_type, v.cpp_set.docstring)
        else:
          docstring = '%s(%s)  C++ %s.%s setter' % (
            v.cpp_set.name.native, v.type.lang_type, self.name, v.name.cpp_name)
        self.methods.append((v.cpp_set.name.native, setter,
                             'METH_O', docstring))
      else:
        setter = 'nullptr'
    else:
      if v.cpp_get.docstring != '':
        docstring = v.cpp_get.docstring
      else:
        docstring = 'C++ %s %s.%s' % (v.type.cpp_type, self.CppName(), vname)
      self.properties.append((v.name.native, getter, setter, docstring))
    # For a nested container we'll try to return it (we use cpp_toptr_conversion
    # as an indicator for a custom container).
    for s in gen.VarGetter(getter, unproperty, base, cvar, _GetCppObj(),
                           pc=postconv.Initializer(v.type, self.typemap),
                           get_nested=(not is_property and not unproperty and
                                       v.type.cpp_toptr_conversion)): yield s
    if setter != 'nullptr':
      for s in gen.VarSetter(setter, unproperty, base, cvar, v,
                             cobj + Ident(v.cpp_set.name.cpp_name)
                             if v.cpp_set.name.cpp_name else '',
                             as_str=('PyUnicode_AsUTF8' if self.py3output else
                                     'PyString_AS_STRING')): yield s

  def WrapClass(self, c, unused_ln, cpp_namespace):
    """Process AST.ClassDecl c."""
    cname = Ident(c.name.cpp_name)
    pyname = c.name.native
    self.Add(Context(cname, pyname, c.name.cpp_name))
    ns = self.class_namespace
    yield ''
    yield 'namespace %s {' % ns
    virtual, has_iterator = _IsSpecialClass(c, pyname)
    if virtual:
      for s in gen.VirtualOverriderClass(
          VIRTUAL_OVERRIDER_CLASS, pyname,
          c.name.cpp_name, c.name.cpp_name+'::'+cname, c.cpp_abstract,
          Ident, vfuncs=virtual,
          pcfunc=lambda t, tm=self.typemap: postconv.Initializer(t, tm)):
        yield s
      c.bases.add().cpp_name = c.name.cpp_name
    # Flag that we're now in the nested __iter__ class.
    iter_class = (pyname == _ITER_KW)
    for s in gen.WrapperClassDef(
        WRAPPER_CLASS_NAME, is_iter=iter_class, has_iter=has_iterator,
        iter_ns=_ClassNamespace(_ITER_KW), cname=c.name.cpp_name,
        ctype=VIRTUAL_OVERRIDER_CLASS if virtual else c.name.cpp_name): yield s
    if iter_class:
      # Special-case nested __iter__ class.
      for s in _WrapIterSubclass(c.members, self.typemap):
        yield s
      tp_slots = {
          'tp_flags': ['Py_TPFLAGS_DEFAULT'],
          'tp_iter': 'PyObject_SelfIter',
          'tp_iternext': gen.IterNext.name}
      ctor = None
    else:
      # Normal class generator.
      if c.final:
        self.final = True
      else:
        yield 'static %s* ThisPtr(PyObject*);' % c.name.cpp_name
      ctor = ('DEF' if c.cpp_has_def_ctor and (not c.cpp_abstract or virtual)
              else None)
      for d in c.members:
        if d.decltype == d.FUNC:
          f = d.func
          if f.name.native == '__init__':
            if virtual:
              # Constructors are not virtual, but we mark the constructor as
              # virtual to indicate that there exist virtual functions in the
              # Clif class declaration.
              f.virtual = True
            if not f.params:
              continue  # Skip generating wrapper function for default ctor.
            ctor = 'wrap%s_as___init__' % types.Mangle(cname)
          elif c.cpp_abstract and f.virtual:
            continue  # Skip calling virtual func from the abstract base class.
        for s in self.WrapDecl(d, cpp_namespace):
          yield s
      if virtual and not ctor:
        raise ValueError(
            'A constructor should be declared in the Clif wrapper for %s as it '
            'has virtual method declarations.' % c.name.cpp_name)
      # For Py2 slots.py relies on Py_TPFLAGS_DEFAULT being set.
      tp_slots = {'tp_flags': ['Py_TPFLAGS_DEFAULT']}
      if c.cpp_abstract:
        tp_slots['tp_flags'].append('Py_TPFLAGS_IS_ABSTRACT')
      if not self.py3output:
        tp_slots['tp_flags'].append('Py_TPFLAGS_CHECKTYPES')
      if not c.final:
        tp_slots['tp_flags'].append('Py_TPFLAGS_BASETYPE')
      if has_iterator:
        n = _ClassNamespace(_ITER_KW)+'::'
        w = n + WRAPPER_CLASS_NAME
        # Python convention to have a type struct named FOO_Type.
        for s in gen.NewIter(_GetCppObj(), n, w, w+'_Type'):
          yield s
        tp_slots['tp_iter'] = gen.NewIter.name
      if self.properties:
        for s in gen.GetSetDef(self.properties):
          yield s
        tp_slots['tp_getset'] = gen.GetSetDef.name
      for b in c.bases:
        if b.cpp_name and not b.native:
          p = b.cpp_name
          w = 'as_' + types.Mangle(p)  # pyname == cname == w
          # Protect against duplicate bases.
          if not any(w == m[0] for m in self.methods):
            for s in gen.CastAsCapsule(_GetCppObj(), p, w):
              yield s
            self.methods.append((w, w, NOARGS, 'Upcast to %s*' % p))
      if self.methods:
        for s in slots.GenSlots(self.methods, tp_slots, py3=self.py3output):
          yield s
        if self.methods:  # If all methods are slots, it's empty.
          for s in gen.MethodDef(self.methods):
            yield s
          tp_slots['tp_methods'] = gen.MethodDef.name
          for name, wrapper_name, _, _ in self.methods:
              if name == '__call__':
                  tp_slots['tp_call'] = '(ternaryfunc)%s' % wrapper_name
    qualname = '.'.join(f.pyname for f in self.nested)
    tp_slots['tp_name'] = '"%s.%s"' % (self.path, qualname)
    if c.async_dtor and c.cpp_has_trivial_dtor:
      raise ValueError('Class %s has a trivial dtor yet @async__del__ decorator'
                       % pyname)
    # Python convention to have a type struct named FOO_Type.
    # Generate wrapper Type object in wname+'_Type' static var.
    for s in gen.TypeObject(
        tp_slots, slots.GenTypeSlots, pyname, ctor, docstring=c.docstring,
        fqclassname=c.name.cpp_name, wname=WRAPPER_CLASS_NAME,
        abstract=c.cpp_abstract, need_dtor=not c.cpp_has_trivial_dtor,
        iterator=_GetCppObj('iter') if iter_class else None,
        subst_cpp_ptr=VIRTUAL_OVERRIDER_CLASS if virtual else ''): yield s
    if not iter_class:
      for s in types.GenThisPointerFunc(
          c.name.cpp_name, WRAPPER_CLASS_NAME, c.final): yield s
    yield '}  // namespace ' + ns
    type_dict = self.dict
    wrapns = '::'.join(f.class_namespace for f in self.nested) + '::'
    wclass = wrapns + WRAPPER_CLASS_NAME
    vclass = wrapns + VIRTUAL_OVERRIDER_CLASS
    # Python convention to have a type struct named FOO_Type.
    wtype = wclass + '_Type'
    self.DropContext()
    base, cpp_replacement = _ProcessInheritance(c.bases, '::%s_Type'
                                                % WRAPPER_CLASS_NAME)
    self.types_init.append((wtype, base, type_dict))
    if iter_class:
      if base:
        raise TypeError("__iter__ class can't be derived, base '%s' found"
                        % base)
    else:
      self.dict.append((pyname, types.AsPyObj(wtype)))
      if cpp_replacement:
        # Find replacement class namespace.
        for b in c.cpp_bases:
          if b.name == cpp_replacement:
            cpp_namespace = b.namespace
            break
        else:
          cpp_namespace = ''
      self.types.add(
          types.ClassType(c.name.cpp_name, qualname, wclass, wtype, wrapns,
                          can_copy=c.cpp_copyable and not c.cpp_abstract,
                          can_destruct=c.cpp_has_public_dtor,
                          down_cast=cpp_replacement,
                          virtual=vclass if virtual else '',
                          ns=cpp_namespace))

  def WrapEnum(self, e, unused_ln, cpp_namespace):
    """Process AST.EnumDecl e."""
    # Enum(pyname, ((name, value),...))
    pytype = 'Enum' if e.enum_class else 'IntEnum'
    pystr = 'PyUnicode_FromString' if self.py3output else 'PyString_FromString'
    items = [('%s("%s")' % (pystr, m.native or Ident(m.cpp_name)),
              'PyInt_FromLong(\n%s%s)' % (4*I, types.AsType(
                  types.EnumIntType(e.name.cpp_name),
                  m.cpp_name if ':' in m.cpp_name  # FQN populated by matcher.
                  else e.name.cpp_name + '::' + m.cpp_name)),
             ) for m in e.members]
    assert items, 'matcher should populate enum members'
    wclass = '_'+e.name.native
    genw = 'wrap'+Ident(e.name.cpp_name)
    pyname = '.'.join([f.pyname for f in self.nested] + [e.name.native])
    t = types.EnumType(e.name.cpp_name, pyname, pytype, self.CppName(wclass),
                       cpp_namespace)
    self.types.add(t)
    self.dict.append((e.name.native,
                      '(%s=%s())' % (self.CppName(wclass), self.CppName(genw))))
    if not self.enums:
      self.enums = True
      self.init.extend([
          '{PyObject* em = PyImport_ImportModule("enum");',
          ' if (em == nullptr) goto err;',
          ' _Enum = PyObject_GetAttrString(em, "Enum");',
          ' _IntEnum = PyObject_GetAttrString(em, "IntEnum");',
          ' Py_DECREF(em);}',
          'if (!_Enum || !_IntEnum) {',
          I+'Py_XDECREF(_Enum);',
          I+'Py_XDECREF(_IntEnum);',
          I+'goto err;',
          '}'])
    yield ''
    for s in t.CreateEnum(genw, wclass, items, self.py3output):
      yield s

  def WrapCapsule(self, p, unused_ln, ns):
    """Process AST.ForwardDecl p."""
    self.types.add(types.CapsuleType(p.name.cpp_name, p.name.native, ns))
    return []

  def GenTypesReady(self):
    """Generate Ready() function to call PyType_Ready for wrapped types."""
    assert not self.nested, 'Stack was not fully processed'
    for cppname, _, dict_ in self.types_init:
      self.init.extend('if (PyDict_SetItemString(%s.tp_dict, "%s", %s) < 0)'
                       ' goto err;' % (cppname, n, o) for n, o in dict_)
    for s in gen.ReadyFunction(self.types_init):
      yield s

  def GenInitFunction(self, api_source_h, docstring):
    """Generate a function to create the module and initialize it."""
    assert not self.nested, 'Stack was not fully processed'
    if docstring == '':
      docstring = 'CLIF-generated module for %s' % api_source_h
    for s in gen.InitFunction(
        self.path, docstring,
        gen.MethodDef.name if self.methods else 'nullptr',
        self.init, self.dict): yield s

  def GenerateBase(self, ast, api_header, more_headers):
    """Extension module generation."""
    self.init += ast.extra_init
    for s in gen.Headlines(ast.source,
                           ['PYTHON',
                            'clif/python/ptr_util.h',
                            'clif/python/optional.h'] +
                           more_headers +
                           # Container templates calling PyObj* go last.
                           ['clif/python/stltypes.h',
                            'clif/python/slots.h'],
                           open_ns=self.wrap_namespace): yield s
    yield 'using namespace clif;'
    for s in postconv.GenPostConvTable(self.typemap):
      yield s
    if astutils.HaveEnum(ast.decls):
      yield ''
      yield 'static PyObject *_Enum{}, *_IntEnum{};  // set below in Init()'
    self.catch_cpp_exceptions = ast.catch_exceptions
    yield ''
    for d in ast.decls:
      for s in self.WrapDecl(d):
        yield s
    assert not self.nested, 'decl stack not exhausted (in GenBase)'
    yield ''
    yield ''
    yield '// Initialize module'
    if self.methods:
      for s in gen.MethodDef(self.methods):
        yield s
    for s in self.GenTypesReady():  # extends self.init
      yield s
    for s in self.GenInitFunction(api_header,
                                  ast.docstring):  # consumes self.init
      yield s
    yield ''
    yield '}  // namespace %s' % self.wrap_namespace
    if self.types:
      # Assumed we always want a deterministic output. Since dict/set order
      # is not, do sorted() order traversal.
      #
      # Save sorted types for GenerateHeader.
      self.types = sorted(self.types, key=types.Order)
      for ns, ts in itertools.groupby(self.types, types.Namespace):
        for s in gen.TypeConverters(
            ns, ts, self.wrap_namespace, self.py3output): yield s

  def GenerateInit(self, source_filename, skip_initfunc=False):
    """Generate module initialization file."""
    assert not self.nested, 'decl stack not exhausted (in GenInit)'
    for s in gen.Headlines(source_filename, ['PYTHON'],
                           open_ns=self.wrap_namespace): yield s
    yield ''
    yield 'bool Ready();'
    yield 'PyObject* Init();'
    yield ''
    yield '}  // namespace %s' % self.wrap_namespace
    if not skip_initfunc:
      for s in gen.PyModInitFunction(modname=self.modname, py3=self.py3output,
                                     ns=self.wrap_namespace): yield s

  def GenerateHeader(self, source_filename, api_header_filename, macros):
    """Generate header file with type conversion declarations."""
    for s in gen.Headlines(source_filename,
                           ['clif/python/optional.h', api_header_filename,
                            'clif/python/postconv.h'],
                           ['memory']): yield s
    if self.types:
      for ns, ts in itertools.groupby(self.types, types.Namespace):
        yield ''
        yield gen.OpenNs(ns)
        if ns and ns != 'clif':
          yield 'using namespace ::clif;'
        yield ''
        for t in ts:
          for s in t.GenHeader():
            yield s
        yield ''
        yield gen.CloseNs(ns)
      yield ''
      yield ('// CLIF init_module if (PyObject* m = PyImport_ImportModule('
             '"%s")) Py_DECREF(m);' % self.path)
      yield '// CLIF init_module else goto err;'
    else:
      yield '// This module defines no types.'
    for m in macros:
      yield ''
      yield '// CLIF macro %s %s' % (m.name, m.definition.replace('\n', r'\n'))


def _ProcessInheritance(bases, wrapped_type):
  """Get base class and "replacement" flag."""
  base = cpp_replacement = None
  if bases:
    # Pytd fills bases with native name (cpp_name='') for Python inheritance.
    # Matcher extends it with cpp_name (native=='') for C++ parent classes.
    base = [b.native for b in bases if b.native and not b.cpp_name]
    if base:
      if len(base) > 1:
        raise ValueError('Multiple inheritance not supported')
      base = base[0]
      if '.' not in base:
        # base defined in the same .clif wrapper
        base = _ClassNamespace(base) + wrapped_type
    elif bases[0].native == 'replacement':
      assert bases[0].cpp_name, 'A replacement class must have a `C++` name'
      cpp_replacement = bases[0].cpp_name
  return base, cpp_replacement


def _WrapIterSubclass(members, typemap):
  # Special-case nested __iter__ class.
  assert len(members) == 1, ('__iter__ class must have only one "def",'
                             ' %d members found' % len(members))
  d = members[0]
  assert d.decltype == d.FUNC, ('__iter__ class must have only one "def",'
                                ' %s member found' % d.decltype)
  assert d.func.name.native == '__next__', (
      '__iter__ class must have only one "def __next__", "def %s" found'
      % d.func.name.native)
  for s in gen.IterNext(_GetCppObj('iter'), not d.func.py_keep_gil,
                        postconv.Initializer(d.func.returns[0].type, typemap)):
    yield s


def _IsSpecialClass(c, pyname):
  """Get class properties."""
  # If class c has @virtual members, return a list of virtual functions.
  # If class c has a nested __iter__ class, return has_iterator=True.
  has_iterator = False
  virtual = []
  for d in c.members:
    if d.decltype == d.CLASS and d.class_.name.native == _ITER_KW:
      has_iterator = d.class_.name.cpp_name  # Cache `iterator` name.
    if d.decltype == d.FUNC and d.func.virtual:
      virtual.append(d.func)
    if virtual and c.final:
      raise ValueError("Final class %s can't have virtual methods." % pyname)
  return virtual, has_iterator


def Ident(cpp_name):
  _, fq, name = cpp_name.rpartition('::')
  return name if fq else cpp_name
