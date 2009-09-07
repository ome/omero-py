#!/usr/bin/env python

"""
   Test of the Tables facility independent of Ice.

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import unittest, os
import omero, omero.tables

class TestTables(unittest.TestCase):

    def testTables(self):
        tables = omero.tables.TablesI()
        table = omero.tables.newTable()

def test_suite():
    return 1

if __name__ == '__main__':
    unittest.main()
