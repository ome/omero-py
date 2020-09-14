#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
   Copyright 2008-2020 The Open Microscopy Environment, Glencoe Software, Inc.
   All rights reserved.

   Use is subject to license terms supplied in LICENSE.txt
"""
from __future__ import print_function

import glob
import sys
import os

from setuptools import (
    Command,
    setup,
    find_packages,
)

try:
    from StringIO import StringIO
    from StringIO import StringIO as BytesIO
except ImportError:
    # Python 3
    from io import StringIO
    from io import BytesIO

from shutil import (
    copy,
    rmtree,
)

try:
    from urllib.request import urlopen
except ImportError:
    # Python 2
    from urllib import urlopen
from zipfile import ZipFile

try:
    import configparser
except ImportError:
    # Python 2
    import ConfigParser as configparser


def get_blitz_location():

    config_blitz_version = "5.5.5"

    # simplified strings
    defaultsect = configparser.DEFAULTSECT
    version_key = "versions.omero-blitz"
    url_key = "versions.omero-blitz-url"

    # detect if in Jenkins or not
    if "JENKINS_URL" in os.environ:
        config_blitz_url = os.environ.get("JENKINS_URL")
        config_blitz_url += "job/OMERO-build-build/lastSuccessfulBuild/"
        config_blitz_url += "artifact/omero-blitz/build/distributions/"
        config_blitz_url += "omero-blitz-VERSION-python.zip"
    else:
        config_blitz_url = (
            "https://artifacts.openmicroscopy.org/artifactory/ome.releases/"
            "org/openmicroscopy/omero-blitz/VERSION/"
            "omero-blitz-VERSION-python.zip")

    # load version.properties if available
    config_path = os.environ.get("VERSION_PROPERTIES",
                                 "artifact/version.properties")
    if os.path.exists(config_path):
        config_obj = configparser.RawConfigParser({
            url_key: config_blitz_url,
            version_key: config_blitz_version,
        })
        with open(config_path) as f:
            config_str = StringIO('[%s]\n%s' % (defaultsect, f.read()))
        config_obj.readfp(config_str)
        config_blitz_url = config_obj.get(defaultsect, url_key)
        config_blitz_version = config_obj.get(defaultsect, version_key)

    # replace VERSION in the final url and return
    config_blitz_url = config_blitz_url.replace(
        "VERSION", config_blitz_version)
    return config_blitz_url


def download_blitz_target():
    loc = get_blitz_location()
    print("Downloading %s ..." % loc, file=sys.stderr)
    resp = urlopen(loc)
    content = resp.read()
    content = BytesIO(content)
    zipfile = ZipFile(content)
    zipfile.extractall("target")


def _relative_symlink_file(src, dst):
    relsrc = os.path.relpath(src, os.path.dirname(dst))
    try:
        os.symlink(relsrc, dst)
        print(src, dst)
    except OSError as e:
        if e.errno != 17:
            raise
        os.remove(dst)
        os.symlink(relsrc, dst)


def copy_src_to_target(symlink=False):
    for dirpath, dirs, files in os.walk("src"):
        for filename in files:
            topath = dirpath.replace("src", "target", 1)
            if not os.path.exists(topath):
                os.makedirs(topath)
            fromfile = os.path.sep.join([dirpath, filename])
            tofile = os.path.sep.join([topath, filename])
            if symlink:
                _relative_symlink_file(fromfile, tofile)
            else:
                copy(fromfile, tofile)


# https://coderwall.com/p/3q_czg/custom-subcommand-at-setup-py
class DevTargetCommand(Command):
    """
    Recreate "target" with symlinks to files in "src" to ease development.

    For example, `pip install -e .` will work.
    Changes in files under "src" will be automatically seen in the installed
    module.

    If you add or remove files in src you must re-run both of these commands:

        python setup.py devtarget
        pip install -e .
    """

    description = (
        'Recreate target with symlinks to files in src to ease development')
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        rmtree('target')
        download_blitz_target()
        copy_src_to_target(symlink=True)
        print("If this is installed as an editable module re-run "
              "`pip install -e .`")


if not os.path.exists('target'):
    download_blitz_target()
    copy_src_to_target()


packageless = glob.glob("target/*.py")
packageless = [x[7:-3] for x in packageless]
packages = find_packages(where="target")

sys.path.append("target")
from omero_version import omero_version as ov  # noqa


def read(fname):
    """
    Utility function to read the README file.
    :rtype : String
    """
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="omero-py",
    version=ov,
    description="Python bindings to the OMERO.blitz server",
    long_description=read("README.rst"),
    classifiers=[
      'Development Status :: 5 - Production/Stable',
      'Intended Audience :: Developers',
      'Intended Audience :: Science/Research',
      'Intended Audience :: System Administrators',
      'License :: OSI Approved :: GNU General Public License v2 '
      'or later (GPLv2+)',
      'Natural Language :: English',
      'Operating System :: OS Independent',
      'Programming Language :: Python :: 3',
      'Topic :: Software Development :: Libraries :: Python Modules',
    ],  # Get strings from
        # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    author="The Open Microscopy Team",
    author_email="ome-devel@lists.openmicroscopy.org.uk",
    url='https://github.com/ome/omero-py',
    project_urls={
        'Documentation':
            'https://docs.openmicroscopy.org/omero/latest/developers/'
            'Python.html',
        'Bug tracker': 'https://github.com/ome/omero-py/issues',
    },
    package_dir={"": "target"},
    packages=packages,
    package_data={
        'omero.gateway': ['pilfonts/*'],
        'omero.gateway.scripts': ['imgs/*']},
    py_modules=packageless,
    entry_points={
        'console_scripts': ['omero=omero.main:main'],
    },
    python_requires='>=3',
    install_requires=[
        'appdirs',
        'future',
        'numpy',
        'Pillow',
        'PyYAML',
        'zeroc-ice>=3.6.4,<3.7',
        'pywin32; platform_system=="Windows"',
        'requests'
    ],
    tests_require=[
        'pytest',
        'mox3',
    ],
    cmdclass={
        'devtarget': DevTargetCommand,
    },
)
