#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2014-2015 University of Dundee & Open Microscopy Environment.
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from __future__ import division
from builtins import str
from builtins import object
from past.utils import old_div
from omero.cli import CLI
from omero.plugins.sessions import SessionsControl

import os
import pytest


class TestSessions(object):

    def setup_method(self, method):
        self.cli = CLI()
        self.cli.register("sessions", SessionsControl, "TEST")
        self.args = ["sessions"]

    def testHelp(self):
        self.args += ["-h"]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize(
        "subcommand", SessionsControl().get_subcommands())
    def testSubcommandHelp(self, subcommand):
        self.args += [subcommand, "-h"]
        self.cli.invoke(self.args, strict=True)

    def testDefaultSessionsDir(self):
        from omero.util import get_user_dir
        from path import path

        # Default store sessions dir is under user dir
        store = self.cli.controls['sessions'].store(None)
        assert store.dir == path(get_user_dir()) / 'omero' / 'sessions'

    @pytest.mark.parametrize('environment', (
        {'OMERO_USERDIR': None,
         'OMERO_SESSION_DIR': None,
         'OMERO_SESSIONDIR': None},
        {'OMERO_USERDIR': None,
         'OMERO_SESSION_DIR': 'session_dir',
         'OMERO_SESSIONDIR': None},
        {'OMERO_USERDIR': None,
         'OMERO_SESSION_DIR': None,
         'OMERO_SESSIONDIR': 'sessiondir'},
        {'OMERO_USERDIR': 'userdir',
         'OMERO_SESSION_DIR': None,
         'OMERO_SESSIONDIR': None},
        {'OMERO_USERDIR': None,
         'OMERO_SESSION_DIR': 'session_dir',
         'OMERO_SESSIONDIR': 'sessiondir'},
        {'OMERO_USERDIR': 'userdir',
         'OMERO_SESSION_DIR': 'session_dir',
         'OMERO_SESSIONDIR': None},
        {'OMERO_USERDIR': 'userdir',
         'OMERO_SESSION_DIR': None,
         'OMERO_SESSIONDIR': 'sessiondir'},
        {'OMERO_USERDIR': 'userdir',
         'OMERO_SESSION_DIR': 'session_dir',
         'OMERO_SESSIONDIR': 'sessiondir'}))
    @pytest.mark.parametrize('session_args', [None, 'session_dir'])
    def testCustomSessionsDir(
            self, tmpdir, monkeypatch, environment,
            session_args):
        from argparse import Namespace
        from omero.util import get_user_dir
        from path import path

        for var in list(environment.keys()):
            if environment[var]:
                monkeypatch.setenv(var, "%s%s%s" % (tmpdir, os.path.sep, environment.get(var)))
            else:
                monkeypatch.delenv(var, raising=False)

        # args.session_dir sets the sessions dir
        args = Namespace()
        if session_args:
            setattr(args, session_args, old_div(tmpdir, session_args))

        if environment.get('OMERO_SESSION_DIR') or session_args:
            store = pytest.deprecated_call(self.cli.controls['sessions'].store, args)
        else:
            store = self.cli.controls['sessions'].store(args)

        # By order of precedence
        if environment.get('OMERO_SESSIONDIR'):
            sdir = old_div(path(tmpdir), environment.get('OMERO_SESSIONDIR'))
        elif environment.get('OMERO_SESSION_DIR'):
            sdir = (path(tmpdir) / environment.get('OMERO_SESSION_DIR') /
                    'omero' / 'sessions')
        elif session_args:
            sdir = path(getattr(args, session_args)) / 'omero' / 'sessions'
        elif environment.get('OMERO_USERDIR'):
            sdir = path(tmpdir) / environment.get('OMERO_USERDIR') / 'sessions'
        else:
            sdir = path(get_user_dir()) / 'omero' / 'sessions'
        assert store.dir == str(sdir)
