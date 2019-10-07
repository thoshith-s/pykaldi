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

"""Tests for clif.testing.t4."""

import unittest
from clif.protos import ast_pb2
from clif.testing import nested_pb2
from clif.testing.python import t4


class T4Test(unittest.TestCase):

  def testProtoParam(self):
    pb = ast_pb2.AST()
    self.assertEqual(t4.Walk(pb), 0)
    self.assertEqual(t4.Size(pb), 0)

  def testProtoNestedParam(self):
    pb = ast_pb2.Decl()
    pb.decltype = pb.FUNC
    self.assertEqual(t4.DeclType(pb), pb.FUNC)
    self.assertEqual(t4.DeclTypeUI(pb), pb.FUNC)
    self.assertEqual(t4.DeclTypeUO(pb), pb.FUNC)

  def testProtoNestedMessage(self):
    pb = nested_pb2.Outer.Inner()
    pb.val = pb.B
    self.assertEqual(t4.nested(pb), pb.B)

  def testProtoVectorRaw(self):
    pbs = t4.all_ast_borrowed()
    self.assertEqual(len(pbs), 3)
    for a, b in zip(pbs, '123'):
      self.assertIsInstance(a, ast_pb2.AST)
      self.assertEqual(a.source, b)

  def testProtoVectorUniq(self):
    pbs = t4.all_ast_holds()
    self.assertEqual(len(pbs), 3)
    for a, b in zip(pbs, '123'):
      self.assertIsInstance(a, ast_pb2.AST)
      self.assertEqual(a.source, b)

  def testAsMessage(self):
    pbs = t4.all_ast_holds()
    self.assertEqual(len(pbs), 3)
    ast = pbs[0]
    self.assertIsInstance(ast, ast_pb2.AST)
    self.assertEqual(ast.DESCRIPTOR.full_name, 'clif.protos.AST')
    self.assertEqual(t4.ByteSize_R(ast), 3)
    self.assertEqual(t4.ByteSize_P(ast), 3)

  def testWrongMessageType(self):
    with self.assertRaises(TypeError):
      t4.Walk(ast_pb2.Decl())

  def testReturnSmartPtr(self):
    t4.GetUniquePtr(ast_pb2.Decl())
    t4.GetSharedPtr(ast_pb2.Decl())


if __name__ == '__main__':
  unittest.main()
