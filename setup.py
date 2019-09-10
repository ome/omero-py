#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
   Copyright 2008-2019 The Open Microscopy Environment, Glencoe Software, Inc.
   All rights reserved.

   Use is subject to license terms supplied in LICENSE.txt
"""


import glob
import sys
import os

from setuptools import setup, find_packages

from StringIO import StringIO
from shutil import copy
from urllib import urlopen
from zipfile import ZipFile

import ConfigParser


def get_blitz_location():
    defaultsect = ConfigParser.DEFAULTSECT
    version_key = "versions.omero-blitz"
    url_key = "versions.omero-blitz-url"

    config_blitz_url = ("https://artifacts.openmicroscopy.org/artifactory/"
                        "ome.releases/org/openmicroscopy/omero-blitz/VERSION/"
                        "omero-blitz-VERSION-python.zip")
    config_blitz_version = "5.5.3"
    config_path = os.environ.get("VERSION_PROPERTIES", "version.properties")
    if os.path.exists(config_path):
        config_obj = ConfigParser.RawConfigParser({
            url_key: config_blitz_url,
            version_key: config_blitz_version,
        })
        with open(config_path) as f:
            config_str = StringIO('[%s]\n%s' % (defaultsect, f.read()))
        config_obj.readfp(config_str)
        config_blitz_url = config_obj.get(defaultsect, url_key)
        config_blitz_version = config_obj.get(defaultsect, version_key)
    config_blitz_url = config_blitz_url.replace("VERSION", config_blitz_version)
    return config_blitz_url

if not os.path.exists("target"):
    resp = urlopen(get_blitz_location())
    content = resp.read()
    zipfile = ZipFile(StringIO(content))
    zipfile.extractall("target")

    for dirpath, dirs, files in os.walk("src"):
        for filename in files:
            topath = dirpath.replace("src", "target", 1)
            if not os.path.exists(topath):
                os.makedirs(topath)
            fromfile = os.path.sep.join([dirpath, filename])
            tofile = os.path.sep.join([topath, filename])
            copy(fromfile, tofile)


packageless = glob.glob("target/*.py")
packageless = [x[7:-3] for x in packageless]
packages = find_packages(where="target")

url = 'https://docs.openmicroscopy.org/latest/omero/developers'

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
      'Programming Language :: Python :: 2',
      'Topic :: Software Development :: Libraries :: Python Modules',
    ],  # Get strings from
        # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    author="The Open Microscopy Team",
    author_email="ome-devel@lists.openmicroscopy.org.uk",
    url=url,
    package_dir={"": "target/"},
    packages=packages,
    package_data={
        'omero.gateway': ['pilfonts/*'],
        'omero.gateway.scripts': ['imgs/*']},
    py_modules=packageless,
    scripts=glob.glob(os.path.sep.join(["bin", "*"])),
    install_requires=[
        'zeroc-ice>=3.6.4,<3.7',
    ],
    tests_require=['pytest<3'])
