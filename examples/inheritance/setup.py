#!/usr/bin/env python
#
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Setup configuration."""

import os
import platform

try:
  import setuptools
except ImportError:
  from ez_setup import use_setuptools
  use_setuptools()
  import setuptools

py_version = platform.python_version_tuple()
if py_version < ('2', '7') or py_version[0] == '3' and py_version < ('3', '4'):
  raise RuntimeError('Python version 2.7 or 3.4+ required')

user_home = os.getenv('HOME')

setuptools.setup(
    name='pyclif_example_inheritance',
    version='1.0',
    description='Python CLIF hidden_base example',
    url='https://github.com/google/clif',
    author='CLIF authors',
    author_email='pyclif@googlegroups.com',
    install_requires=['enum34;python_version<"3.4"'],
    ext_modules=[
        setuptools.Extension(
            'hidden_base', [
                # CLIF-generated sources
                'python/hidden_base.cc',
                'python/hidden_base_init.cc',
                # 'clif_runtime',
                user_home + '/opt/clif/python/runtime.cc',
                user_home + '/opt/clif/python/slots.cc',
                user_home + '/opt/clif/python/types.cc',
                ],
            include_dirs=[
                # Path to clif runtime headers
                user_home + '/opt',
                # Path to examples in CLIF installation.
                user_home + '/opt/clif/examples',
                ],
            extra_compile_args=['-std=c++11'],
            ),
        setuptools.Extension(
            'base', [
                # CLIF-generated sources
                'python/base.cc',
                'python/base_init.cc',
                # 'clif_runtime',
                user_home + '/opt/clif/python/runtime.cc',
                user_home + '/opt/clif/python/slots.cc',
                user_home + '/opt/clif/python/types.cc',
                ],
            include_dirs=[
                # Path to clif runtime headers
                user_home + '/opt',
                # Path to examples in CLIF installation.
                user_home + '/opt/clif/examples',
                ],
            extra_compile_args=['-std=c++11'],
            ),
        setuptools.Extension(
            'python_inheritance', [
                # CLIF-generated sources
                'python/python_inheritance.cc',
                'python/python_inheritance_init.cc',
                # 'clif_runtime',
                user_home + '/opt/clif/python/runtime.cc',
                user_home + '/opt/clif/python/slots.cc',
                user_home + '/opt/clif/python/types.cc',
                ],
            include_dirs=[
                # Path to clif runtime headers
                user_home + '/opt',
                # Path to examples in CLIF installation.
                user_home + '/opt/clif/examples',
                ],
            extra_compile_args=['-std=c++11'],
            ),
        setuptools.Extension(
            'inheritance', [
                # CLIF-generated sources
                'python/inheritance.cc',
                'python/inheritance_init.cc',
                # 'clif_runtime',
                user_home + '/opt/clif/python/runtime.cc',
                user_home + '/opt/clif/python/slots.cc',
                user_home + '/opt/clif/python/types.cc',
                ],
            include_dirs=[
                # Path to clif runtime headers
                user_home + '/opt',
                # Path to examples in CLIF installation.
                user_home + '/opt/clif/examples',
                ],
            extra_compile_args=['-std=c++11'],
            ),
        setuptools.Extension(
            'operation', [
                # CLIF-generated sources
                'python/operation.cc',
                'python/operation_init.cc',
                # 'clif_runtime',
                user_home + '/opt/clif/python/runtime.cc',
                user_home + '/opt/clif/python/slots.cc',
                user_home + '/opt/clif/python/types.cc',
                ],
            include_dirs=[
                # Path to clif runtime headers
                user_home + '/opt',
                # Path to examples in CLIF installation.
                user_home + '/opt/clif/examples',
                ],
            extra_compile_args=['-std=c++11'],
            ),
        ],
    )
