#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
   setuptools entry point

   Tests run by default using the OmeroPy/dist egg as the omero python lib but
   you can override that by using the --test-pythonpath flag to ./setup.py
   test.

   For testing that require a running Omero server, the ice.config file must
   exist and hold the proper configuration either at the same directory as
   this file or in some place pointed to by the --test-ice-config flag to
   ./setup.py test.

   For example:

      # this will run all tests under OmeroPy/test/
      ./setup.py test
       # run all tests under OmeroPy/test/gatewaytest
      ./setup.py test -s test/gatewaytest
      # run all tests that include TopLevelObjects in the name
      ./setup.py test -k TopLevelObjects
      # exit on first failure
      ./setup.py test -x
      # drop to the pdb debugger on failure
      ./setup.py test --pdb


   Copyright 2007-2016 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import glob
import sys
import os

sys.path.append("src")
from omero_setup import PyTest

from setuptools import setup, find_packages
from omero_version import omero_version as ov

from StringIO import StringIO
from hashlib import md5
from urllib import urlopen
from zipfile import ZipFile

blitz_zip = "https://artifacts.openmicroscopy.org/artifactory/ome.releases/org/openmicroscopy/omero-blitz/5.5.3/omero-blitz-5.5.3-python.zip"
blitz_md5 = "cf9c0cd4b2e499fc3b4b8be8c58ab6cb"


if not os.path.exists("target"):
    resp = urlopen(blitz_zip)
    content = resp.read()
    md5 = md5(content).hexdigest()
    assert md5 == blitz_md5
    zipfile = ZipFile(StringIO(content))
    zipfile.extractall("target")


packages = find_packages("target")+[""]
url = 'https://docs.openmicroscopy.org/latest/omero/developers'

setup(
    name="omero-py",
    version=ov,
    description="Python bindings to the OMERO.blitz server",
    long_description="Python bindings to the OMERO.blitz server.",
    author="The Open Microscopy Team",
    author_email="ome-devel@lists.openmicroscopy.org.uk",
    url=url,
    download_url=url,
    package_dir={"": "target"},
    packages=packages,
    package_data={
        'omero.gateway': ['pilfonts/*'],
        'omero.gateway.scripts': ['imgs/*']},
    cmdclass={'test': PyTest},
    tests_require=['pytest<3'])
