#!/usr/bin/env python

"""
   scripts test suite. Please add a reference to your subpackage,
   module, or specific class here.

   Copyright 2010 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import unittest

class TopLevel(unittest.TestCase):
    pass

def _additional_tests():
    load = unittest.defaultTestLoader.loadTestsFromName
    suite = unittest.TestSuite()
    suite.addTest(load("scriptstest.coverage"))
    suite.addTest(load("scriptstest.ping"))
    suite.addTest(load("scriptstest.proj"))
    suite.addTest(load("scriptstest.rand"))
    suite.addTest(load("scriptstest.params"))
    return suite
