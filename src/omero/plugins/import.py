#!/usr/bin/env python
"""
   Startup plugin for command-line importer.

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import subprocess, optparse, os, sys, signal, time
from omero.cli import Arguments, BaseControl, CLI, VERSION, OMERODIR
import omero.java

START_CLASS="ome.formats.importer.cli.CommandLineImporter"
TEST_CLASS="ome.formats.test.util.TestEngine"

class ImportControl(BaseControl):

    def __init__(self, ctx, dir = OMERODIR):
        BaseControl.__init__(self, ctx, dir)
        self.command = [ START_CLASS ]

    def _run(self, args = []):
        args = Arguments(args)
        client_dir = self.ctx.dir / "lib" / "client"
        log4j = "-Dlog4j.configuration=log4j-cli.properties"
        classpath = [ file.abspath() for file in client_dir.files("*.jar") ]
        xargs = [ log4j, "-Xmx1024M", "-cp", os.pathsep.join(classpath) ]

        # Here we permit passing ---file=some_output_file in order to
        # facilitate the omero.util.import_candidates.as_dictionary
        # call. This may not always be necessary.
        out = None
	err = None
        for i in args.args:
            if i.startswith("---file="):
                out = i
            if i.startswith("---errs="):
                err = i
        if out:
            args.args.remove(out)
            out = open(out[8:], "w")
        if err:
            args.args.remove(err)
            err = open(err[8:], "w")

        p = omero.java.popen(self.command + args.args, debug=False, xargs = xargs, stdout=out, stderr=err)
        self.ctx.rv = p.wait()

    def help(self, args = None):
        self._run() # Prints help by default

    def __call__(self, *args):
        args = Arguments(*args)
        self._run(args)


class TestEngine(ImportControl):

    def __init__(self, ctx, dir = OMERODIR):
        ImportControl.__init__(self, ctx, dir)
        self.command = [ TEST_CLASS ]

try:
    register("import", ImportControl)
    register("testengine", TestEngine)
except NameError:
    ImportControl(None)._main()
