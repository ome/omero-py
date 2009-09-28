#!/usr/bin/env python
"""
   HQL plugin

   Plugin read by omero.cli.Cli during initialization. The method(s)
   defined here will be added to the Cli class for later use.

   Copyright 2008 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

from omero.cli import CLI, BaseControl
import cmd, sys, exceptions
import sys

class HqlCLI(CLI):

    prompt = "omero hql [%s]> "

    def __init__(self):
        CLI.__init__(self)
        self.queue = []
        self.prompt = HqlCLI.prompt % str(0)

    def invoke(self, args):
        args = Arguments(args)

class HqlControl(BaseControl):

    def help(self, args = None):
        self.ctx.out("""
Syntax: %(program_name)s hql param1=value1 param2=value2 select x from X ...

        Executes an HQL statement with the given parameters.
        If no query is given, then a shell is opened which
        will run any entered query with the current parameters.
        """)

    def __call__(self, *args):
        args = Arguments(*args)
        hql = HqlCLI()
        if len(args) > 0:
            hql.invoke(args)
        else:
            hql.invokeloop()

try:
    register("hql", HqlControl)
except NameError:
    HqlControl()._main()
