#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Copyright 2009 Glencoe Software, Inc. All rights reserved.
    Use is subject to license terms supplied in LICENSE.txt
"""

from future import standard_library
from builtins import str
from builtins import object
from omero_version import omero_version

import platform
import logging
import requests
standard_library.install_aliases()


class UpgradeCheck(object):

    """
    Port of Java UpgradeCheck:

    >>> from omero.util.upgrade_check import UpgradeCheck
    >>> uc = UpgradeCheck("doctest")
    >>> uc.run()
    >>> uc.isUpgradeNeeded()
    False
    >>> uc.isExceptionThrown()
    False
    >>> uc = UpgradeCheck("doctest", version = "0.0.0")
    >>> uc.run()
    >>> uc.isUpgradeNeeded()
    True
    >>> uc.isExceptionThrown()
    False
    >>>
    >>> uc = UpgradeCheck("doctest",
    ...     url = "http://some-completely-unknown-host.abcd/")
    >>> uc.run()
    >>> uc.isUpgradeNeeded()
    False
    >>> uc.isExceptionThrown()
    True
    """

    #
    # our default timeout to use for requests; package default is no timeout
    # * https://requests.readthedocs.io/en/master/user/quickstart/#timeouts
    #
    DEFAULT_TIMEOUT = 6.0

    def __init__(self, agent, url="http://upgrade.openmicroscopy.org.uk/",
                 version=omero_version, timeout=DEFAULT_TIMEOUT):
        """
        ::
            agent   := Name of the agent which is accessing the registry.
                       This will be appended to "OMERO." in order to adhere
                       to the registry API.
            url     := Connection information for the upgrade check.
                       None or empty string disables check.
                       Defaults to upgrade.openmicroscopy.org.uk
            version := Version to check against the returned value.
                       Defaults to current version as specified
                       in omero_version.py.
            timeout := How long to wait for the HTTP GET in seconds (float).
                       The default timeout is 3 seconds.
        """

        self.log = logging.getLogger("omero.util.UpgradeCheck")

        self.url = str(url)
        self.version = str(version)
        self.timeout = float(timeout)
        self.agent = "OMERO." + str(agent)

        self.upgradeUrl = None
        self.exc = None

    def isUpgradeNeeded(self):
        return self.upgradeUrl is not None

    def getUpgradeUrl(self):
        return self.upgradeUrl

    def isExceptionThrown(self):
        return self.exc is not None

    def getExceptionThrown(self):
        return self.exc

    def _set(self, results, e):
        self.upgradeUrl = results
        self.exc = e

    def getOSVersion(self):
        try:
            if len(platform.mac_ver()[0]) > 0:
                version = "%s;%s" % (platform.platform(),
                                     platform.mac_ver()[0])
            else:
                version = platform.platform()
        except Exception:
            version = platform.platform()
        return version

    def run(self):
        """
        If the {@link #url} has been set to null or the empty string, then no
        upgrade check will be performed (silently). If however the string is an
        invalid URL, a warning will be printed.

        This method should <em>never</em> throw an exception.
        """

        # If None or empty, the upgrade check is disabled.
        if self.url is None or len(self.url) == 0:
            return
            # EARLY EXIT!

        try:
            params = {}
            params["version"] = self.version
            params["os.name"] = platform.system()
            params["os.arch"] = platform.machine()
            params["os.version"] = self.getOSVersion()
            params["python.version"] = platform.python_version()
            params["python.compiler"] = platform.python_compiler()
            params["python.build"] = platform.python_build()

            headers = {'User-Agent': self.agent}
            request = requests.get(
                self.url, headers=headers, params=params,
                timeout=self.DEFAULT_TIMEOUT
            )
            result = request.text
        except Exception as e:
            self.log.error(str(e), exc_info=0)
            self._set(None, e)
            return

        if len(result) == 0:
            self.log.info("no update needed")
            self._set(None, None)
        else:
            self.log.warn("UPGRADE AVAILABLE:" + result)
            self._set(result, None)
