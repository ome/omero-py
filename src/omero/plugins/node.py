#!/usr/bin/env python
"""
 :author: Josh Moore, josh at glencoesoftware.com

 OMERO Grid node controller

 This is a python wrapper around icegridnode.

 Copyright 2008 Glencoe Software, Inc.  All Rights Reserved.
 Use is subject to license terms supplied in LICENSE.txt

"""

from omero.cli import BaseControl, CLI
from omero.util import tail_lines
from omero_ext.strings import shlex
import re, os, sys, signal
from exceptions import Exception as Exc
from path import path

HELP = "Control icegridnode."

class NodeControl(BaseControl):

    def help(self, args = None):
        self.ctx.out( """
Syntax: %(program_name)s node [node-name ] [sync] [ start | stop | status | restart ]
           start       -- Start the node via icegridnode. With sync doesn't return until reachable.
           stop        -- Stop the node via icegridadmin. With sync doesn't return until stopped.
           status      -- Prints a status message. Return code is non-zero if there is a problem.
           restart     -- Calls "sync start" then "stop" ("sync stop" if sync is specified)

        node-name cannot be "start", "stop", "restart", "status", or "sync".
        """ )

    def _configure(self, parser):
        sub = parser.sub()
        start = parser.add(sub, self.start, help = "Start the node via icegridnode. With sync doesn't return until reachable")
        stop = parser.add(sub, self.stop, help = "Stop the node via icegridadmin. With sync doesn't return until stopped")
        status = parser.add(sub, self.status, help = "Prints a status message. Return code is non-zero if there is a problem")
        restart = parser.add(sub, self.restart, help = "Calls 'sync start' then 'stop' ('sync stop' if sync is specified")


    def _likes(self, args):
        first, other = args.firstOther()
        return hasattr(self,first) or RE.match(args.join(" ")) and True or False

    def _noargs(self):
        self.help()

    def __call__(self, args):
        first, other = args.firstOther()
        try:
            name = self._node()
            sync = False
            acts = []

            if first == "sync":
                # No master specified
                sync = True
                name = self._node()
                acts.extend(other)
            elif first == "start" or first == "stop" or first =="stop" or first == "kill" or first == "restart":
                # Neither master nor sync specified. Defaults in effect
                acts.append(first)
                acts.extend(other)
            else:
                # Otherwise, command is name of master
                name = first
                # Check for sync
                if len(other) > 0 and other[0] == "sync":
                    sync = True
                    other.pop(0)
                acts.extend(other)

            self._node(name)
            if len(acts) == 0:
                self.help()
            else:
                for act in acts:
                    c = getattr(self, act)
                    c(name, sync)
        finally:
            pass

            #self.ctx.dbg(str(ex))
            #self.ctx.die(100, "Bad argument: "+ str(first) + ", " + ", ".join(other))

    def _handleNZRC(self, nzrc):
        """
        Set the return value from nzrc on the context, and print
        out the last two lines of any error messages if present.
        """
        props = self._properties()
        self.ctx.rv = nzrc.rv
        myoutput = self.dir / path(props["Ice.StdErr"])
        if not myoutput.exists():
	        pass
	else:
                print "from %s:" % str(myoutput)
                print tail_lines(str(myoutput),2)


    ##############################################
    #
    # Commands : Since node plugin implements its own
    # __call__() method, the pattern for the following
    # commands is somewhat different.
    #

    def start(self, name = None, sync = False):

        self._initDir()

        if name == None:
            name = self._node()

        try:
            command = ["icegridnode", self._icecfg()]
            if self._isWindows():
                command = command + ["--install","OMERO."+self._node()]
                self.ctx.call(command)
                self.ctx.call(["icegridnode","--start","OMERO."+self._node()])
            else:
                command = command + ["--daemon", "--pidfile", str(self._pid()),"--nochdir"]
                self.ctx.call(command)
        except OSError, o:
                msg = """%s\nPossibly an error finding "icegridnode". Try "icegridnode -h" from the command line.""" % o
                raise Exc(msg)
        except NonZeroReturnCode, nzrc:
                self._handleNZRC(nzrc)

    def status(self, name = None):

        if name == None:
            name = self._node()

        self.ctx.pub(["admin","status",name])

    def stop(self, name = None, sync = False):
        if name == None:
            name = self._node()
        if self._isWindows():
                try:
                        command = ["icegridnode", "--stop", "OMERO."+self._node()]
                        self.ctx.call(command)
                        command = ["icegridnode", "--uninstall", "OMERO."+self._node()]
                        self.ctx.call(command)
                except NonZeroReturnCode, nzrc:
                        self._handleNZRC(nzrc)
        else:
                pid = open(self._pid(),"r").readline()
                os.kill(int(pid), signal.SIGQUIT)

    def kill(self, name = None, sync = False):
        if name == None:
            name = self._node()
        pid = open(self._pid(),"r").readline()
        os.kill(int(pid), signal.SIGKILL)

try:
    register("node", NodeControl, HELP)
except NameError:
    if __name__ == "__main__":
        cli = CLI()
        cli.register("node", NodeControl, HELP)
        cli.invoke(sys.argv[1:])
