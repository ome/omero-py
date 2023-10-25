#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2013 Glencoe Software, Inc. All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
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

"""
Test of the omero/plugins/tx.py module
"""

from builtins import object
import pytest
from omero.cli import CLI
from omero.model import ProjectI
from omero.plugins.obj import NewObjectTxAction
from omero.plugins.obj import TxCmd
from omero.plugins.obj import ObjControl
from omero.plugins.obj import TxState


class MockCLI(CLI):

    def conn(self, *args, **kwargs):
        return self.get_client()

    def close(self, *args, **kwargs):
        pass

    def out(self, out):
        if hasattr(self, "_out"):
            self._out.append(out)
        else:
            self._out = [out]


class TxBase(object):

    def init(self, mocker):
        self.client = mocker.patch('omero.clients.BaseClient', autospec=True)
        self.sf = mocker.patch('omero.api.ServiceFactoryPrx', autospec=True)
        self.query = mocker.patch('omero.api.IQueryPrx', autospec=True)
        self.update = mocker.patch('omero.api.IUpdatePrx', autospec=True)
        self.client.sf = self.sf
        self.cli = MockCLI()
        self.cli.set_client(self.client)
        self.cli.set("tx.state", TxState(self.cli))
        self.cli.register("obj", ObjControl, "TEST")
        self.args = ["obj"]

    def queries(self, obj):
        self.sf.getQueryService.return_value = self.query
        self.query.get.return_value = obj

    def saves(self, obj):
        self.sf.getUpdateService.return_value = self.update
        self.update.saveAndReturnObject.return_value = obj


class TestNewObjectTxAction(TxBase):

    def test_unknown_class(self, mocker):
        self.init(mocker)
        self.saves(ProjectI(1, False))
        state = TxState(self.cli)
        cmd = TxCmd(state, arg_list=["new", "Project", "name=foo"])
        action = NewObjectTxAction(state, cmd)
        action.go(self.cli, None)


class TestObjControl(TxBase):

    def test_simple_new_usage(self, mocker):
        self.init(mocker)
        self.saves(ProjectI(1, False))
        self.cli.invoke("obj new Project name=foo", strict=True)
        assert self.cli._out == ["Project:1"]

    def test_simple_update_usage(self, mocker):
        self.init(mocker)
        self.queries(ProjectI(1, True))
        self.saves(ProjectI(1, False))
        self.cli.invoke(("obj update Project:1 name=bar "
                        "description=loooong"), strict=True)
        assert self.cli._out == ["Project:1"]

    def testHelp(self, mocker):
        self.init(mocker)
        self.args += ["-h"]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize('subcommand', ("new", "update", "null",
                     "map-get", "map-set",
                     "get", "list-get"))
    def testSubcommandHelp(self, subcommand, mocker):
        self.init(mocker)
        self.args += [subcommand, "-h"]
        self.cli.invoke(self.args, strict=True)
