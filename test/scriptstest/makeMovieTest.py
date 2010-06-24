#!/usr/bin/env python

"""
   Integration test which checks the various parameters for makemovie.py

   Copyright 2010 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import integration.library as lib
import unittest, os, sys, uuid


class TestMakeMovie(lib.ITest):
    """
    Requires PIL being installed
    """

    def setUp(self):
        lib.ITest.setUp(self)
        self.svc = self.client.sf.getScriptService()

    def testNoParams(self):
        makeMovieID = self.svc.getScriptID("/omero/export_scripts/Make_Movie.py")
        imported_pix = ",".join(self.import_image())
        imported_img = self.query.findByQuery("select i from Image i where i.pixels.id in (%s" % imported_pix, None)
        inputs = {"Image_ID": imported_img.id.val}
        process = self.svc.runScript(makeMovieID, {}, None)

if __name__ == '__main__':
    unittest.main()
