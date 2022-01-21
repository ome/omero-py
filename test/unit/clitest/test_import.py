#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
   Test of the omero import control.

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""
from __future__ import division
from __future__ import print_function

from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import object
from past.utils import old_div
import os
import pytest
import sys
from omero_ext.path import path
import omero.clients
import uuid
from omero.cli import CLI, NonZeroReturnCode
from omero.util import import_candidates

# Workaround for a poorly named module
try:
    plugin = __import__('omero.plugins.import', globals(), locals(),
                        ['ImportControl'], -1)
except ValueError:
    # Python 3
    plugin = __import__('omero.plugins.import', globals(), locals(),
                        ['ImportControl'], 0)

ImportControl = plugin.ImportControl
CommandArguments = plugin.CommandArguments

help_arguments = ("-h", "--javahelp", "--java-help", "--advanced-help")

OMERODIR = False
if 'OMERODIR' in os.environ:
    OMERODIR = os.environ.get('OMERODIR')


@pytest.fixture(scope="session")
def omero_userdir_tmpdir(tmpdir_factory):
    # If OMERO_USERDIR is set assume user wants to use it for tests
    # Otherwise avoid modifying the default userdir
    if os.getenv("OMERO_USERDIR"):
        return os.getenv("OMERO_USERDIR")
    return str(tmpdir_factory.mktemp('omero_userdir'))


@pytest.fixture(scope="function", autouse=True)
def omero_userdir(monkeypatch, omero_userdir_tmpdir):
    monkeypatch.setenv("OMERO_USERDIR", omero_userdir_tmpdir)


class MockClient(omero.clients.BaseClient):

    def setSessionId(self, uuid):
        self._uuid = uuid

    def getSessionId(self):
        return self._uuid


class TestImport(object):

    def setup_method(self, method):
        self.cli = CLI()
        self.cli.register("import", ImportControl, "TEST")
        self.args = ["import"]

    def add_client_dir(self):
        if OMERODIR is not False:
            dist_dir = path(OMERODIR)
            client_dir = dist_dir / "lib" / "client"
            logback = dist_dir / "etc" / "logback-cli.xml"
            self.args += ["--clientdir", client_dir]
            self.args += ["--logback", logback]

    def mkdir(self, parent, name, with_ds_store=False):
        child = old_div(parent, name)
        child.mkdir()
        if with_ds_store:
            ds_store = old_div(child, ".DS_STORE")
            ds_store.write("")
        return child

    def mkfakescreen(self, screen_dir, nplates=2, nruns=2, nwells=2,
                     nfields=4, with_ds_store=False):

        fieldfiles = []
        for iplate in range(nplates):
            plate_dir = self.mkdir(
                screen_dir, "Plate00%s" % str(iplate),
                with_ds_store=with_ds_store)
            for irun in range(nruns):
                run_dir = self.mkdir(
                    plate_dir, "Run00%s" % str(irun),
                    with_ds_store=with_ds_store)
                for iwell in range(nwells):
                    well_dir = self.mkdir(
                        run_dir, "WellA00%s" % str(iwell),
                        with_ds_store=with_ds_store)
                    for ifield in range(nfields):
                        fieldfile = (old_div(well_dir, ("Field00%s.fake" %
                                                 str(ifield))))
                        fieldfile.write('')
                        fieldfiles.append(fieldfile)
        return fieldfiles

    def mkfakepattern(self, tmpdir, nangles=7, ntimepoints=10):

        spim_dir = tmpdir.join("SPIM")
        spim_dir.mkdir()
        tiffiles = []
        for angle in range(1, nangles + 1):
            for timepoint in range(1, ntimepoints + 1):
                tiffile = (old_div(spim_dir, ("spim_TL%s_Angle%s.fake" %
                                       (str(timepoint), str(angle)))))
                tiffile.write('')
                print(str(tiffile))
                tiffiles.append(tiffile)
        patternfile = old_div(spim_dir, "spim.pattern")
        patternfile.write("spim_TL<1-%s>_Angle<1-%s>.fake"
                          % (str(ntimepoints), str(nangles)))
        assert len(tiffiles) == nangles * ntimepoints
        return patternfile, tiffiles

    def testDropBoxArgs(self):
        class MockImportControl(ImportControl):
            def importer(this, args):
                assert args.server == "localhost"
                assert args.port == "4064"
                assert args.key == "b0742975-03a1-4f6d-b0ac-639943f1a147"
                assert args.errs == "/tmp/dropbox.err"
                assert args.file == "/tmp/dropbox.out"

        self.cli.register("mock-import", MockImportControl, "HELP")
        self.args = ['-s', 'localhost', '-p', '4064', '-k',
                     'b0742975-03a1-4f6d-b0ac-639943f1a147']
        self.args += ['mock-import', '---errs=/tmp/dropbox.err']
        self.args += ['---file=/tmp/dropbox.out']
        self.args += ['--', '/OMERO/DropBox/root/test.fake']

        self.cli.invoke(self.args)

    @pytest.mark.parametrize('help_argument', help_arguments)
    def testHelp(self, help_argument):
        """Test help arguments"""
        self.args += [help_argument]
        self.cli.invoke(self.args)

    @pytest.mark.parametrize('clientdir_exists', [True, False])
    def testImportNoClientDirFails(self, tmpdir, clientdir_exists):
        """Test fake screen import"""

        fakefile = tmpdir.join("test.fake")
        fakefile.write('')

        if clientdir_exists:
            self.args += ["--clientdir", str(tmpdir)]
        self.args += [str(fakefile)]

        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    @pytest.mark.parametrize("data", (("1", False), ("3", True)))
    def testImportDepth(self, tmpdir, capfd, data):
        """Test import using depth argument"""

        dir1 = tmpdir.join("a")
        dir1.mkdir()
        dir2 = old_div(dir1, "b")
        dir2.mkdir()
        fakefile = old_div(dir2, "test.fake")
        fakefile.write('')

        self.add_client_dir()
        self.args += ["-f", "--debug=ERROR"]
        self.args += [str(dir1)]

        def f():
            self.cli.invoke(self.args + ["--depth=%s" % depth], strict=True)

        depth, result = data
        if result:
            f()
            o, e = capfd.readouterr()
            assert str(fakefile) in str(o)
        else:
            # Now a failure condition
            with pytest.raises(NonZeroReturnCode):
                f()

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testImportFakeImage(self, tmpdir, capfd):
        """Test fake image import"""

        fakefile = tmpdir.join("test.fake")
        fakefile.write('')

        self.add_client_dir()
        self.args += ["-f", "--debug=ERROR"]
        self.args += [str(fakefile)]

        self.cli.invoke(self.args, strict=True)
        o, e = capfd.readouterr()
        outputlines = str(o).split('\n')
        reader = 'loci.formats.in.FakeReader'
        assert outputlines[-2] == str(fakefile)
        assert outputlines[-3] == \
            "# Group: %s SPW: false Reader: %s" % (str(fakefile), reader)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    @pytest.mark.parametrize('params', (
        ("-l", "only_fakes.txt", True),
        ("-l", "no_fakes.txt", False),
        ("--readers", "only_fakes.txt", True),
        ("--readers", "no_fakes.txt", False),
    ))
    def testImportReaders(self, tmpdir, capfd, params):
        """Test fake image import"""

        fakefile = tmpdir.join("test.fake")
        fakefile.write('')

        flag, filename, status = params
        filename = path(__file__).parent / "readers" / filename
        self.add_client_dir()
        self.args += ["-f", flag, filename]
        self.args += [str(fakefile)]

        if status:
            self.cli.invoke(self.args, strict=True)
            o, e = capfd.readouterr()
            outputlines = str(o).split('\n')
            reader = 'loci.formats.in.FakeReader'
            assert outputlines[-2] == str(fakefile)
            assert outputlines[-3] == \
                "# Group: %s SPW: false Reader: %s" % (str(fakefile), reader)
        else:
            with pytest.raises(NonZeroReturnCode):
                self.cli.invoke(self.args, strict=True)
            o, e = capfd.readouterr()
            assert "parsed into 0 group" in e

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    @pytest.mark.parametrize('with_ds_store', (True, False))
    def testImportFakeScreen(self, tmpdir, capfd, with_ds_store):
        """Test fake screen import"""

        screen_dir = tmpdir.join("screen.fake")
        screen_dir.mkdir()
        fieldfiles = self.mkfakescreen(
            screen_dir, with_ds_store=with_ds_store)

        self.add_client_dir()
        self.args += ["-f", "--debug=ERROR"]
        self.args += [str(fieldfiles[0])]

        self.cli.invoke(self.args, strict=True)
        o, e = capfd.readouterr()
        outputlines = str(o).split('\n')
        reader = 'loci.formats.in.FakeReader'
        assert outputlines[-len(fieldfiles)-2] == \
            "# Group: %s SPW: true Reader: %s" % (str(fieldfiles[0]), reader)
        for i in range(len(fieldfiles)):
            assert outputlines[-1-len(fieldfiles)+i] == str(fieldfiles[i])

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testImportPattern(self, tmpdir, capfd):
        """Test pattern import"""

        patternfile, tiffiles = self.mkfakepattern(tmpdir)

        self.add_client_dir()
        self.args += ["-f", "--debug=ERROR"]
        self.args += [str(patternfile)]

        self.cli.invoke(self.args, strict=True)
        o, e = capfd.readouterr()
        outputlines = str(o).split('\n')
        reader = 'loci.formats.in.FilePatternReader'
        print(o)
        assert outputlines[-len(tiffiles)-3] == \
            "# Group: %s SPW: false Reader: %s" % (str(patternfile), reader)
        assert outputlines[-len(tiffiles)-2] == str(patternfile)
        for i in range(len(tiffiles)):
            assert outputlines[-1-len(tiffiles)+i] == str(tiffiles[i])

    @pytest.mark.parametrize('hostname', ['localhost', 'servername'])
    @pytest.mark.parametrize('port', [None, 4064, 14064])
    def testLoginArguments(self, monkeypatch, hostname, port, tmpdir):
        self.args += ['test.fake']
        sessionid = str(uuid.uuid4())

        def new_client(x):
            if port:
                c = MockClient(hostname, port)
            else:
                c = MockClient(hostname)
            c.setSessionId(sessionid)
            return c
        monkeypatch.setattr(self.cli, 'conn', new_client)
        ice_config = old_div(tmpdir, 'ice.config')
        ice_config.write('omero.host=%s\nomero.port=%g' % (
            hostname, (port or 4064)))
        monkeypatch.setenv("ICE_CONFIG", "%s" % ice_config)
        args = self.cli.parser.parse_args(self.args)
        command_args = CommandArguments(self.cli, args)

        expected_args = ['-s', '%s' % hostname]
        expected_args += ['-p', '%s' % (port or 4064)]
        expected_args += ['-k', '%s' % sessionid]
        expected_args += ['test.fake']
        assert command_args.java_args() == expected_args

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testLogPrefix(self, tmpdir, capfd):
        fakefile = tmpdir.join("test.fake")
        fakefile.write('')
        prefix = tmpdir.join("log")

        self.add_client_dir()
        self.args += ["-f", "---logprefix=%s" % prefix,
                      "---file=out", "---errs=errs"]
        self.args += [str(fakefile)]
        self.cli.invoke(self.args, strict=True)

        o, e = capfd.readouterr()
        assert o == ""
        assert (e == "" or e.startswith('Using OMERO.java-'))

        outlines = prefix.join("out").read().split("\n")
        reader = 'loci.formats.in.FakeReader'
        assert outlines[-2] == str(fakefile)
        assert outlines[-3] == \
            "# Group: %s SPW: false Reader: %s" % (str(fakefile), reader)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testLogs(self, tmpdir, capfd, monkeypatch):
        fakefile = tmpdir.join("test.fake")
        fakefile.write('')
        monkeypatch.chdir(tmpdir)

        self.add_client_dir()
        self.args += ["-f", "--file=out", "--errs=errs"]
        self.args += [str(fakefile)]
        self.cli.invoke(self.args, strict=True)

        o, e = capfd.readouterr()
        assert o == ""
        assert (e == "" or e.startswith('Using OMERO.java-'))

        outlines = tmpdir.join("out").read().split("\n")
        reader = 'loci.formats.in.FakeReader'
        assert outlines[-2] == str(fakefile)
        assert outlines[-3] == \
            "# Group: %s SPW: false Reader: %s" % (str(fakefile), reader)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testYamlOutput(self, tmpdir, capfd):

        import yaml
        from io import StringIO

        fakefile = tmpdir.join("test.fake")
        fakefile.write('')
        self.add_client_dir()
        self.args += ["-f", "--output=yaml", str(fakefile)]
        self.cli.invoke(self.args, strict=True)

        o, e = capfd.readouterr()
        # o also contains loads of preceding log output, strip this off
        yamlout = o[o.find('---'):]
        result = yaml.safe_load(StringIO(yamlout))
        result = result[0]
        assert "fake" in result["group"]
        assert 1 == len(result["files"])
        assert "reader" in result
        assert "spw" in result

    def testBulkNoPaths(self):
        t = path(__file__) / "bulk_import" / "test_simple"
        b = old_div(t, "bulk.yml")
        self.add_client_dir()
        self.args += ["-f", "---bulk=%s" % b, "dne.fake"]
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkSimple(self):
        t = path(__file__).parent / "bulk_import" / "test_simple"
        b = old_div(t, "bulk.yml")

        self.add_client_dir()
        self.args += ["-f", "---bulk=%s" % b]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkInclude(self):
        t = path(__file__).parent / "bulk_import" / "test_include" / "inner"
        b = old_div(t, "bulk.yml")

        self.add_client_dir()
        self.args += ["-f", "---bulk=%s" % b]
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkName(self):
        # Metadata provided in the yml file will be applied
        # to the args
        t = path(__file__).parent / "bulk_import" / "test_name"
        b = old_div(t, "bulk.yml")

        class MockImportControl(ImportControl):
            def do_import(self, command_args, xargs, mode):
                assert "--name=testname" in command_args.java_args()
        self.cli.register("mock-import", MockImportControl, "HELP")

        self.args = ["mock-import", "-f", "---bulk=%s" % b]
        self.add_client_dir()
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkCols(self):
        # Metadata provided about the individual columns in
        # the tsv will be used.
        t = path(__file__).parent / "bulk_import" / "test_cols"
        b = old_div(t, "bulk.yml")

        class MockImportControl(ImportControl):
            def do_import(self, command_args, xargs, mode):
                cmd = command_args.java_args()
                assert "--name=meta_one" in cmd or \
                       "--name=meta_two" in cmd

        self.cli.register("mock-import", MockImportControl, "HELP")

        self.args = ["mock-import", "-f", "---bulk=%s" % b]
        self.add_client_dir()
        self.cli.invoke(self.args, strict=True)

    def testBulkBad(self):
        t = path(__file__).parent / "bulk_import" / "test_bad"
        b = old_div(t, "bulk.yml")

        self.add_client_dir()
        self.args += ["-f", "---bulk=%s" % b]
        with pytest.raises(NonZeroReturnCode):
            self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkDry(self, capfd):
        t = path(__file__).parent / "bulk_import" / "test_dryrun"
        b = old_div(t, "bulk.yml")

        self.add_client_dir()
        self.args += ["-f", "---bulk=%s" % b]
        self.cli.invoke(self.args, strict=True)
        o, e = capfd.readouterr()
        assert o == '"--name=no-op" "1.fake"\n'

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testBulkJavaArgs(self):
        """Test Java arguments"""
        t = path(__file__).parent / "bulk_import" / "test_javaargs"
        b = old_div(t, "bulk.yml")

        class MockImportControl(ImportControl):
            def do_import(self, command_args, xargs, mode):
                assert ("--checksum-algorithm=File-Size-64" in
                        command_args.java_args())
                assert "--parallel-upload=10" in command_args.java_args()
                assert "--parallel-fileset=5" in command_args.java_args()
                assert "--transfer=ln_s" in command_args.java_args()
                assert "--exclude=clientpath" in command_args.java_args()
        self.cli.register("mock-import", MockImportControl, "HELP")

        self.args = ["mock-import", "-f", "---bulk=%s" % b]
        self.add_client_dir()
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    @pytest.mark.parametrize('skip', plugin.SKIP_CHOICES)
    def testBulkSkip(self, skip):
        """Test skip arguments"""
        t = path(__file__).parent / "bulk_import" / "test_skip"
        b = t / "%s.yml" % skip

        class MockImportControl(ImportControl):
            def do_import(self, command_args, xargs, mode):
                if skip in ["all", "checksum"]:
                    assert ("--checksum-algorithm=File-Size-64" in
                            command_args.java_args())
                if skip in ["all", "minmax"]:
                    assert ("--no-stats-info" in
                            command_args.java_args())
                if skip in ["all", "thumbnails"]:
                    assert ("--no-thumbnails" in
                            command_args.java_args())
                if skip in ["all", "upgrade"]:
                    assert ("--no-upgrade-check" in
                            command_args.java_args())
        self.cli.register("mock-import", MockImportControl, "HELP")

        self.args = ["mock-import", "-f", "---bulk=%s" % b]
        self.add_client_dir()
        self.cli.invoke(self.args, strict=True)

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testImportCandidates(self, tmpdir):
        """test using import_candidates from util
        """
        fakefile = tmpdir.join("test.fake")
        fakefile.write('')
        candidates = import_candidates.as_dictionary(str(tmpdir))
        assert str(fakefile) in candidates

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testImportCandidatesDepth(self, tmpdir):
        dir1 = tmpdir.join("a")
        dir1.mkdir()
        dir2 = old_div(dir1, "b")
        dir2.mkdir()
        dir3 = old_div(dir2, "c")
        dir3.mkdir()
        fakefile = old_div(dir2, "test.fake")
        fakefile.write("")
        fakefile2 = old_div(dir3, "test2.fake")
        fakefile2.write("")
        candidates = import_candidates.as_dictionary(
            str(tmpdir), extra_args=["--debug", "WARN", "--depth", "3"]
        )
        assert str(fakefile) in candidates
        assert str(fakefile2) not in candidates

    @pytest.mark.skipif(sys.platform == "win32", reason="Fails on Windows")
    def testImportCandidatesReaders(self, tmpdir):
        """
        Test using import_candidates with a populated readers.txt
        """
        fakefile = tmpdir.join("test.fake")
        fakefile.write('')
        patternfile = tmpdir.join("test.pattern")
        patternfile.write('test.fake')
        readers = tmpdir.join("readers.txt")
        readers.write('loci.formats.in.FakeReader')
        candidates = import_candidates.as_dictionary(str(tmpdir))
        assert str(patternfile) in candidates
        assert str(fakefile) in candidates[str(patternfile)]
        candidates = import_candidates.as_dictionary(
            str(tmpdir), readers=str(readers))
        assert str(fakefile) in candidates
        assert str(patternfile) not in candidates
        candidates = import_candidates.as_dictionary(
            str(tmpdir), readers=str(readers), extra_args=["--debug", "WARN"])
        assert str(fakefile) in candidates
        assert str(patternfile) not in candidates
