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
from omero.cli import ServiceManagerMixin
from omero.plugins.admin import AdminControl
from omero.plugins.prefs import PrefsControl

from mocks import MockCLI


class MockServiceManagerMixin(MockCLI, ServiceManagerMixin):
    SERVICE_MANAGER_KEY = 'test_servicemanager_mixin'

    class MockCtx:
        def __init__(self):
            self._die_args = []

        def die(self, *args):
            self._die_args.append(args)

    def __init__(self):
        super().__init__()
        self.ctx = self.MockCtx()


class MockConfigXml(object):
    def __init__(self, configmap):
        self.configmap = configmap

    def as_map(self):
        return self.configmap


class TestServiceManagerMixin:

    def test_not_required(self, monkeypatch, tmpdir):
        monkeypatch.setenv('OMERODIR', str(tmpdir))
        cli = MockServiceManagerMixin()
        cli.requires_service_manager(MockConfigXml({}))
        assert not cli.ctx._die_args

    def test_required_notset(self, monkeypatch, tmpdir):
        monkeypatch.setenv('OMERODIR', str(tmpdir))
        cli = MockServiceManagerMixin()
        cli.requires_service_manager(MockConfigXml({
            'omero.test_servicemanager_mixin.servicemanager.checkenv':
            'TEST_SERVICEMANAGER_MIXIN'}))
        assert cli.ctx._die_args == [(
            112,
            "ERROR: OMERO is configured to run under a service manager which "
            "should also set TEST_SERVICEMANAGER_MIXIN")]

    def test_required_set(self, monkeypatch, tmpdir):
        monkeypatch.setenv('OMERODIR', str(tmpdir))
        monkeypatch.setenv('TEST_SERVICEMANAGER_MIXIN', '123')
        cli = MockServiceManagerMixin()
        cli.requires_service_manager(MockConfigXml({
            'omero.test_servicemanager_mixin.servicemanager.checkenv':
            'TEST_SERVICEMANAGER_MIXIN'}))
        assert not cli.ctx._die_args


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
            "omero.server.servicemanager.checkenv",
            "TESTOMERO_ADMIN_SERVICEMANAGER_CHECKENV"],
            strict=True)
        self.cli.invoke(["admin", command, "--force-rewrite"], strict=False)
        assert self.cli.getStderr()[-1] == (
            "ERROR: OMERO is configured to run under a service manager which "
            "should also set TESTOMERO_ADMIN_SERVICEMANAGER_CHECKENV")
