#!/usr/bin/env python
#
# Copyright 2014 Major Hayden
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
"""Install osa-differ."""
import sys


from setuptools import setup


required_packages = [
    "GitPython",
    "jinja2",
    "PyYAML",
    "requests"
]

if sys.version_info < (2, 7):
    required_packages.append("importlib")

setup(
    name='osa_differ',
    version='0.3.8',
    author='Major Hayden',
    author_email='major@mhtx.net',
    description="Find changes between OpenStack-Ansible versions",
    install_requires=required_packages,
    packages=['osa_differ'],
    include_package_data=True,
    url='https://github.com/rcbops/osa-differ',
    entry_points='''
        [console_scripts]
        osa-differ = osa_differ.osa_differ:run_osa_differ
    '''
)
