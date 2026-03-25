#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
   Test of the omero admin control.

   Copyright 2008-2019 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)

import os
import re
import sys
import pytest

from glob import glob

import omero
import omero.clients

from omero.cli import CLI, NonZeroReturnCode
from omero.plugins.admin import AdminControl
from omero.plugins.prefs import PrefsControl
from omero_ext.path import path
from omero_version import ice_compatibility

omeroDir = path(os.getcwd()) / "build"

GRID_FILES = ["templates.xml", "default.xml", "windefault.xml"]
ETC_FILES = ["ice.config", "master.cfg", "internal.cfg"]

MISSING_CONFIGURATION_MSG = "Missing internal configuration."
REWRITE_MSG = " Run `omero admin rewrite`."
FORCE_REWRITE_MSG = " Pass --force-rewrite to the command."
OMERODIR = False
if 'OMERODIR' in os.environ:
    OMERODIR = os.environ.get('OMERODIR')


def _squashWhiteSpace(s):
    # Attempt to make the XML comparison more robust
    return ' '.join(s.split())

@pytest.fixture(autouse=True)
def tmpadmindir(tmpdir, monkeypatch):
    etc_dir = tmpdir.mkdir('etc')
    etc_dir.mkdir('grid')
    tmpdir.mkdir('var')
    templates_dir = etc_dir.mkdir('templates')
    templates_dir.mkdir('grid')

    # Need to know where to find OMERO
    assert 'OMERODIR' in os.environ
    old_etc_dir = os.path.join(OMERODIR, "etc")
    old_templates_dir = os.path.join(old_etc_dir, "templates")
    for f in glob(os.path.join(old_etc_dir, "*.properties")):
        path(f).copy(path(etc_dir))
    for f in glob(os.path.join(old_templates_dir, "*.cfg")):
        path(f).copy(path(templates_dir))
    for f in glob(os.path.join(old_templates_dir, "grid", "*.xml")):
        path(f).copy(path(templates_dir / "grid"))
    path(os.path.join(old_templates_dir, "ice.config")).copy(path(templates_dir))
    # The OMERODIR env-var is directly reference in other omero components so
    # we need to override it
    monkeypatch.setenv('OMERODIR', str(tmpdir))

    return path(tmpdir)


@pytest.mark.skipif(OMERODIR is False, reason="We need $OMERODIR")
class TestAdmin(object):

    @pytest.fixture(autouse=True)
    def setup_method(self, tmpadmindir):
        # Other setup
        self.cli = CLI()
        self.cli.dir = tmpadmindir
        self.cli.register("admin", AdminControl, "TEST")
        self.cli.register("config", PrefsControl, "TEST")

    #
    # Async first because simpler
    #

    def testStartAsync(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_check_access = mocker.patch("omero.plugins.admin.AdminControl.check_access")
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_call = mocker.patch.object(self.cli, "call")
        mock_call.return_value = 0
        mock_popen.return_value.wait.return_value = 1  # I.e. running
        mock_popen.return_value.communicate.return_value = [None, ice_compatibility] 

        self.cli.invoke("admin startasync", strict=True)
        mock_err.assert_called_once_with(
            'No descriptor given. Using etc/grid/default.xml')
        mock_out.assert_called()
        mock_call.assert_called_once()
        assert mock_popen.call_count == 3
        mock_popen.assert_has_calls([
            mocker.call(['icegridnode', '--version']),
            mocker.call().communicate(),
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait(),
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait()
            ])

    def testStopAsyncNoConfig(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin stopasync", strict=True)
        mock_err.assert_called_once_with(
            MISSING_CONFIGURATION_MSG + FORCE_REWRITE_MSG, True)
        mock_out.assert_not_called()

    def testStopAsyncRunning(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_call = mocker.patch.object(self.cli, "call")
        self.cli.invoke("admin rewrite", strict=True)
        mock_popen.return_value.wait.return_value = 0  # I.e. running
        mock_call.return_value = 0
        self.cli.invoke("admin stopasync", strict=True)
        mock_call.assert_called_once()
        mock_popen.assert_has_calls([
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait()])
        mock_err.assert_not_called()
        mock_out.assert_not_called()

    def testStopAsyncRunningForceRewrite(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_call = mocker.patch.object(self.cli, "call")
        mock_popen.return_value.wait.return_value = 0  # I.e. running
        mock_call.return_value = 0

        self.cli.invoke("admin stopasync --force-rewrite", strict=True)
        mock_call.assert_called_once()
        mock_popen.assert_has_calls([
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait()])
        mock_err.assert_not_called()
        mock_out.assert_not_called()

    def testStopAsyncNotRunning(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_popen = mocker.patch.object(self.cli, "popen")
        self.cli.invoke("admin rewrite", strict=True)
        mock_popen.return_value.wait.return_value = 1  # I.e. not running
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin stopasync", strict=True)
        mock_popen.assert_has_calls([
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait()])
        mock_err.assert_called_once_with("Server not running")
        mock_out.assert_not_called()

    def testStopAsyncNotRunningForceRewrite(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_popen.return_value.wait.return_value = 1  # I.e. not running
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin stopasync --force-rewrite", strict=True)
        mock_popen.assert_has_calls([
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                  "-e", "node ping master"]),
            mocker.call().wait()])
        mock_err.assert_called_once_with("Server not running")
        mock_out.assert_not_called()

    def testStopNoConfig(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin stop", strict=True)
        mock_err.assert_called_once_with(
            MISSING_CONFIGURATION_MSG + FORCE_REWRITE_MSG, True)
        mock_out.assert_not_called()

    def testStopNoConfigForceRewrite(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_call = mocker.patch.object(self.cli, "call")
        mock_popen = mocker.patch.object(self.cli, "popen")

        mock_popen.return_value.wait.side_effect = [0, 1]
        mock_call.return_value = 0
        self.cli.invoke("admin stop --force-rewrite", strict=True)

        mock_call.assert_called_once_with(
            ["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
             "-e", "node shutdown master"])
        assert mock_popen.call_count == 2
        mock_call.assert_called_once()
        mock_popen.assert_has_calls([
            mocker.call(["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
             "-e", "node ping master"]),
            mocker.call().wait()])
        mock_out.assert_called_once_with(
            'Waiting on shutdown. Use CTRL-C to exit')
        mock_err.assert_not_called()


    def testStop(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_call = mocker.patch.object(self.cli, "call")
        mock_popen = mocker.patch.object(self.cli, "popen")

        self.cli.invoke("admin rewrite", strict=True)
        mock_popen.return_value.wait.side_effect = [0, 1]
        mock_call.return_value = 0
        self.cli.invoke("admin stop", strict=True)
        mock_call.assert_called_once_with(
            ["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
             "-e", "node shutdown master"])
        assert mock_popen.call_count == 2
        mock_popen.assert_called_with(
            ["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
             "-e", "node ping master"])
        mock_out.assert_called_once_with(
            'Waiting on shutdown. Use CTRL-C to exit')
        mock_err.assert_not_called()

    #
    # STATUS
    #

    def testDiagnostics(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_popen.return_value.wait.return_value = 0

        self.cli.invoke("admin diagnostics", strict=True)
        mock_out.assert_called()
        mock_err.assert_called()
        mock_popen.assert_has_calls([
            mocker.call(['java', '-version']),
            mocker.call(['python', '-V']),
            mocker.call(['icegridnode', '--version']),
            mocker.call(['icegridadmin', '--version']),
            mocker.call(['psql', '--version']),
            mocker.call(['openssl', 'version']),
            mocker.call([
                "icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
                "-e", "application list"])],
            any_order=True)

    def testStatusNoConfig(self, mocker):
        mock_out = mocker.patch.object(self.cli, "out")
        mock_err = mocker.patch.object(self.cli, "err")
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin status", strict=True)
        mock_err.assert_called_once_with(
            MISSING_CONFIGURATION_MSG + REWRITE_MSG, True)
        mock_out.assert_not_called()

    def testStatusNodeFails(self, mocker):

        self.cli.invoke("admin rewrite", strict=True)

        # Setup the call to omero admin ice node
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_popen.return_value.wait.return_value = 1

        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin status", strict=True)
        mock_popen.assert_called_once_with(
            ["icegridadmin", f"--Ice.Config={self.cli.dir}/etc/internal.cfg",
             "-e", "node ping master"])

    def testStatusSMFails(self, mocker):

        self.cli.invoke("admin rewrite", strict=True)

        # Setup the call to omero admin ice node
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_popen.return_value.wait.return_value = 0

        # Setup the call to session manager
        control = self.cli.controls["admin"]
        control._intcfg = lambda: ""

        def sm(*args):
            raise Exception("unknown")
        control.session_manager = sm

        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke("admin status", strict=True)
        mock_popen.assert_called_once_with(
            ["icegridadmin", "", "-e", "node ping master"])

    def testStatusPasses(self, tmpdir, monkeypatch, mocker):

        self.cli.invoke("admin rewrite", strict=True)

        ice_config = tmpdir / 'ice.config'
        ice_config.write('omero.host=localhost\nomero.port=4064')
        monkeypatch.setenv("ICE_CONFIG", str(ice_config))

        # Setup the call to omero admin ice node
        mock_popen = mocker.patch.object(self.cli, "popen")
        mock_popen.return_value.wait.return_value = 0

        # Setup the call to session manager
        control = self.cli.controls["admin"]
        control._intcfg = lambda: ""

        def sm(*args):

            class A(object):
                def create(self, *args):
                    raise omero.WrappedCreateSessionException()
            return A()
        control.session_manager = sm

        self.cli.invoke("admin status", strict=True)
        assert 0 == self.cli.rv
        mock_popen.assert_called_once_with(
            ["icegridadmin", "", "-e", "node ping master"])


def check_registry(topdir, prefix='', registry=4061, **kwargs):
    for key in ['master.cfg', 'internal.cfg']:
        s = (path(topdir) / "etc"/ key).text()
        assert 'tcp -h 127.0.0.1 -p %s%s' % (prefix, registry) in s


def check_ice_config(topdir, prefix='', ssl=4064, **kwargs):
    config_text = (path(topdir) / "etc" / "ice.config").text()
    pattern = re.compile(r'^omero.port=\d+$', re.MULTILINE)
    matches = pattern.findall(config_text)
    assert matches == ["omero.port=%s%s" % (prefix, ssl)]


def check_default_xml(topdir, prefix='', tcp=4063, ssl=4064, ws=4065, wss=4066,
                      transports=None, **kwargs):
    if transports is None:
        transports = ['ssl', 'tcp']
    routerport = (
        '<variable name="ROUTERPORT"    value="%s%s"/>' % (prefix, ssl))
    insecure_routerport = (
        '<variable name="INSECUREROUTER" value="OMERO.Glacier2'
        '/router:tcp -p %s%s -h @omero.host@"/>' % (prefix, tcp))
    client_endpoint_list = []
    for tp in transports:
        if tp == 'tcp':
            client_endpoint_list.append('tcp -p %s%s' % (prefix, tcp))
        if tp == 'ssl':
            client_endpoint_list.append('ssl -p %s%s' % (prefix, ssl))
        if tp == 'ws':
            client_endpoint_list.append('ws -p %s%s' % (prefix, ws))
        if tp == 'wss':
            client_endpoint_list.append('wss -p %s%s' % (prefix, wss))

    client_endpoints = 'client-endpoints="%s"' % ':'.join(client_endpoint_list)
    for key in ['default.xml', 'windefault.xml']:
        s = path(topdir / "etc" / "grid" / key).text()
        assert routerport in s
        assert insecure_routerport in s
        assert client_endpoints in s


def check_templates_xml(topdir, glacier2props):
    s = (path(topdir) / "etc" / "grid" / "templates.xml").text()
    for k, v in glacier2props:
        expected = '<property name="%s" value="%s" />' % (k, v)
        assert expected in s


@pytest.mark.skipif(OMERODIR is False, reason="We need $OMERODIR")
class TestJvmCfg(object):
    """Test template files regeneration"""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmpadmindir):
        self.cli = CLI()
        self.cli.dir = path(tmpadmindir)
        self.cli.register("admin", AdminControl, "TEST")
        self.cli.register("config", PrefsControl, "TEST")
        self.args = ["admin", "jvmcfg"]

    def testNoTemplatesGeneration(self):
        """Test no template files are generated by the jvmcfg subcommand"""

        # Test non-existence of configuration files
        for f in GRID_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / "grid" / f)
        for f in ETC_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / f)

        # Call the jvmcf command and test file genearation
        self.cli.invoke(self.args, strict=True)
        for f in GRID_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / "grid" / f)
        for f in ETC_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / f)

    @pytest.mark.parametrize(
        'suffix', ['', '.blitz', '.indexer', '.pixeldata', '.repository'])
    def testInvalidJvmCfgStrategy(self, suffix, tmpdir):
        """Test invalid JVM strategy configuration leads to CLI error"""

        key = "omero.jvmcfg.strategy%s" % suffix
        self.cli.invoke(["config", "set", key, "bad"], strict=True)
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)



DEFAULT_XML_PARAMS = {
    # "": """\
    # <node name="master">
    #   <server-instance template="Glacier2Template"
    #     client-endpoints="ssl -p 4064:tcp -p 4063"
    #     server-endpoints="tcp -h 127.0.0.1"/>
    #   <server-instance template="BlitzTemplate" index="0" config="default"/>
    #   <server-instance template="IndexerTemplate" index="0"/>
    #   <server-instance template="DropBoxTemplate"/>
    #   <server-instance template="MonitorServerTemplate"/>
    #   <server-instance template="FileServerTemplate"/>
    #   <server-instance template="StormTemplate"/>
    #   <server-instance template="PixelDataTemplate" index="0" dir=""/><!-- assumes legacy -->
    #   <server-instance template="ProcessorTemplate" index="0" dir=""/><!-- assumes legacy -->
    #   <server-instance template="TablesTemplate" index="0" dir=""/><!-- assumes legacy -->
    #   <server-instance template="TestDropBoxTemplate"/>
    # </node>""",
    # "master:Blitz-0,Indexer-0,DropBox,MonitorServer,FileServer,Storm,PixelData-0,Tables-0,TestDropBox slave:Processor-0": """
    # <node name="master">
    #   <server-instance template="Glacier2Template"
    #     client-endpoints="@omero.client.endpoints@"
    #     server-endpoints="tcp -h @omero.master.host@"/>
    #   <server-instance template="BlitzTemplate" index="0" config="default"/>
    #   <server-instance template="IndexerTemplate" index="0"/>
    #   <server-instance template="DropBoxTemplate"/>
    #   <server-instance template="MonitorServerTemplate"/>
    #   <server-instance template="FileServerTemplate"/>
    #   <server-instance template="StormTemplate"/>
    #   <server-instance template="PixelDataTemplate" index="0" dir=""/>
    #   <server-instance template="TablesTemplate" index="0" dir=""/>
    #   <server-instance template="TestDropBoxTemplate"/>
    # </node>

    # <node name="worker">
    #   <server-instance template="ProcessorTemplate" index="0" dir=""/>
    # </node>
    # """,
    "master:Blitz-0,Indexer-0,DropBox,MonitorServer,FileServer,Storm,Tables-0,TestDropBox worker-1:Processor-0,PixelData-0 worker-2:Processor-1,PixelData-1": """
    <node name="master">
      <server-instance template="Glacier2Template"
        client-endpoints="ssl -p 4064:tcp -p 4063"
        server-endpoints="tcp -h 127.0.0.1"/>
      <server-instance template="BlitzTemplate" index="0" config="default"/>
      <server-instance template="IndexerTemplate" index="0"/>
      <server-instance template="DropBoxTemplate"/>
      <server-instance template="MonitorServerTemplate"/>
      <server-instance template="FileServerTemplate"/>
      <server-instance template="StormTemplate"/>
      <server-instance template="TablesTemplate" index="0" dir=""/>
      <server-instance template="TestDropBoxTemplate"/>
    </node>

    <node name="worker-1">
      <server-instance template="ProcessorTemplate" index="0" dir=""/>
      <server-instance template="PixelDataTemplate" index="0" dir=""/>
    </node>

    <node name="worker-2">
      <server-instance template="ProcessorTemplate" index="1" dir=""/>
      <server-instance template="PixelDataTemplate" index="1" dir=""/>
    </node>
    """,
}


@pytest.mark.skipif(OMERODIR is False, reason="We need $OMERODIR")
class TestRewrite(object):
    """Test template files regeneration"""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmpadmindir):
        self.cli = CLI()
        self.cli.dir = path(tmpadmindir)
        self.cli.register("admin", AdminControl, "TEST")
        self.cli.register("config", PrefsControl, "TEST")
        self.args = ["admin", "rewrite"]

    def testTemplatesGeneration(self):
        """Test template files are generated by the rewrite subcommand"""

        # Test non-existence of configuration files
        for f in GRID_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / "grid" / f)
        for f in ETC_FILES:
            assert not os.path.exists(path(self.cli.dir) / "etc" / f)

        # Call the jvmcf command and test file genearation
        self.cli.invoke(self.args, strict=True)
        for f in GRID_FILES:
            assert os.path.exists(path(self.cli.dir) / "etc" / "grid" / f)
        for f in ETC_FILES:
            assert os.path.exists(path(self.cli.dir) / "etc" / f)

    def testForceRewrite(self, monkeypatch):
        """Test template regeneration while the server is running"""

        # Call the jvmcfg command and test file generation
        self.cli.invoke(self.args, strict=True)
        monkeypatch.setattr(AdminControl, "status", lambda *args, **kwargs: 0)
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    def testOldTemplates(self):
        old_templates = path(__file__).dirname() / ".." / "old_templates.xml"
        old_templates.copy(
            path(self.cli.dir) / "etc" / "templates" / "grid" /
            "templates.xml")
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    @pytest.mark.parametrize('prefix', [None, 1])
    @pytest.mark.parametrize('registry', [None, 111])
    @pytest.mark.parametrize('tcp', [None, 222])
    @pytest.mark.parametrize('ssl', [None, 333])
    @pytest.mark.parametrize('ws_wss_transports', [
        (None, None, None),
        (444, None, ('ssl', 'tcp', 'wss', 'ws')),
        (None, 555, ('ssl', 'tcp', 'wss', 'ws')),
    ])
    def testExplicitPorts(self, registry, ssl, tcp, prefix,
                          ws_wss_transports, monkeypatch):
        """
        Test the omero.ports.xxx and omero.client.icetransports
        configuration properties during the generation
        of the configuration files
        """

        # Skip the JVM settings calculation for this test
        ws, wss, transports = ws_wss_transports
        kwargs = {}
        if prefix:
            kwargs["prefix"] = prefix
        if registry:
            kwargs["registry"] = registry
        if tcp:
            kwargs["tcp"] = tcp
        if ssl:
            kwargs["ssl"] = ssl
        if ws:
            kwargs["ws"] = ws
        if wss:
            kwargs["wss"] = wss
        for (k, v) in list(kwargs.items()):
            self.cli.invoke(
                ["config", "set", "omero.ports.%s" % k, "%s" % v],
                strict=True)

        if transports:
            self.cli.invoke(
                ["config", "set", "omero.client.icetransports", "%s" %
                 ','.join(transports)], strict=True)
            kwargs["transports"] = transports

        self.cli.invoke(self.args, strict=True)

        check_ice_config(self.cli.dir, **kwargs)
        check_registry(self.cli.dir, **kwargs)

    def testGlacier2Icessl(self, monkeypatch):
        """
        Test the omero.glacier2.IceSSL.* properties during the generation
        of the configuration files
        """

        # Skip the JVM settings calculation for this test
        # monkeypatch.setattr(omero.install.jvmcfg, "adjust_settings",
        #                     lambda x, y: {})

        if sys.platform == "darwin":
            expected_ciphers = '(AES)'
        else:
            expected_ciphers = 'ADH:!LOW:!MD5:!EXP:!3DES:@STRENGTH'
        glacier2 = [
            ("IceSSL.Ciphers", expected_ciphers),
            ("IceSSL.TestKey", "TestValue"),
        ]
        self.cli.invoke([
            "config", "set",
            "omero.glacier2." + glacier2[1][0], glacier2[1][1]],
            strict=True)
        self.cli.invoke(self.args, strict=True)
        check_templates_xml(self.cli.dir, glacier2)

    @pytest.mark.parametrize('descriptor', DEFAULT_XML_PARAMS.keys())
    def testNodeDescriptors(self, descriptor, monkeypatch):
        """
        Test omero.server.nodedescriptors for configuring the available
        services in master and other nodes
        """
        self.cli.invoke(
            ["config", "set", "omero.server.nodedescriptors", descriptor],
            strict=True)
        self.cli.invoke(self.args, strict=True)

        defaultxml = (self.cli.dir / "etc" / "grid" / "default.xml").text()
        # print(defaultxml)
        expected = DEFAULT_XML_PARAMS[descriptor]

        assert _squashWhiteSpace(expected) in _squashWhiteSpace(defaultxml)
