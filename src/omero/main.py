#!/usr/bin/env python

"""

:author: Josh Moore <josh@glencoesoftware.com>

Python driver for OMERO
Copyright (c) 2007, Glencoe Software, Inc.
See LICENSE for details.

"""
from __future__ import print_function

import logging
import os
import sys

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
# Assuming a CLI user never wants to see development details
# such as code that has been deprecated.


def not_root():
    """
    Check that the effective current user is not 0
    on systems supporting os.geteuid()
    """
    try:
        euid = os.geteuid()
        if euid == 0:
            print(
                "FATAL: Running %s as root can corrupt your directory "
                "permissions." % sys.argv[0])
            sys.exit(1)
        else:
            return euid
    except AttributeError:
        # This platform doesn't support effective uid
        # So nothing to worry about.
        return None


def readlink(file=sys.argv[0]):
    """
    Resolve symlinks and similar. This is useful to allow
    linking this file under /usr/bin/, for example.
    """
    import stat

    file = sys.argv[0]
    if not os.path.exists(file) and sys.platform == 'win32':
        file += '.exe'
    while stat.S_ISLNK(os.lstat(file)[stat.ST_MODE]):
        target = os.readlink(file)
        if target[0] != "/":
            file = os.path.join(os.path.dirname(file), target)
        else:
            file = target

    file = os.path.abspath(file)
    return file


def main():
    not_root()

    if "OMERO_HOME" in os.environ:
        print("WARN: OMERO_HOME usage is ignored in omero-py")

    exe = readlink()
    top = os.path.join(exe, os.pardir, os.pardir)

    #
    # This list needs to be kept in line with omero.cli.CLI._env
    #
    top = os.path.normpath(top)
    var = os.path.join(top, "var")
    vlb = os.path.join(var, "lib")
    sys.path.append(vlb)

    # Testing shortcut. If the first argument is an
    # empty string, exit sucessfully.
    #
    if len(sys.argv) == 2 and sys.argv[1] == "":
        sys.exit(0)

    #
    # Primary activity: import omero.cli and launch
    # catching any Ctrl-Cs from the user
    #
    try:
        try:
            import omero.cli
        except ImportError as ie:
            OMERODIR = os.environ.get('OMERODIR', None)
            print("*"*80)
            print("""
            ERROR: Could not import omero.cli! (%s)

            This means that your installation is incomplete. Contact
            the OME mailing lists for more information:

            https://www.openmicroscopy.org/support/

            If you are building from source, please supply the build log
            as well as which version you are building from. If you
            downloaded a distribution, please provide which link you
            used.
            """ % ie)
            print("*"*80)
            print("""
            Debugging Info:
            --------------
            CWD=%s
            VERSION=%s
            OMERO_EXE=%s
            OMERODIR=%s
            PYTHONPATH=%s
            """ % (os.getcwd(), sys.version.replace("\n", " "), top,
                   OMERODIR, sys.path))
            sys.exit(2)

        logging.basicConfig(level=logging.WARN)
        rv = omero.cli.argv()
        sys.exit(rv)
    except KeyboardInterrupt:
        print("Cancelled")
        sys.exit(1)
