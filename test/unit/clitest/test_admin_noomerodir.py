#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2020 University of Dundee & Open Microscopy Environment.
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

import pytest
from omero.plugins.admin import AdminControl
from omero.plugins.prefs import PrefsControl

from mocks import MockCLI


class TestAdminCommandsFailFast(object):
    # These commands should fail immediately so there's no need for the full
    # setup

    @pytest.fixture(autouse=True)
    def setup_method(self, tmpdir, monkeypatch):
        # Other setup
        self.cli = MockCLI()
        monkeypatch.setenv('OMERODIR', str(tmpdir))
        self.cli.dir = tmpdir
        self.cli.register("admin", AdminControl, "TEST")
        self.cli.register("config", PrefsControl, "TEST")

    @pytest.mark.parametrize("command", ["start", "stop", "restart"])
    def testCheckServiceManagerEnv(self, command):
        self.cli.invoke([
            "config", "set",
            "omero.admin.servicemanager.checkenv",
            "TESTOMERO_ADMIN_SERVICEMANAGER_CHECKENV"],
            strict=True)
        self.cli.invoke(["admin", command, "--force-rewrite"], strict=False)
        assert self.cli.getStderr()[-1] == (
            "ERROR: OMERO is configured to run under a service manager but "
            "TESTOMERO_ADMIN_SERVICEMANAGER_CHECKENV is not set")
