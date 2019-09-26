from __future__ import division

# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# blitz_gateway - python bindings and wrappers to access an OMERO blitz server
#
# Copyright (c) 2007-2015 Glencoe Software, Inc. All rights reserved.
#
# This software is distributed under the terms described by the LICENCE file
# you can find at the root of the distribution bundle, which states you are
# free to use it only for non commercial purposes.
# If the file is missing please request a copy by contacting
# jason@glencoesoftware.com.

# Set up the python include paths
from past.builtins import cmp
from future import standard_library
standard_library.install_aliases()
from builtins import chr
from builtins import map
from builtins import str
from builtins import range
from past.builtins import basestring
from past.utils import old_div
from builtins import object
import os

import warnings
from collections import defaultdict

# TODO check various types are used
try:
    from types import IntType, LongType, UnicodeType
    from types import BooleanType, TupleType, StringType, StringTypes
except ImportError:
    IntType = int
    LongType = int
    UnicodeType = str
    BooleanType = bool
    TupleType = tuple
    StringType = str
    StringTypes = str

from datetime import datetime
from io import StringIO
import configparser

import omero
import omero.clients
from omero.util.decorators import timeit
from omero.cmd import Chgrp2, Delete2, DoAll, SkipHead
from omero.cmd.graphs import ChildOption
from omero.api import Save
from omero.gateway.utils import ServiceOptsDict, GatewayConfig, toBoolean
from omero.model.enums import PixelsTypeint8, PixelsTypeuint8, PixelsTypeint16
from omero.model.enums import PixelsTypeuint16, PixelsTypeint32
from omero.model.enums import PixelsTypeuint32, PixelsTypefloat
from omero.model.enums import PixelsTypecomplex, PixelsTypedouble

import Ice
import Glacier2

import traceback
import time

from gettext import gettext as _

import logging

from omero.rtypes import rstring, rint, rlong, rbool
from omero.rtypes import rtime, rlist, unwrap

logger = logging.getLogger(__name__)

from ._core import omero_type
from ._core import OmeroRestrictionWrapper
from ._core import BlitzObjectWrapper
from ._core import AnnotationWrapper
from ._core import AnnotationLinkWrapper
from ._core import EnumerationWrapper

# BASIC #


class NoProxies (object):
    """ A dummy placeholder to indicate that proxies haven't been created """

    def __getitem__(self, k):
        raise Ice.ConnectionLostException

    def values(self):
        return ()


class _BlitzGateway (object):
    """
    Connection wrapper. Handles connecting and keeping the session alive,
    creation of various services, context switching, security privileges etc.
    """

    """
    Holder for class wide configuration properties.
    """
    ICE_CONFIG = None
    """
    ICE_CONFIG - Defines the path to the Ice configuration
    """
# def __init__ (self, username, passwd, server, port, client_obj=None,
# group=None, clone=False):

    def __init__(self, username=None, passwd=None, client_obj=None, group=None,
                 clone=False, try_super=False, host=None, port=None,
                 extra_config=None, secure=False, anonymous=True,
                 useragent=None, userip=None):
        """
        Create the connection wrapper.
        Does not attempt to connect at this stage
        Initialises the omero.client

        :param username:    User name.
        :type username:     String
        :param passwd:      Password.
        :type passwd:       String
        :param client_obj:  omero.client
        :param group:       name of group to try to connect to
        :type group:        String
        :param clone:       If True, overwrite anonymous with False
        :type clone:        Boolean
        :param try_super:   Try to log on as super user ('system' group)
        :type try_super:    Boolean
        :param host:        Omero server host.
        :type host:         String
        :param port:        Omero server port.
        :type port:         Integer
        :param extra_config:    Dictionary of extra configuration
        :type extra_config:     Dict
        :param secure:      Initial underlying omero.client connection type
                            (True=SSL/False=insecure)
        :type secure:       Boolean
        :param anonymous:
        :type anonymous:    Boolean
        :param useragent:   Log which python clients use this connection.
                            E.g. 'OMERO.webadmin'
        :param userip:      Log client ip.
        :type useragent:    String
        """

        if extra_config is None:
            extra_config = []
        super(_BlitzGateway, self).__init__()
        self.CONFIG = GatewayConfig()
        self.c = client_obj
        if not type(extra_config) in (type(()), type([])):
            extra_config = [extra_config]
        self.extra_config = extra_config
        self.ice_config = [self.ICE_CONFIG]
        self.ice_config.extend(extra_config)
        self.ice_config = [os.path.abspath(str(x)) for x in [_f for _f in self.ice_config if _f]]

        self.host = host
        self.port = port
        self.secure = secure
        self.useragent = useragent
        self.userip = userip

        self._sessionUuid = None
        self._session_cb = None
        self._session = None
        self._lastGroupId = None
        self._anonymous = anonymous
        self._defaultOmeroGroup = None
        self._defaultOmeroUser = None
        self._maxPlaneSize = None

        self._connected = False
        self._user = None
        self._userid = None
        self._proxies = NoProxies()
        self._tracked_services = dict()
        if self.c is None:
            self._resetOmeroClient()
        else:
            # if we already have client initialised, we can go ahead and create
            # our services.
            self._connected = True
            self._createProxies()
            self.SERVICE_OPTS = self.createServiceOptsDict()
        if try_super:
            # self.c.ic.getProperties().getProperty('omero.gateway.admin_group')
            self.group = 'system'
        else:
            self.group = group and group or None

        # The properties we are setting through the interface
        self.setIdentity(username, passwd, not clone)

    def __enter__(self):
        """
        Enter a context manager, connect if necesaary
        Raise Exception if not connected

        with BlitzGateway('user', 'password', host='host') as conn:
            print list(conn.getObjects('Project'))
        """
        if not self._connected:
            r = self.connect()
            if not r:
                raise Exception("Connect failed")
        return self

    def __exit__(self, *args):
        """
        Exit a context manager, close connection
        """
        self.close()

    def _register_service(self, service_string, stack):
        """
        Register the results of traceback.extract_stack() at the time
        that a service was created.
        """
        service_string = str(service_string)
        self._tracked_services[service_string] = stack
        logger.info("Registered %s" % service_string)

    def _unregister_service(self, service_string):
        """
        Called on close of a service.
        """
        service_string = str(service_string)
        if service_string in self._tracked_services:
            del self._tracked_services[service_string]
            logger.info("Unregistered %s" % service_string)
        else:
            logger.warn("Cannot find registered service %s" % service_string)

    def _assert_unregistered(self, prefix="Service left open!"):
        """
        Log an ERROR for every stateful service that is open
        and was registered by this BlitzGateway instance.

        Return the number of unclosed services found.
        """

        try:
            stateful_services = self.c.getStatefulServices()
        except Exception as e:
            logger.warn("No services could be found.", e)
            stateful_services = []

        count = 0
        for s in stateful_services:
            service_string = str(s)
            stack_list = self._tracked_services.get(service_string, [])
            if stack_list:
                count += 1
                stack_msg = "".join(traceback.format_list(stack_list))
                logger.error("%s - %s\n%s" % (
                    prefix, service_string, stack_msg))
        return count

    def createServiceOptsDict(self):
        serviceOpts = ServiceOptsDict(self.c.getImplicitContext().getContext())
        serviceOpts.setOmeroGroup(self.getDefaultOmeroGroup())
        serviceOpts.setOmeroUser(self.getDefaultOmeroUser())
        return serviceOpts

    def setDefaultOmeroGroup(self, defaultOmeroGroup):
        self._defaultOmeroGroup = defaultOmeroGroup

    def setDefaultOmeroUser(self, defaultOmeroUser):
        self._defaultOmeroUser = defaultOmeroUser

    def getDefaultOmeroGroup(self):
        return self._defaultOmeroGroup

    def getDefaultOmeroUser(self):
        return self._defaultOmeroUser

    def getMaxPlaneSize(self):
        """
        Returns the maximum plane size the server will allow for an image to
        not be considered big i.e. width or height larger than this will
        trigger image pyramids to be calculated.

        This is useful for the client to filter images based on them needing
        pyramids or not, without the full rendering engine overhead.

        :return: tuple holding (max_plane_width, max_plane_height)
            as set on the server
        :rtype:  Tuple
        """
        if self._maxPlaneSize is None:
            c = self.getConfigService()
            self._maxPlaneSize = (
                int(c.getConfigValue('omero.pixeldata.max_plane_width')),
                int(c.getConfigValue('omero.pixeldata.max_plane_height')))
        return self._maxPlaneSize

    def getClientSettings(self):
        """
        Returns all client properties matching omero.client.*
        """
        try:
            return self.getConfigService().getClientConfigValues()
        except:
            return self.getConfigService().getClientConfigDefaults()

    def getRoiLimitSetting(self):
        try:
            roi_limit = (int(self.getConfigService().getConfigValue(
                             "omero.client.viewer.roi_limit")) or 2000)
        except:
            roi_limit = 2000
        return roi_limit

    def getInitialZoomLevel(self):
        """
        Returns default initial zoom level set on the server.
        """
        try:
            initzoom = (self.getConfigService().getConfigValue(
                        "omero.client.viewer.initial_zoom_level") or 0)
        except:
            initzoom = 0
        return initzoom

    def getInterpolateSetting(self):
        """
        Returns default interpolation setting on the server.
        This is a string but represents a boolean, E.g. 'true'

        :return:    String
        """
        try:
            interpolate = (
                toBoolean(self.getConfigService().getConfigValue(
                    "omero.client.viewer.interpolate_pixels"))
            )
        except:
            interpolate = True
        return interpolate

    def getDownloadAsMaxSizeSetting(self):
        """
        Returns default max size of images that can be downloaded as
        jpg, png or tiff, expressed as number of pixels.
        Default is 144000000 (12k * 12k image)

        :return:    Integer
        """
        size = 144000000
        try:
            size = self.getConfigService().getConfigValue(
                "omero.client.download_as.max_size")
            size = int(size)
        except:
            pass
        return size

    def getWebclientHost(self):
        """
        Returns default initial zoom level set on the server.
        """
        try:
            host = self.getConfigService() \
                       .getConfigValue("omero.client.web.host")
        except:
            host = None
        return host

    def isAnonymous(self):
        """
        Returns the anonymous flag

        :return:    Anonymous
        :rtype:     Boolean
        """
        return not not self._anonymous

    def getProperty(self, k):
        """
        Returns named property of the wrapped omero.client

        :return:    named client property
        """
        return self.c.getProperty(k)

    def clone(self):
        """
        Returns a new instance of this class, with all matching properties.
        TODO: Add anonymous and userAgent parameters?

        :return:    Clone of this connection wrapper
        :rtype:     :class:`_BlitzGateway`
        """
        return self.__class__(self._ic_props[omero.constants.USERNAME],
                              self._ic_props[omero.constants.PASSWORD],
                              host=self.host,
                              port=self.port,
                              extra_config=self.extra_config,
                              clone=True,
                              secure=self.secure,
                              anonymous=self._anonymous,
                              useragent=self.useragent,
                              userip=self.userip)
        # self.server, self.port, clone=True)

    def setIdentity(self, username, passwd, _internal=False):
        """
        Saves the username and password for later use, creating session etc

        :param username:    User name.
        :type username:     String
        :param passwd:      Password.
        :type passwd:       String
        :param _internal:   If False, set _anonymous = False
        :type _internal:    Boolean
        """
        self._ic_props = {omero.constants.USERNAME: username,
                          omero.constants.PASSWORD: passwd}
        if not _internal:
            self._anonymous = False

    def suConn(self, username, group=None, ttl=60000):
        """
        If current user isAdmin, return new connection owned by 'username'

        :param username:    Username for new connection
        :type username:     String
        :param group:       If specified, try to log in to this group
        :type group:        String
        :param ttl:         Timeout for new session
        :type ttl:          Int
        :return:            Clone of this connection,
                            with username's new Session
        :rtype:             :class:`_BlitzGateway`
                            or None if not admin or username unknown
        """
        if self.isAdmin():
            if group is None:
                e = self.getObject(
                    "Experimenter", attributes={'omeName': username})
                if e is None:
                    return
                group = e._obj._groupExperimenterMapSeq[0].parent.name.val
            p = omero.sys.Principal()
            p.name = username
            p.group = group
            p.eventType = "User"
            newConnId = self.getSessionService().createSessionWithTimeout(
                p, ttl)
            newConn = self.clone()
            newConn.connect(sUuid=newConnId.getUuid().val)
            return newConn

    def keepAlive(self):
        """
        Keeps service alive.
        Returns True if connected. If connection was lost, reconnecting.
        If connection failed, returns False and error is logged.

        :return:    True if connection alive.
        :rtype:     Boolean
        """

        try:
            if self.c.sf is None:  # pragma: no cover
                logger.debug('... c.sf is None, reconnecting')
                return self.connect()
            return self.c.sf.keepAlive(self._proxies['admin']._getObj())
        except Ice.ObjectNotExistException:  # pragma: no cover
            # The connection is there, but it has been reset, because the proxy
            # no longer exists...
            logger.debug(traceback.format_exc())
            logger.debug("... reset, not reconnecting")
            return False
        except Ice.ConnectionLostException:  # pragma: no cover
            # The connection was lost. This shouldn't happen, as we keep
            # pinging it, but does so...
            logger.debug(traceback.format_exc())
            logger.debug("... lost, reconnecting")
            # return self.connect()
            return False
        except Ice.ConnectionRefusedException:  # pragma: no cover
            # The connection was refused. We lost contact with
            # glacier2router...
            logger.debug(traceback.format_exc())
            logger.debug("... refused, not reconnecting")
            return False
        except omero.SessionTimeoutException:  # pragma: no cover
            # The connection is there, but it has been reset, because the proxy
            # no longer exists...
            logger.debug(traceback.format_exc())
            logger.debug("... reset, not reconnecting")
            return False
        except omero.RemovedSessionException:  # pragma: no cover
            # Session died on us
            logger.debug(traceback.format_exc())
            logger.debug("... session has left the building, not reconnecting")
            return False
        except Ice.UnknownException as x:  # pragma: no cover
            # Probably a wrapped RemovedSession
            logger.debug(traceback.format_exc())
            logger.debug('Ice.UnknownException: %s' % str(x))
            logger.debug(
                "... ice says something bad happened, not reconnecting")
            return False
        except:
            # Something else happened
            logger.debug(traceback.format_exc())
            logger.debug("... error not reconnecting")
            return False

    def seppuku(self, softclose=False):  # pragma: no cover
        """
        Terminates connection with killSession(). If softclose is False, the
        session is really terminated disregarding its connection refcount.
        If softclose is True then the connection refcount is decremented by 1.

        :param softclose:   Boolean

        ** Deprecated ** Use :meth:`close`.
        Our apologies for any offense caused by this previous method name.
        """
        warnings.warn("Deprecated. Use close()",
                      DeprecationWarning)
        self._connected = False
        oldC = self.c
        if oldC is not None:
            try:
                if softclose:
                    try:
                        r = oldC.sf.getSessionService().getReferenceCount(
                            self._sessionUuid)
                        oldC.closeSession()
                        if r < 2:
                            self._session_cb and self._session_cb.close(self)
                    except Ice.OperationNotExistException:
                        oldC.closeSession()
                else:
                    self._closeSession()
            finally:
                oldC.__del__()
                oldC = None
                self.c = None

        self._proxies = NoProxies()
        logger.info("closed connection (uuid=%s)" % str(self._sessionUuid))

    def close(self, hard=True):  # pragma: no cover
        """
        Terminates connection with killSession(), where the session is
        terminated regardless of its connection refcount, or closeSession().

        :param hard: If True, use killSession(), otherwise closeSession()
        """
        self._connected = False
        oldC = self.c
        for proxy in list(self._proxies.values()):
            proxy.close()
        if oldC is not None:
            try:
                if hard:
                    self._closeSession()
            finally:
                oldC.__del__()
                oldC = None
                self.c = None
                self._session = None

        self._proxies = NoProxies()
        logger.info("closed connection (uuid=%s)" % str(self._sessionUuid))

    def _createProxies(self):
        """
        Creates proxies to the server services. Called on connection or
        security switch. Doesn't actually create any services themselves.
        Created if/when needed. If proxies have been created already, they are
        resynced and reused.
        """

        if not isinstance(self._proxies, NoProxies):
            logger.debug("## Reusing proxies")
            for k, p in list(self._proxies.items()):
                p._resyncConn(self)
        else:
            logger.debug("## Creating proxies")
            self._proxies = {}
            self._proxies['admin'] = ProxyObjectWrapper(
                self, 'getAdminService')
            self._proxies['config'] = ProxyObjectWrapper(
                self, 'getConfigService')
            self._proxies['container'] = ProxyObjectWrapper(
                self, 'getContainerService')
            self._proxies['ldap'] = ProxyObjectWrapper(self, 'getLdapService')
            self._proxies['metadata'] = ProxyObjectWrapper(
                self, 'getMetadataService')
            self._proxies['query'] = ProxyObjectWrapper(
                self, 'getQueryService')
            self._proxies['pixel'] = ProxyObjectWrapper(
                self, 'getPixelsService')
            self._proxies['projection'] = ProxyObjectWrapper(
                self, 'getProjectionService')
            self._proxies['rawpixels'] = ProxyObjectWrapper(
                self, 'createRawPixelsStore')
            self._proxies['rendering'] = ProxyObjectWrapper(
                self, 'createRenderingEngine')
            self._proxies['rendsettings'] = ProxyObjectWrapper(
                self, 'getRenderingSettingsService')
            self._proxies['thumbs'] = ProxyObjectWrapper(
                self, 'createThumbnailStore')
            self._proxies['rawfile'] = ProxyObjectWrapper(
                self, 'createRawFileStore')
            self._proxies['repository'] = ProxyObjectWrapper(
                self, 'getRepositoryInfoService')
            self._proxies['roi'] = ProxyObjectWrapper(self, 'getRoiService')
            self._proxies['script'] = ProxyObjectWrapper(
                self, 'getScriptService')
            self._proxies['search'] = ProxyObjectWrapper(
                self, 'createSearchService')
            self._proxies['session'] = ProxyObjectWrapper(
                self, 'getSessionService')
            self._proxies['share'] = ProxyObjectWrapper(
                self, 'getShareService')
            self._proxies['sharedres'] = ProxyObjectWrapper(
                self, 'sharedResources')
            self._proxies['timeline'] = ProxyObjectWrapper(
                self, 'getTimelineService')
            self._proxies['types'] = ProxyObjectWrapper(
                self, 'getTypesService')
            self._proxies['update'] = ProxyObjectWrapper(
                self, 'getUpdateService')
        self._userid = None
        self._user = None
        self._ctx = None

        if self._session_cb:  # pragma: no cover
            if self._was_join:
                self._session_cb.join(self)
            else:
                self._session_cb.create(self)

    def setSecure(self, secure=True):
        """
        Switches between SSL and insecure (faster) connections to Blitz.
        The gateway must already be connected.

        :param secure:  If False, use an insecure connection
        :type secure:   Boolean
        """
        if hasattr(self.c, 'createClient') and (secure ^ self.c.isSecure()):
            oldC = self.c
            self.c = oldC.createClient(secure=secure)
            oldC.__del__()  # only needs to be called if previous doesn't throw
            self._createProxies()
            self.secure = secure

    def isSecure(self):
        """
        Returns 'True' if the underlying omero.clients.BaseClient is connected
        using SSL
        """
        return hasattr(self.c, 'isSecure') and self.c.isSecure() or False

    def _getSessionId(self):
        return self.c.getSessionId()

    def _createSession(self):
        """
        Creates a new session for the principal given in the constructor.
        Used during :meth`connect` method
        """
        s = self.c.createSession(self._ic_props[omero.constants.USERNAME],
                                 self._ic_props[omero.constants.PASSWORD])
        s.detachOnDestroy()
        self._sessionUuid = self._getSessionId()
        ss = self.c.sf.getSessionService()
        self._session = ss.getSession(self._sessionUuid)
        self._lastGroupId = None
        self._was_join = False
        if self.group is not None:
            # try something that fails if the user don't have permissions on
            # the group
            self.c.sf.getAdminService().getEventContext()
        self.setSecure(self.secure)
        self.c.sf.detachOnDestroy()
        self.SERVICE_OPTS = self.createServiceOptsDict()

    def _closeSession(self):
        """
        Close session.
        """
        self._session_cb and self._session_cb.close(self)
        try:
            if self.c:
                try:
                    self.c.getSession()
                except omero.ClientError:
                    return  # No session available
                self.c.killSession()
        except Glacier2.SessionNotExistException:  # pragma: no cover
            pass
        except:
            logger.warn(traceback.format_exc())

    def _resetOmeroClient(self):
        """
        Creates new omero.client object using self.host or self.ice_config (if
        host is None) Also tries to setAgent for the client
        """
        logger.debug(self.host)
        logger.debug(self.port)
        logger.debug(self.ice_config)

        if self.c is not None:
            self.c.__del__()
            self.c = None

        if self.host is not None:
            if self.port is not None:
                self.c = omero.client(
                    host=str(self.host), port=int(self.port),
                    args=['--Ice.Config='+','.join(self.ice_config)])
                # , pmap=['--Ice.Config='+','.join(self.ice_config)])
            else:
                self.c = omero.client(
                    host=str(self.host),
                    args=['--Ice.Config='+','.join(self.ice_config)])
        else:
            self.c = omero.client(
                args=['--Ice.Config='+','.join(self.ice_config)])

        if hasattr(self.c, "setAgent"):
            if self.useragent is not None:
                self.c.setAgent(self.useragent)
            else:
                self.c.setAgent("OMERO.py.gateway")

        if hasattr(self.c, "setIP"):
            if self.userip is not None:
                self.c.setIP(self.userip)

    def connect(self, sUuid=None):
        """
        Creates or retrieves connection for the given sessionUuid.
        Returns True if connected.

        :param sUuid:   omero_model_SessionI
        :return:        Boolean
        """

        logger.debug("Connect attempt, sUuid=%s, group=%s, self.sUuid=%s" % (
            str(sUuid), str(self.group), self._sessionUuid))
        if not self.c:  # pragma: no cover
            self._connected = False
            logger.debug("Ooops. no self._c")
            return False
        try:
            if self._sessionUuid is None and sUuid:
                self._sessionUuid = sUuid
            if self._sessionUuid is not None:
                try:
                    logger.debug('connected? %s' % str(self._connected))
                    if self._connected:
                        self._connected = False
                        logger.debug(
                            "was connected, creating new omero.client")
                        self._resetOmeroClient()
                    # timeout to allow this is $ omero config set
                    # omero.sessions.timeout 3600000
                    s = self.c.joinSession(self._sessionUuid)
                    s.detachOnDestroy()
                    self.SERVICE_OPTS = self.createServiceOptsDict()
                    logger.debug(
                        'Joined Session OK with Uuid: %s'
                        % (self._sessionUuid,))
                    self._was_join = True
                except Ice.SyscallException:  # pragma: no cover
                    raise
                except Exception as x:  # pragma: no cover
                    logger.debug("Error: " + str(x))
                    self._sessionUuid = None
                    if sUuid:
                        return False
            if self._sessionUuid is None:
                if sUuid:  # pragma: no cover
                    logger.debug("Uncaptured sUuid failure!")
                if self._connected:
                    self._connected = False
                    try:
                        logger.debug(
                            "Closing previous connection..."
                            "creating new client")
                        # args = self.c._ic_args
                        # logger.debug(str(args))
                        self._closeSession()
                        self._resetOmeroClient()
                        # self.c = omero.client(*args)
                    # pragma: no cover
                    except Glacier2.SessionNotExistException:
                        pass
                for key, value in list(self._ic_props.items()):
                    if isinstance(value, str):
                        value = value.encode('utf_8')
                    self.c.ic.getProperties().setProperty(key, value)
                if self._anonymous:
                    self.c.ic.getImplicitContext().put(
                        omero.constants.EVENT, 'Internal')
                if self.group is not None:
                    self.c.ic.getImplicitContext().put(
                        omero.constants.GROUP, self.group)
                try:
                    logger.debug("Creating Session...")
                    self._createSession()
                    logger.debug("Session created")
                except omero.SecurityViolation:
                    if self.group is not None:
                        # User don't have access to group
                        logger.debug("## User not in '%s' group" % self.group)
                        self.group = None
                        self._closeSession()
                        self._sessionUuid = None
                        self._connected = True
                        return self.connect()
                    else:  # pragma: no cover
                        logger.debug(
                            "BlitzGateway.connect().createSession(): " +
                            traceback.format_exc())
                        logger.info(
                            "first create session threw SecurityViolation, "
                            "retry (but only once)")
                        # time.sleep(10)
                        try:
                            self._createSession()
                        except omero.SecurityViolation:
                            if self.group is not None:
                                # User don't have access to group
                                logger.debug(
                                    "## User not in '%s' group" % self.group)
                                self.group = None
                                self._connected = True
                                return self.connect()
                            else:
                                raise
                except Ice.SyscallException:  # pragma: no cover
                    raise
                except:
                    logger.info("Failed to create session.")
                    logger.debug(
                        "BlitzGateway.connect().createSession(): " +
                        traceback.format_exc())
                    # time.sleep(10)
                    self._createSession()

            self._last_error = None
            self._createProxies()
            self._connected = True
            logger.info('created connection (uuid=%s)' %
                        str(self._sessionUuid))
        except Ice.SyscallException:  # pragma: no cover
            logger.debug('This one is a SyscallException', exc_info=True)
            raise
        except Ice.LocalException as x:  # pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        except Exception as x:  # pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        logger.debug(".. connected!")
        return True

    def getLastError(self):  # pragma: no cover
        """
        Returns error if thrown by _BlitzGateway.connect connect.

        :return: String
        """

        return self._last_error

    def isConnected(self):
        """
        Returns last status of connection.

        :return:    Boolean
        """

        return self._connected

    ########################
    # # Connection Stuff # #

    def getEventContext(self):
        """
        Returns omero_System_ice.EventContext.
        It contains: shareId, sessionId, sessionUuid, userId, userName,
        groupId, groupName, isAdmin, isReadOnly,
        eventId, eventType, eventType,
        memberOfGroups, leaderOfGroups
        Also saves context to self._ctx

        :return:    Event Context from admin service.
        :rtype:     :class:`omero.sys.EventContext`
        """
        if self._ctx is None:
            self._ctx = self._proxies['admin'].getEventContext()
        return self._ctx

    def getUserId(self):
        """
        Returns current experimenter id

        :return:    Current Experimenter id
        :rtype:     long
        """
        if self._userid is None:
            self._userid = self.getEventContext().userId
        return self._userid

    def setUserId(self, uid):
        """
        Sets current experimenter id
        """
        self._userid = uid
        self._user = None

    def getUser(self):
        """
        Returns current Experimenter.

        :return:    Current Experimenter
        :rtype:     :class:`ExperimenterWrapper`
        """
        if self._user is None:
            uid = self.getUserId()
            if uid is not None:
                self._user = self.getObject(
                    "Experimenter", self._userid) or None
        return self._user

    def getAdministrators(self):
        """
        Returns Experimenters with administration privileges.

        :return:    Current Experimenter
        :return:     Generator of :class:`BlitzObjectWrapper` subclasses
        """
        sysGroup = self.getObject(
            "ExperimenterGroup",
            self.getAdminService().getSecurityRoles().systemGroupId)
        for gem in sysGroup.copyGroupExperimenterMap():
            yield ExperimenterWrapper(self, gem.child)

    def getGroupFromContext(self):
        """
        Returns current omero_model_ExperimenterGroupI.

        :return:    omero.model.ExperimenterGroupI
        """
        admin_service = self.getAdminService()
        group = admin_service.getGroup(self.getEventContext().groupId)
        return ExperimenterGroupWrapper(self, group)

    def getCurrentAdminPrivileges(self):
        """
        Returns list of Admin Privileges for the current session.

        :return:    List of strings such as ["ModifyUser", "ModifyGroup"]
        """
        privileges = self.getAdminService().getCurrentAdminPrivileges()
        return [unwrap(p.getValue()) for p in privileges]

    def getAdminPrivileges(self, user_id):
        """
        Returns list of Admin Privileges for the specified user.

        :return:    List of strings such as ["ModifyUser", "ModifyGroup"]
        """
        privileges = self.getAdminService().getAdminPrivileges(
            omero.model.ExperimenterI(user_id, False))
        return [unwrap(p.getValue()) for p in privileges]

    def updateAdminPrivileges(self, exp_id, add=[], remove=[]):
        """
        Update the experimenter's Admin Priviledges, adding and removing.

        :param exp_id:  ID of experimenter to update
        :param add:     List of strings
        :param remove:  List of strings
        """
        admin = self.getAdminService()
        exp = omero.model.ExperimenterI(exp_id, False)

        privileges = set(self.getAdminPrivileges(exp_id))

        # Add via union
        privileges = privileges.union(set(add))
        # Remove via difference
        privileges = privileges.difference(set(remove))

        to_set = []
        for p in list(privileges):
            privilege = omero.model.AdminPrivilegeI()
            privilege.setValue(rstring(p))
            to_set.append(privilege)

        admin.setAdminPrivileges(exp, to_set)

    def isAdmin(self):
        """
        Checks if a user has administration privileges.

        :return:    Boolean
        """

        return self.getEventContext().isAdmin

    def isFullAdmin(self):
        """
        Checks if a user has full administration privileges.

        :return:    Boolean
        """

        if self.getEventContext().isAdmin:
            allPrivs = list(self.getEnumerationEntries('AdminPrivilege'))
            return len(allPrivs) == len(self.getCurrentAdminPrivileges())

        return False

    def isLeader(self, gid=None):
        """
        Is the current group (or a specified group) led by the current user?

        :return:    True if user leads the current group
        :rtype:     Boolean
        """
        if gid is None:
            gid = self.getEventContext().groupId
        if not isinstance(gid, LongType) or not isinstance(gid, IntType):
            gid = int(gid)
        if gid in self.getEventContext().leaderOfGroups:
            return True
        return False

    def canBeAdmin(self):
        """
        Checks if a user is in system group, i.e. can have administration
        privileges.

        :return:    Boolean
        """
        return 0 in self.getEventContext().memberOfGroups

    def canWrite(self, obj):
        """
        Checks if a user has write privileges to the given object.

        :param obj: Given object
        :return:    Boolean
        """

        return (self.isAdmin() or
                (self.getUserId() == obj.getDetails().getOwner().getId() and
                    obj.getDetails().getPermissions().isUserWrite()))

    def canOwnerWrite(self, obj):
        """
        Returns isUserWrite() from the object's permissions

        :param obj: Given object
        :return:    True if the objects's permissions allow owner to write
        """
        return obj.getDetails().getPermissions().isUserWrite()

    def getSession(self):
        """
        Returns the existing session, or creates a new one if needed

        :return:    The session from session service
        :rtype:     :class:`omero.model.session`
        """
        if self._session is None:
            ss = self.c.sf.getSessionService()
            self._session = ss.getSession(self._sessionUuid)
        return self._session

    def setGroupNameForSession(self, group):
        """
        Looks up the group by name, then delegates to
        :meth:`setGroupForSession`, returning the result

        :param group:       Group name
        :type group:        String
        :return:            True if group set successfully
        :rtype:             Boolean
        """
        a = self.getAdminService()
        g = a.lookupGroup(group)
        return self.setGroupForSession(g.getId().val)

    def setGroupForSession(self, groupid):
        """
        Sets the security context of this connection to the specified group

        :param groupid:     The ID of the group to switch to
        :type groupid:      Long
        :rtype:             Boolean
        :return:            True if the group was switched successfully
        """
        if self.getEventContext().groupId == groupid:
            return None
        if (groupid not in self._ctx.memberOfGroups and
                0 not in self._ctx.memberOfGroups):
            return False
        self._lastGroupId = self._ctx.groupId
        self._ctx = None
        for s in self.c.getStatefulServices():
            s.close()
        self.c.sf.setSecurityContext(
            omero.model.ExperimenterGroupI(groupid, False))
        return True

    def revertGroupForSession(self):
        """ Switches the group to the previous group """
        if self._lastGroupId is not None:
            self.setGroupForSession(self._lastGroupId)
            self._lastGroupId = None

    ############
    # Services #

    def getAdminService(self):
        """
        Gets reference to the admin service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['admin']

    def getQueryService(self):
        """
        Gets reference to the query service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['query']

    def getContainerService(self):
        """
        Gets reference to the container service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['container']

    def getPixelsService(self):
        """
        Gets reference to the pixels service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['pixel']

    def getMetadataService(self):
        """
        Gets reference to the metadata service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['metadata']

    def getRoiService(self):
        """
        Gets ROI service.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['roi']

    def getScriptService(self):
        """
        Gets script service.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['script']

    def createRawFileStore(self):
        """
        Gets a reference to the raw file store on this connection object or
        creates a new one if none exists.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['rawfile']

    def getRepositoryInfoService(self):
        """
        Gets reference to the repository info service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['repository']

    def getShareService(self):
        """
        Gets reference to the share service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['share']

    def getSharedResources(self):
        """
        Gets reference to the sharedresources from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['sharedres']

    def getTimelineService(self):
        """
        Gets reference to the timeline service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['timeline']

    def getTypesService(self):
        """
        Gets reference to the types service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['types']

    def getConfigService(self):
        """
        Gets reference to the config service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['config']

    def createRenderingEngine(self):
        """
        Creates a new rendering engine.
        This service is special in that it does not get cached inside
        BlitzGateway so every call to this function returns a new object,
        avoiding unexpected inherited states.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        rv = self._proxies['rendering']
        if rv._tainted:
            rv = self._proxies['rendering'] = rv.clone()
        rv.taint()
        return rv

    def getRenderingSettingsService(self):
        """
        Gets reference to the rendering settings service from
        ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['rendsettings']

    def createRawPixelsStore(self):
        """
        Gets a reference to the raw pixels store on this connection object or
        creates a new one if none exists.

        :return:    omero.gateway.ProxyObjectWrapper
        """

        return self._proxies['rawpixels']

    def createThumbnailStore(self):
        """
        Gets a reference to the thumbnail store on this connection object or
        creates a new one if none exists.

        :rtype: omero.gateway.ProxyObjectWrapper
        :return: The proxy wrapper of the thumbnail store
        """

        return self._proxies['thumbs']

    def createSearchService(self):
        """
        Gets a reference to the searching service on this connection object or
        creates a new one if none exists.

        :return: omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['search']

    def getUpdateService(self):
        """
        Gets reference to the update service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['update']

    def getSessionService(self):
        """
        Gets reference to the session service from ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['session']

    def createExporter(self):
        """
        New instance of non cached Exporter, wrapped in ProxyObjectWrapper.

        :return:    omero.gateway.ProxyObjectWrapper
        """
        return ProxyObjectWrapper(self, 'createExporter')

    ####################
    # Read-only status #

    def canCreate(self):
        """
        Get the read-only status of the server.
        Warning: This is EXPERIMENTAL API that is subject to change.

        :return:  True if the server is wholly in read-write mode,
                  False if the server is wholly in read-only mode,
                  otherwise None
        """
        key_regex = r'^omero\.cluster\.read_only\.runtime\.'
        properties = self.getConfigService().getConfigValues(key_regex)
        values = frozenset(list(properties.values()))
        if not values:
            return True
        elif len(values) == 1:
            return 'false' in values
        else:
            return None

    #############################
    # Top level object fetchers #

    def listProjects(self, eid=None):
        """
        List every Project controlled by the security system.

        :param eid:         Filters Projects by owner ID
        :rtype:             :class:`ProjectWrapper` list
        """

        params = omero.sys.Parameters()
        params.theFilter = omero.sys.Filter()
        # if only_owned:
        #     params.theFilter.ownerId = rlong(self._userid)
        # elif
        if eid is not None:
            params.theFilter.ownerId = rlong(eid)

        return self.getObjects("Project", params=params)

    def listScreens(self, eid=None):
        """
        List every Screens controlled by the security system.

        :param eid:         Filters Screens by owner ID
        :rtype:             :class:`ProjectWrapper` list
        """

        params = omero.sys.Parameters()
        params.theFilter = omero.sys.Filter()
        # if only_owned:
        #     params.theFilter.ownerId = rlong(self._userid)
        # elif
        if eid is not None:
            params.theFilter.ownerId = rlong(eid)

        return self.getObjects("Screen", params=params)

    def listOrphans(self, obj_type, eid=None, params=None, loadPixels=False):
        """
        List orphaned Datasets, Images, Plates controlled by the security
        system, Optionally filter by experimenter 'eid'

        :param obj_type:    'Dataset', 'Image', 'Plate'
        :param eid:         experimenter id
        :type eid:          Long
        :param params:      omero.sys.ParametersI, can be used for pagination,
                            filtering etc.
        :param attributes:  Map of key-value pairs to filter results by.
                            Key must be attribute of obj_type.
                            E.g. 'name', 'ns'
        :return:            Generator yielding Datasets
        :rtype:             :class:`DatasetWrapper` generator

        """

        links = {'Dataset': ('ProjectDatasetLink', DatasetWrapper),
                 'Image': ('DatasetImageLink', ImageWrapper),
                 'Plate': ('ScreenPlateLink', PlateWrapper)}

        if obj_type not in list(links.keys()):
            raise AttributeError("obj_type must be in %s" % str(list(links.keys())))

        if params is None:
            params = omero.sys.ParametersI()

        wrapper = KNOWN_WRAPPERS.get(obj_type.lower(), None)
        query = wrapper._getQueryString()[0]

        if loadPixels and obj_type == 'Image':
            # left outer join so we don't exclude
            # images that have no thumbnails
            query += (" join fetch obj.pixels as pix "
                      "left outer join fetch pix.thumbnails")

        if eid is not None:
            params.exp(eid)
            query += " where owner.id = (:eid)"
            params.map["eid"] = params.theFilter.ownerId

        query += "where" not in query and " where " or " and "
        query += " not exists (select obl from %s as obl where " \
                 "obl.child=obj.id) " % (links[obj_type][0])

        if obj_type == 'Image':
            query += " and not exists ( select ws from WellSample as ws "\
                     "where ws.image=obj.id "
            if eid is not None:
                query += " and ws.details.owner.id=:eid "
            query += ")"

        query += " order by lower(obj.name), obj.id"

        result = self.getQueryService().findAllByQuery(
            query, params, self.SERVICE_OPTS)
        for r in result:
            yield wrapper(self, r)
    #################################################
    # IAdmin

    # GROUPS

    def listGroups(self):
        """
        Look up all experimenters and related groups.
        Groups are also loaded

        :return:    All experimenters
        :rtype:     :class:`ExperimenterWrapper` generator
        """

        admin_serv = self.getAdminService()
        for exp in admin_serv.lookupGroups():
            yield ExperimenterGroupWrapper(self, exp)

    def getDefaultGroup(self, eid):
        """
        Retrieve the default group for the given user id.

        :param eid:     Experimenter ID
        :type eid:      Long
        :return:        The default group for user
        :rtype:         :class:`ExperimenterGroupWrapper`
        """

        admin_serv = self.getAdminService()
        dgr = admin_serv.getDefaultGroup(int(eid))
        return ExperimenterGroupWrapper(self, dgr)

    def getOtherGroups(self, eid):
        """
        Fetch all groups of which the given user is a member.
        The returned groups will have all fields filled in and all collections
        unloaded.

        :param eid:         Experimenter ID
        :type eid:          Long
        :return:            Generator of groups for user
        :rtype:             :class:`ExperimenterGroupWrapper` generator
        """

        admin_serv = self.getAdminService()
        for gr in admin_serv.containedGroups(int(eid)):
            yield ExperimenterGroupWrapper(self, gr)

    def getGroupsLeaderOf(self):
        """
        Look up Groups where current user is a leader of.

        :return:        Groups that current user leads
        :rtype:         :class:`ExperimenterGroupWrapper` generator
        """

        system_groups = [
            self.getAdminService().getSecurityRoles().userGroupId]
        if len(self.getEventContext().leaderOfGroups) > 0:
            for g in self.getObjects("ExperimenterGroup",
                                     self.getEventContext().leaderOfGroups):
                if g.getId() not in system_groups:
                    yield g

    def getGroupsMemberOf(self):
        """
        Look up Groups where current user is a member of (except "user" group).

        :return:        Current users groups
        :rtype:         :class:`ExperimenterGroupWrapper` generator
        """

        system_groups = [
            self.getAdminService().getSecurityRoles().userGroupId]
        if len(self.getEventContext().memberOfGroups) > 0:
            for g in self.getObjects("ExperimenterGroup",
                                     self.getEventContext().memberOfGroups):
                if g.getId() not in system_groups:
                    yield g

    def createGroup(self, name, owner_Ids=None, member_Ids=None, perms=None,
                    description=None, ldap=False):
        """
        Creates a new ExperimenterGroup.
        Must have Admin permissions to call this.

        :param name:        New group name
        :param owner_Ids:   Option to add existing Experimenters
                            as group owners
        :param member_Ids:  Option to add existing Experimenters
                            as group members
        :param perms:       New group permissions.
                            E.g. 'rw----' (private), 'rwr---'(read-only),
                            'rwrw--'
        :param description: Group description
        :param ldap:        Group ldap setting
        """
        admin_serv = self.getAdminService()

        group = omero.model.ExperimenterGroupI()
        group.name = rstring(str(name))
        group.description = (
            (description != "" and description is not None) and
            rstring(str(description)) or None)
        if perms is not None:
            group.details.permissions = omero.model.PermissionsI(perms)
        group.ldap = rbool(ldap)

        gr_id = admin_serv.createGroup(group)

        if owner_Ids is not None:
            group_owners = [
                owner._obj for owner in self.getObjects(
                    "Experimenter", owner_Ids)]
            admin_serv.addGroupOwners(
                omero.model.ExperimenterGroupI(gr_id, False), group_owners)

        if member_Ids is not None:
            group_members = [
                member._obj for member in self.getObjects(
                    "Experimenter", member_Ids)]
            for user in group_members:
                admin_serv.addGroups(
                    user, [omero.model.ExperimenterGroupI(gr_id, False)])

        return gr_id

    # EXPERIMENTERS

    def findExperimenters(self, start=''):
        """
        Return a generator for all Experimenters whose omeName starts with
        'start'. Experimenters ordered by omeName.

        :param start:   omeName must start with these letters
        :type start:    String
        :return:        Generator of experimenters
        :rtype:         :class:`ExperimenterWrapper` generator
        """

        if isinstance(start, UnicodeType):
            start = start.encode('utf8')
        params = omero.sys.Parameters()
        params.map = {'start': rstring('%s%%' % start.lower())}
        q = self.getQueryService()
        rv = q.findAllByQuery(
            "from Experimenter e where lower(e.omeName) like :start",
            params, self.SERVICE_OPTS)
        rv.sort(lambda x, y: cmp(x.omeName.val, y.omeName.val))
        for e in rv:
            yield ExperimenterWrapper(self, e)

    def containedExperimenters(self, gid):
        """
        Fetch all users contained in this group.
        The returned users will have all fields filled in and all collections
        unloaded.

        :param gid:     Group ID
        :type gid:      Long
        :return:        Generator of experimenters
        :rtype:         :class:`ExperimenterWrapper` generator
        """

        admin_serv = self.getAdminService()
        for exp in admin_serv.containedExperimenters(int(gid)):
            yield ExperimenterWrapper(self, exp)

    def listColleagues(self):
        """
        Look up users who are a member of the current user active group.
        Returns None if the group is private and isn't lead by the current user

        :return:    Generator of Experimenters or None
        :rtype:     :class:`ExperimenterWrapper` generator
        """

        default = self.getObject(
            "ExperimenterGroup", self.getEventContext().groupId)
        if not default.isPrivate() or self.isLeader():
            for d in default.copyGroupExperimenterMap():
                if d is None:
                    continue
                if d.child.id.val != self.getUserId():
                    yield ExperimenterWrapper(self, d.child)

    def groupSummary(self, gid=None, exclude_self=False):
        """
        Returns unsorted lists of 'leaders' and 'members' of the specified
        group (default is current group) as a dict with those keys.

        :return:    {'leaders': list :class:`ExperimenterWrapper`,
                     'colleagues': list :class:`ExperimenterWrapper`}
        :rtype:     dict

        ** Deprecated ** Use :meth:`ExperimenterGroupWrapper.groupSummary`.
        """
        warnings.warn(
            "Deprecated. Use ExperimenterGroupWrapper.groupSummary()",
            DeprecationWarning)

        if gid is None:
            gid = self.getEventContext().groupId
        default = self.getObject("ExperimenterGroup", gid)
        leaders, colleagues = default.groupSummary(exclude_self)
        return {"leaders": leaders, "colleagues": colleagues}

    def listStaffs(self):
        """
        Look up users who are members of groups lead by the current user.

        :return:    Members of groups lead by current user
        :rtype:     :class:`ExperimenterWrapper` generator
        """

        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["gids"] = rlist(
            [rlong(a) for a in set(self.getEventContext().leaderOfGroups)])
        sql = ("select e from Experimenter as e where exists "
               "( select gem from GroupExperimenterMap as gem "
               "where gem.child = e.id and gem.parent.id in (:gids)) "
               "order by e.omeName")
        for e in q.findAllByQuery(sql, p, self.SERVICE_OPTS):
            if e.id.val != self.getUserId():
                yield ExperimenterWrapper(self, e)

    def listOwnedGroups(self):
        """
        Looks up owned groups for the logged user.

        :return:    Groups owned by current user
        :rtype:     :class:`ExperimenterGroupWrapper` generator
        """

        exp = self.getUser()
        for gem in exp.copyGroupExperimenterMap():
            if gem is None:
                continue
            if gem.owner.val:
                yield ExperimenterGroupWrapper(self, gem.parent)

    def getFreeSpace(self):
        """
        Returns the free or available space on this file system
        including nested subdirectories.

        :return:    Free space in bytes
        :rtype:     Int
        """

        rep_serv = self.getRepositoryInfoService()
        return rep_serv.getFreeSpaceInKilobytes() * 1024

    def getFilesetFilesInfo(self, imageIds):
        """
        Gets summary of Original Files that are part of the FS Fileset linked
        to images Returns a dict of files 'count' and sum of 'size'

        :param imageIds:    Image IDs list
        :return:            Dict of files 'count' and 'size'
        """
        params = omero.sys.ParametersI()
        params.addIds(imageIds)
        query = 'select count(fse), sum(fse.originalFile.size) '\
                'from FilesetEntry as fse where fse.id in ('\
                '   select distinct(i_fse.id) from FilesetEntry as i_fse '\
                '   join i_fse.fileset as i_fileset'\
                '   join i_fileset.images as i_image '\
                '   where i_image.id in (:ids)'\
                ')'
        queryService = self.getQueryService()
        count, size = queryService.projection(
            query, params, self.SERVICE_OPTS
        )[0]
        if size is None:
            size = 0

        query = 'select ann.id, ann.ns, ann.textValue '\
                'from Fileset as fileset '\
                'join fileset.annotationLinks as a_link '\
                'join a_link.child as ann '\
                'where fileset.id in ('\
                '   select distinct(i_fileset.id) from Fileset as i_fileset '\
                '   join i_fileset.images as i_image '\
                '   where i_image.id in (:ids)'\
                ')'
        queryService = self.getQueryService()
        annotations = list()
        rows = queryService.projection(query, params, self.SERVICE_OPTS)
        for row in rows:
            annotation_id, ns, text_value = row
            annotation = {
                'id': unwrap(annotation_id), 'ns': unwrap(ns)
            }
            if text_value is not None:
                annotation['value'] = unwrap(text_value)
            annotations.append(annotation)
        return {
            'fileset': True, 'count': unwrap(count), 'size': unwrap(size),
            'annotations': annotations
        }

    def getArchivedFilesInfo(self, imageIds):
        """
        Gets summary of Original Files that are archived from OMERO 4 imports
        Returns a dict of files 'count' and sum of 'size'

        :param imageIds:    Image IDs list
        :return:            Dict of files 'count' and 'size'
        """
        params = omero.sys.ParametersI()
        params.addIds(imageIds)
        query = 'select count(link), sum(link.parent.size) '\
                'from PixelsOriginalFileMap as link '\
                'where link.id in ('\
                '    select distinct(i_link.id) '\
                '        from PixelsOriginalFileMap as i_link '\
                '    where i_link.child.image.id in (:ids)'\
                ')'
        queryService = self.getQueryService()
        count, size = queryService.projection(
            query, params, self.SERVICE_OPTS
        )[0]
        if size is None:
            size = 0
        return {'fileset': False, 'count': unwrap(count), 'size': unwrap(size)}

    ############################
    # Timeline service getters #

    def timelineListImages(self, tfrom=None, tto=None, limit=10,
                           only_owned=True):
        """
        List images based on their creation times.
        If both tfrom and tto are None, grab the most recent batch.

        :param tfrom:       milliseconds since the epoch for start date
        :param tto:         milliseconds since the epoch for end date
        :param limit:       maximum number of results
        :param only_owned:  Only owned by the logged user. Boolean.
        :return:            Generator yielding :class:`_ImageWrapper`
        :rtype:             :class:`ImageWrapper` generator
        """

        tm = self.getTimelineService()
        p = omero.sys.Parameters()
        f = omero.sys.Filter()
        if only_owned:
            f.ownerId = rlong(self.getEventContext().userId)
            f.groupId = rlong(self.getEventContext().groupId)
        else:
            f.ownerId = rlong(-1)
            f.groupId = None
        f.limit = rint(limit)
        p.theFilter = f
        if tfrom is None and tto is None:
            for e in tm.getMostRecentObjects(['Image'], p, False)["Image"]:
                yield ImageWrapper(self, e)
        else:
            if tfrom is None:
                tfrom = 0
            if tto is None:
                tto = time.time() * 1000
            for e in tm.getByPeriod(
                    ['Image'], rtime(int(tfrom)),
                    rtime(int(tto)), p, False)['Image']:
                yield ImageWrapper(self, e)

    ###########################
    # Specific Object Getters #

    def getObject(self, obj_type, oid=None, params=None, attributes=None,
                  opts=None):
        """
        Retrieve single Object by type E.g. "Image" or None if not found.
        If more than one object found, raises ome.conditions.ApiUsageException
        See :meth:`getObjects` for more info.

        :param obj_type:    Object type, e.g. "Project" see above
        :type obj_type:     String
        :param ids:         object IDs
        :type ids:          List of Long
        :param params:      omero.sys.Parameters, can be used for pagination,
                            filtering etc.
        :param attributes:  Map of key-value pairs to filter results by.
                            Key must be attribute of obj_type.
                            E.g. 'name', 'ns'
        :return:
        """
        oids = (oid is not None) and [oid] or None
        query, params, wrapper = self.buildQuery(
            obj_type, oids, params, attributes, opts)
        result = self.getQueryService().findByQuery(
            query, params, self.SERVICE_OPTS)
        if result is not None:
            return wrapper(self, result)

    def getObjects(self, obj_type, ids=None, params=None, attributes=None,
                   respect_order=False, opts=None):
        """
        Retrieve Objects by type E.g. "Image"
        Returns generator of appropriate :class:`BlitzObjectWrapper` type.
        E.g. :class:`ImageWrapper`. If ids is None, all available objects will
        be returned. i.e. listObjects() Filter objects by attributes. E.g.
        attributes={'name':name}

        :param obj_type:    Object type, e.g. "Project" see above
        :type obj_type:     String
        :param ids:         object IDs
        :type ids:          List of Long
        :param params:      omero.sys.Parameters, can be used for pagination,
                            & filtering by owner. Takes precedence over opts.
        :param attributes:  Dict of key-value pairs to filter results by.
                            Key must be attribute of obj_type.
                            E.g. 'name', 'ns'
        :param respect_order:   Returned items will be ordered according
                                to the order of ids
        :param opts:        Dict of additional options for filtering or
                            defining extra data to load.
                            offset, limit and owner for all objects.
                            Additional opts handled by _getQueryString()
                            e.g. filter Dataset by 'project'
        :return:            Generator of :class:`BlitzObjectWrapper` subclasses
        """
        query, params, wrapper = self.buildQuery(
            obj_type, ids, params, attributes, opts)
        qs = self.getQueryService()
        result = qs.findAllByQuery(query, params, self.SERVICE_OPTS)
        if respect_order and ids is not None:
            idMap = {}
            for r in result:
                idMap[r.id.val] = r
            ids = unwrap(ids)       # in case we had a list of rlongs
            result = [idMap.get(i) for i in ids if i in idMap]
        for r in result:
            yield wrapper(self, r)

    def buildQuery(self, obj_type, ids=None, params=None, attributes=None,
                   opts=None):
        """
        Prepares a query for iQuery. Also prepares params and determines
        appropriate wrapper for result Returns (query, params, wrapper) which
        can be used with the appropriate query method. Used by
        :meth:`getObjects` and :meth:`getObject` above.

        :param obj_type:    Object type, e.g. "Project" see above
        :type obj_type:     String
        :param ids:         object IDs
        :type ids:          List of Long
        :param params:      omero.sys.Parameters, can be used for pagination,
                            & filtering by owner. Takes precedence over opts.
        :param attributes:  Dict of key-value pairs to filter results by.
                            Key must be attribute of obj_type.
                            E.g. 'name', 'ns'
        :param opts:        Dict of additional options for filtering or
                            defining extra data to load.
                            offset, limit and owner for all objects.
                            Also 'order_by': 'obj.name' to order results.
                            Additional opts handled by _getQueryString()
                            e.g. filter Dataset by 'project'
        :return:            (query, params, wrapper)
        """

        if isinstance(obj_type, StringTypes):
            wrapper = KNOWN_WRAPPERS.get(obj_type.lower(), None)
            if wrapper is None:
                raise KeyError(
                    "obj_type of %s not supported by getOjbects(). "
                    "E.g. use 'Image' etc" % obj_type)
        else:
            raise AttributeError(
                "getObjects uses a string to define obj_type, E.g. "
                "'Image' not %r" % obj_type)

        owner = None
        order_by = None
        offset = None
        limit = None

        # We get the query from the ObjectWrapper class:
        if wrapper.__name__ == "_wrap":
            # If wrapper is the AnnotationWrapper._wrap class method, we
            # need to get the underlying AnnotationWrapper class
            cls = wrapper()
        else:
            cls = wrapper
        query, clauses, baseParams = cls._getQueryString(opts)

        # Handle dict of parameters -> convert to ParametersI()
        if opts is not None:
            # Parse opts dict to build params
            if 'offset' in opts and 'limit' in opts:
                limit = opts['limit']
                offset = opts['offset']
            if 'owner' in opts:
                owner = rlong(opts['owner'])
            if 'order_by' in opts:
                order_by = opts['order_by']
        # Handle additional Parameters - need to retrieve owner filter
        if params is not None and params.theFilter is not None:
            if params.theFilter.ownerId is not None:
                owner = params.theFilter.ownerId
            # pagination
            ofs = params.theFilter.offset
            lmt = params.theFilter.limit
            if ofs is not None and lmt is not None:
                offset = ofs.val
                limit = lmt.val
            # Other params args will be ignored unless we handle here

        if limit is not None and offset is not None:
            baseParams.page(offset, limit)

        # getting object by ids
        if ids is not None:
            clauses.append("obj.id in (:ids)")
            baseParams.map["ids"] = rlist([rlong(a) for a in ids])

        # support filtering by owner (not for some object types)
        if (owner is not None and
                obj_type.lower() not in
                ["experimentergroup", "experimenter"]):
            clauses.append("owner.id = (:eid)")
            baseParams.map["eid"] = owner

        # finding by attributes
        if attributes is not None:
            for k, v in list(attributes.items()):
                clauses.append('obj.%s=:%s' % (k, k))
                baseParams.map[k] = omero_type(v)
        if clauses:
            query += " where " + (" and ".join(clauses))

        # Order by... e.g. 'lower(obj.name)' or 'obj.column, obj.row' for wells
        if order_by is not None:
            query += " order by %s, obj.id" % order_by

        return (query, baseParams, wrapper)

    def buildCountQuery(self, obj_type, opts=None):
        """
        Prepares a 'projection' query to count objects.

        Based on buildQuery(), we modify the query to only return a count.
        Modified query does not 'fetch' any data or add any other
        unnecessary objects to query.
        We return just the query and omero.sys.ParametersI for the query.

        :param obj_type:    Object type, e.g. "Project" see above
        :param opts:        Dict of options for filtering by
                            offset, limit and owner for all objects.
                            Additional opts handled by _getQueryString()
                            e.g. filter Dataset by 'project'
        :return:            (query, params)
        """
        # We disable pagination since we want to count ALL results
        opts_copy = opts.copy()
        if 'limit' in opts_copy:
            del opts_copy['limit']

        # Get query with other options
        query, params, wrapper = self.buildQuery(obj_type, opts=opts_copy)

        # Modify query to only select count()
        query = query.replace("select obj ", "select count(distinct obj) ")
        query = query.replace("fetch", "")
        query = query.split("order by")[0]
        return query, params

    def listFileAnnotations(self, eid=None, toInclude=[], toExclude=[]):
        """
        Lists FileAnnotations created by users, filtering by namespaces if
        specified. If NO namespaces are specified, then 'known' namespaces are
        excluded by default, such as original files and companion files etc.
        File objects are loaded so E.g. file name is available without lazy
        loading.

        :param eid:         Filter results by this owner Id
        :param toInclude:   Only return annotations with these namespaces.
                            List of strings.
        :param toExclude:   Don't return annotations with these namespaces.
                            List of strings.
        :return:            Generator of :class:`FileAnnotationWrapper`
                            - with files loaded.
        """

        params = omero.sys.Parameters()
        params.theFilter = omero.sys.Filter()
        if eid is not None:
            params.theFilter.ownerId = rlong(eid)

        if len(toInclude) == 0 and len(toExclude) == 0:
            toExclude.append(omero.constants.namespaces.NSCOMPANIONFILE)
            toExclude.append(omero.constants.annotation.file.ORIGINALMETADATA)
            toExclude.append(omero.constants.namespaces.NSEXPERIMENTERPHOTO)

        anns = self.getMetadataService().loadSpecifiedAnnotations(
            "FileAnnotation", toInclude, toExclude, params, self.SERVICE_OPTS)

        for a in anns:
            yield(FileAnnotationWrapper(self, a))

    def getAnnotationLinks(self, parent_type, parent_ids=None, ann_ids=None,
                           ns=None, params=None):
        """
        Retrieve Annotation Links by parent_type E.g. "Image". Not Ordered.
        Returns generator of :class:`AnnotationLinkWrapper`
        If parent_ids is None, all available objects will be returned.
        i.e. listObjects()

        :param obj_type:    Object type, e.g. "Project" see above
        :type obj_type:     String
        :param ids:         object IDs
        :type ids:          List of Long
        :return:            Generator yielding wrapped objects.
        """

        if parent_type.lower() not in KNOWN_WRAPPERS:
            wrapper_types = ", ".join(list(KNOWN_WRAPPERS.keys()))
            err_msg = ("getAnnotationLinks() does not support type: '%s'. "
                       "Must be one of: %s" % (parent_type, wrapper_types))
            raise AttributeError(err_msg)
        wrapper = KNOWN_WRAPPERS.get(parent_type.lower(), None)
        class_string = wrapper().OMERO_CLASS
        # E.g. AnnotationWrappers have no OMERO_CLASS
        if class_string is None and "annotation" in parent_type.lower():
            class_string = "Annotation"

        query = ("select annLink from %sAnnotationLink as annLink "
                 "join fetch annLink.details.owner as owner "
                 "join fetch annLink.details.creationEvent "
                 "join fetch annLink.child as ann "
                 "join fetch ann.details.owner "
                 "join fetch ann.details.creationEvent "
                 "join fetch annLink.parent as parent" % class_string)

        q = self.getQueryService()
        if params is None:
            params = omero.sys.Parameters()
        if params.map is None:
            params.map = {}

        clauses = []
        if parent_ids:
            clauses.append("parent.id in (:pids)")
            params.map["pids"] = rlist([rlong(a) for a in parent_ids])

        if ann_ids:
            clauses.append("ann.id in (:ann_ids)")
            params.map["ann_ids"] = rlist([rlong(a) for a in ann_ids])

        if ns:
            clauses.append("ann.ns in (:ns)")
            params.map["ns"] = rstring(ns)

        if params.theFilter and params.theFilter.ownerId:
            clauses.append("owner.id = (:eid)")
            params.map["eid"] = params.theFilter.ownerId

        if len(clauses) > 0:
            query += " where %s" % (" and ".join(clauses))

        result = q.findAllByQuery(query, params, self.SERVICE_OPTS)
        for r in result:
            yield AnnotationLinkWrapper(self, r)

    def countAnnotations(self, obj_type, obj_ids=[]):
        """
        Count the annotions linked to the given objects

        :param obj_type:   The type of the object the annotations are linked to
        :param obj_ids:    List of object ids
        :return:           Dictionary of annotation counts per annotation type
        """

        counts = {
            "TagAnnotation": 0,
            "FileAnnotation": 0,
            "CommentAnnotation": 0,
            "LongAnnotation": 0,
            "MapAnnotation": 0,
            "OtherAnnotation": 0}

        if obj_type is None or not obj_ids:
            return counts

        ctx = self.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(-1)

        params = omero.sys.ParametersI()
        params.addIds(obj_ids)
        params.add('ratingns',
                   rstring(omero.constants.metadata.NSINSIGHTRATING))

        q = """
            select sum( case when an.ns = :ratingns
                        and an.class = LongAnnotation
                        then 1 else 0 end),
                sum( case when (an.ns is null or an.ns != :ratingns)
                               and an.class = LongAnnotation
                               then 1 else 0 end),
               sum( case when an.class != LongAnnotation
                        then 1 else 0 end ), type(an.class)
               from Annotation an where an.id in
                    (select distinct(ann.id) from %sAnnotationLink ial
                        join ial.child as ann
                        join ial.parent as i
                where i.id in (:ids))
                    group by an.class
            """ % obj_type

        queryResult = self.getQueryService().projection(q, params, ctx)

        for r in queryResult:
            ur = unwrap(r)
            if ur[3] == 'ome.model.annotations.LongAnnotation':
                counts['LongAnnotation'] += ur[0]
                counts['OtherAnnotation'] += ur[1]
            elif ur[3] == 'ome.model.annotations.CommentAnnotation':
                counts['CommentAnnotation'] += ur[2]
            elif ur[3] == 'ome.model.annotations.TagAnnotation':
                counts['TagAnnotation'] += ur[2]
            elif ur[3] == 'ome.model.annotations.FileAnnotation':
                counts['FileAnnotation'] += ur[2]
            elif ur[3] == 'ome.model.annotations.MapAnnotation':
                counts['MapAnnotation'] += ur[2]
            else:
                counts['OtherAnnotation'] += ur[2]

        return counts

    def listOrphanedAnnotations(self, parent_type, parent_ids, eid=None,
                                ns=None, anntype=None, addedByMe=True):
        """
        Retrieve all Annotations not linked to the given parents: Projects,
        Datasets, Images, Screens, Plates OR Wells etc.

        :param parent_type:     E.g. 'Dataset', 'Image' etc.
        :param parent_ids:      IDs of the parent.
        :param eid:             Optional filter by Annotation owner
        :param ns:              Filter by annotation namespace
        :param anntype:         Optional specify 'Text', 'Tag', 'File',
                                Long', 'Boolean'
        :return:                Generator yielding AnnotationWrappers
        :rtype:                 :class:`AnnotationWrapper` generator
        """

        if anntype is not None:
            if (anntype.title()
                    not in ('Text', 'Tag', 'File', 'Long', 'Boolean')):
                raise AttributeError(
                    'Use annotation type: Text, Tag, File, Long, Boolean')
            sql = "select an from %sAnnotation as an " % anntype.title()
        else:
            sql = "select an from Annotation as an " \

        if anntype.title() == "File":
            sql += " join fetch an.file "

        p = omero.sys.Parameters()
        p.map = {}

        filterlink = ""
        if addedByMe:
            userId = self.getUserId()
            filterlink = " and link.details.owner.id=:linkOwner"
            p.map["linkOwner"] = rlong(userId)

        q = self.getQueryService()
        wheres = []

        if len(parent_ids) == 1:
            # We can use a single query to exclude links to a single parent
            p.map["oid"] = rlong(parent_ids[0])
            wheres.append(
                "not exists ( select link from %sAnnotationLink as link "
                "where link.child=an.id and link.parent.id=:oid%s)"
                % (parent_type, filterlink))
        else:
            # for multiple parents, we first need to find annotations linked to
            # ALL of them, then exclude those from query
            p.map["oids"] = omero.rtypes.wrap(parent_ids)
            query = ("select link.child.id, count(link.id) "
                     "from %sAnnotationLink link where link.parent.id in "
                     "(:oids)%s group by link.child.id"
                     % (parent_type, filterlink))
            # count annLinks and check if count == number of parents (all
            # parents linked to annotation)
            usedAnnIds = [e[0].getValue() for e in
                          q.projection(query, p, self.SERVICE_OPTS)
                          if e[1].getValue() == len(parent_ids)]
            if len(usedAnnIds) > 0:
                p.map["usedAnnIds"] = omero.rtypes.wrap(usedAnnIds)
                wheres.append("an.id not in (:usedAnnIds)")

        if ns is None:
            wheres.append("an.ns is null")
        else:
            p.map["ns"] = rlist([rstring(n) for n in ns])
            wheres.append("(an.ns not in (:ns) or an.ns is null)")
        if eid is not None:
            wheres.append("an.details.owner.id=:eid")
            p.map["eid"] = rlong(eid)

        if len(wheres) > 0:
            sql += "where " + " and ".join(wheres)

        for e in q.findAllByQuery(sql, p, self.SERVICE_OPTS):
            yield AnnotationWrapper._wrap(self, e)

    def getAnnotationCounts(self, objDict={}):
        """
        Get the annotion counts for the given objects
        """

        obj_type = None
        obj_ids = []
        for key in objDict:
            for o in objDict[key]:
                if obj_type is not None and obj_type != key:
                    raise AttributeError(
                        "getAnnotationCounts cannot be used with "
                        "different types of objects")
                obj_type = key
                obj_ids.append(o.id)

        if obj_type is None:
            return self.countAnnotations()

        obj_type = obj_type.title().replace("Plateacquisition",
                                            "PlateAcquisition")

        return self.countAnnotations(obj_type, obj_ids)

    def createImageFromNumpySeq(self, zctPlanes, imageName, sizeZ=1, sizeC=1,
                                sizeT=1, description=None, dataset=None,
                                sourceImageId=None, channelList=None):
        """
        Creates a new multi-dimensional image from the sequence of 2D numpy
        arrays in zctPlanes. zctPlanes should be a generator of numpy 2D
        arrays of shape (sizeY, sizeX) ordered to iterate through T first,
        then C then Z.
        Example usage::

            original = conn.getObject("Image", 1)
            sizeZ = original.getSizeZ()
            sizeC = original.getSizeC()
            sizeT = original.getSizeT()
            clist = range(sizeC)
            zctList = []
            for z in range(sizeZ):
                for c in clist:
                    for t in range(sizeT):
                        zctList.append( (z,c,t) )
            def planeGen():
                planes = original.getPrimaryPixels().getPlanes(zctList)
                for p in planes:
                    # perform some manipulation on each plane
                    yield p
            createImageFromNumpySeq(
                planeGen(), imageName, sizeZ=sizeZ, sizeC=sizeC, sizeT=sizeT,
                sourceImageId=1, channelList=clist)

        :param session:         An OMERO service factory or equivalent
                                with getQueryService() etc.
        :param zctPlanes:       A generator of numpy 2D arrays,
                                corresponding to Z-planes of new image.
        :param imageName:       Name of new image
        :param description:     Description for the new image
        :param dataset:         If specified, put the image in this dataset.
                                omero.model.Dataset object
        :param sourceImageId:   If specified, copy this image with metadata,
                                then add pixel data
        :param channelList:     Copies metadata from these channels in
                                source image (if specified). E.g. [0,2]
        :return: The new OMERO image: omero.model.ImageI
        """
        queryService = self.getQueryService()
        pixelsService = self.getPixelsService()
        # Make sure we don't get an existing rpStore
        rawPixelsStore = self.c.sf.createRawPixelsStore()
        containerService = self.getContainerService()
        updateService = self.getUpdateService()

        import numpy

        def createImage(firstPlane, channelList):
            """ Create our new Image once we have the first plane in hand """
            convertToType = None
            sizeY, sizeX = firstPlane.shape
            if sourceImageId is not None:
                if channelList is None:
                    channelList = list(range(sizeC))
                iId = pixelsService.copyAndResizeImage(
                    sourceImageId, rint(sizeX), rint(sizeY), rint(sizeZ),
                    rint(sizeT), channelList, None, False, self.SERVICE_OPTS)
                # need to ensure that the plane dtype matches the pixels type
                # of our new image
                img = self.getObject("Image", iId.getValue())
                newPtype = img.getPrimaryPixels().getPixelsType().getValue()
                omeroToNumpy = {PixelsTypeint8: 'int8',
                                PixelsTypeuint8: 'uint8',
                                PixelsTypeint16: 'int16',
                                PixelsTypeuint16: 'uint16',
                                PixelsTypeint32: 'int32',
                                PixelsTypeuint32: 'uint32',
                                PixelsTypefloat: 'float32',
                                PixelsTypedouble: 'double'}
                if omeroToNumpy[newPtype] != firstPlane.dtype.name:
                    convertToType = getattr(numpy, omeroToNumpy[newPtype])
                img._obj.setName(rstring(imageName))
                img._obj.setSeries(rint(0))
                updateService.saveObject(img._obj, self.SERVICE_OPTS)
            else:
                # need to map numpy pixel types to omero - don't handle: bool_,
                # character, int_, int64, object_
                pTypes = {'int8': PixelsTypeint8,
                          'int16': PixelsTypeint16,
                          'uint16': PixelsTypeuint16,
                          'int32': PixelsTypeint32,
                          'float_': PixelsTypefloat,
                          'float8': PixelsTypefloat,
                          'float16': PixelsTypefloat,
                          'float32': PixelsTypefloat,
                          'float64': PixelsTypedouble,
                          'complex_': PixelsTypecomplex,
                          'complex64': PixelsTypecomplex}
                dType = firstPlane.dtype.name
                if dType not in pTypes:  # try to look up any not named above
                    pType = dType
                else:
                    pType = pTypes[dType]
                # omero::model::PixelsType
                pixelsType = queryService.findByQuery(
                    "from PixelsType as p where p.value='%s'" % pType, None)
                if pixelsType is None:
                    raise Exception(
                        "Cannot create an image in omero from numpy array "
                        "with dtype: %s" % dType)
                channelList = list(range(sizeC))
                iId = pixelsService.createImage(
                    sizeX, sizeY, sizeZ, sizeT, channelList, pixelsType,
                    imageName, description, self.SERVICE_OPTS)

            imageId = iId.getValue()
            return (containerService.getImages(
                "Image", [imageId], None, self.SERVICE_OPTS)[0], convertToType)

        def uploadPlane(plane, z, c, t, convertToType):
            # if we're given a numpy dtype, need to convert plane to that dtype
            if convertToType is not None:
                p = numpy.zeros(plane.shape, dtype=convertToType)
                p += plane
                plane = p
            byteSwappedPlane = plane.byteswap()
            convertedPlane = byteSwappedPlane.tostring()
            rawPixelsStore.setPlane(convertedPlane, z, c, t, self.SERVICE_OPTS)

        image = None
        dtype = None
        channelsMinMax = []
        exc = None
        try:
            for theZ in range(sizeZ):
                for theC in range(sizeC):
                    for theT in range(sizeT):
                        plane = next(zctPlanes)
                        # use the first plane to create image.
                        if image is None:
                            image, dtype = createImage(plane, channelList)
                            pixelsId = image.getPrimaryPixels(
                                ).getId().getValue()
                            rawPixelsStore.setPixelsId(
                                pixelsId, True, self.SERVICE_OPTS)
                        uploadPlane(plane, theZ, theC, theT, dtype)
                        # init or update min and max for this channel
                        minValue = plane.min()
                        maxValue = plane.max()
                        # first plane of each channel
                        if len(channelsMinMax) < (theC + 1):
                            channelsMinMax.append([minValue, maxValue])
                        else:
                            channelsMinMax[theC][0] = min(
                                channelsMinMax[theC][0], minValue)
                            channelsMinMax[theC][1] = max(
                                channelsMinMax[theC][1], maxValue)
        except Exception as e:
            logger.error(
                "Failed to setPlane() on rawPixelsStore while creating Image",
                exc_info=True)
            exc = e
        try:
            rawPixelsStore.close(self.SERVICE_OPTS)
        except Exception as e:
            logger.error("Failed to close rawPixelsStore", exc_info=True)
            if exc is None:
                exc = e
        if exc is not None:
            raise exc

        # simply completing the generator - to avoid a GeneratorExit error.
        try:
            next(zctPlanes)
        except StopIteration:
            pass

        for theC, mm in enumerate(channelsMinMax):
            pixelsService.setChannelGlobalMinMax(
                pixelsId, theC, float(mm[0]), float(mm[1]), self.SERVICE_OPTS)
            # resetRenderingSettings(
            #     renderingEngine, pixelsId, theC, mm[0], mm[1])

        # put the image in dataset, if specified.
        if dataset:
            link = omero.model.DatasetImageLinkI()
            link.parent = omero.model.DatasetI(dataset.getId(), False)
            link.child = omero.model.ImageI(image.id.val, False)
            updateService.saveObject(link, self.SERVICE_OPTS)

        return ImageWrapper(self, image)

    def applySettingsToSet(self, fromid, to_type, toids):
        """
        Applies the rendering settings from one image to others.
        Returns a dict of success { True:[ids], False:[ids] }

        :param fromid:      ID of Image to copy settings from.
        :param toids:       List of Image IDs to apply setting to.
        :param to_type:     toids refers to Images by default, but can refer to
                                Project, Dataset, Image, Plate, Screen, Pixels
        """
        json_data = False
        fromimg = self.getObject("Image", fromid)
        frompid = fromimg.getPixelsId()
        if to_type is None:
            to_type = "Image"
        if to_type.lower() == "acquisition":
            plateIds = []
            for pa in self.getObjects("PlateAcquisition", toids):
                plateIds.append(pa.listParents()[0].id)
            to_type = "Plate"
            toids = plateIds
        to_type = to_type.title()
        if fromimg.canAnnotate():
            ctx = self.SERVICE_OPTS.copy()
            ctx.setOmeroGroup(fromimg.getDetails().getGroup().getId())
            rsettings = self.getRenderingSettingsService()
            json_data = rsettings.applySettingsToSet(
                frompid, to_type, list(toids),  ctx)
            if fromid in json_data[True]:
                del json_data[True][json_data[True].index(fromid)]
        return json_data

    def setChannelNames(self, data_type, ids, nameDict, channelCount=None):
        """
        Sets and saves new names for channels of specified Images.
        If an image has fewer channels than the max channel index in nameDict,
        then the channel names will not be set for that image.

        :param data_type:   'Image', 'Dataset', 'Plate'
        :param ids:         Image, Dataset or Plate IDs
        :param nameDict:    A dict of index:'name' ** 1-based **
                            E.g. {1:"DAPI", 2:"GFP"}
        :param channelCount:    If specified, only rename images
                                with this number of channels
        :return:            {'imageCount':totalImages,
                             'updateCount':updateCount}
        """

        if data_type == "Image":
            imageIds = [int(i) for i in ids]
        elif data_type == "Dataset":
            images = self.getContainerService().getImages(
                "Dataset", ids, None, self.SERVICE_OPTS)
            imageIds = [i.getId().getValue() for i in images]
        elif data_type == "Plate":
            imageIds = []
            plates = self.getObjects("Plate", ids)
            for p in plates:
                for well in p._listChildren():
                    for ws in well.copyWellSamples():
                        imageIds.append(ws.image.id.val)
        else:
            raise AttributeError(
                "setChannelNames() supports data_types 'Image', 'Dataset', "
                "'Plate' only, not '%s'" % data_type)

        queryService = self.getQueryService()
        params = omero.sys.Parameters()
        params.map = {'ids': omero.rtypes.wrap(imageIds)}

        # load Pixels, Channels, Logical Channels and Images
        query = ("select p from Pixels p left outer "
                 "join fetch p.channels as c "
                 "join fetch c.logicalChannel as lc "
                 "join fetch p.image as i where i.id in (:ids)")
        pix = queryService.findAllByQuery(query, params, self.SERVICE_OPTS)

        maxIdx = max(nameDict.keys())
        # NB: we may have duplicate Logical Channels (Many Iamges in Plate
        # linked to same LogicalChannel)
        toSave = set()
        updateCount = 0
        ctx = self.SERVICE_OPTS.copy()
        for p in pix:
            sizeC = p.getSizeC().getValue()
            if sizeC < maxIdx:
                continue
            # Filter by channel count
            if channelCount is not None and channelCount != sizeC:
                continue
            updateCount += 1
            group_id = p.details.group.id.val
            ctx.setOmeroGroup(group_id)
            for i, c in enumerate(p.iterateChannels()):
                if i+1 not in nameDict:
                    continue
                lc = c.logicalChannel
                lc.setName(rstring(nameDict[i+1]))
                toSave.add(lc)

        toSave = list(toSave)
        self.getUpdateService().saveCollection(toSave, ctx)
        return {'imageCount': len(imageIds), 'updateCount': updateCount}

    def createOriginalFileFromFileObj(self, fo, path, name, fileSize,
                                      mimetype=None, ns=None):
        """
        Creates a :class:`OriginalFileWrapper` from a local file.
        File is uploaded to create an omero.model.OriginalFileI.
        Returns a new :class:`OriginalFileWrapper`

        :param conn:                    Blitz connection
        :param fo:                      The file object
        :param path:                    The file path
        :param name:                    The file name
        :param fileSize:                The file size
        :param mimetype:                The mimetype of the file. String.
                                        E.g. 'text/plain'
        :param ns:                      Deprecated in 5.4.0. This is ignored
        :return:                        New :class:`OriginalFileWrapper`
        """
        if ns is not None:
            warnings.warn(
                "Deprecated in 5.4.0. The ns parameter was added in error"
                " and has always been ignored",
                DeprecationWarning)

        updateService = self.getUpdateService()
        # create original file, set name, path, mimetype
        originalFile = omero.model.OriginalFileI()
        originalFile.setName(rstring(name))
        originalFile.setPath(rstring(path))
        if mimetype:
            originalFile.mimetype = rstring(mimetype)
        originalFile.setSize(rlong(fileSize))
        # set sha1
        try:
            import hashlib
            hash_sha1 = hashlib.sha1
        except:
            import sha
            hash_sha1 = sha.new
        fo.seek(0)
        h = hash_sha1()
        h.update(fo.read())
        shaHast = h.hexdigest()
        originalFile.setHash(rstring(shaHast))

        chk = omero.model.ChecksumAlgorithmI()
        chk.setValue(rstring(omero.model.enums.ChecksumAlgorithmSHA1160))
        originalFile.setHasher(chk)

        originalFile = updateService.saveAndReturnObject(
            originalFile, self.SERVICE_OPTS)

        # upload file
        fo.seek(0)
        rawFileStore = self.createRawFileStore()
        try:
            rawFileStore.setFileId(
                originalFile.getId().getValue(), self.SERVICE_OPTS)
            buf = 10000
            for pos in range(0, int(fileSize), buf):
                block = None
                if fileSize-pos < buf:
                    blockSize = fileSize-pos
                else:
                    blockSize = buf
                fo.seek(pos)
                block = fo.read(blockSize)
                rawFileStore.write(block, pos, blockSize, self.SERVICE_OPTS)
            originalFile = rawFileStore.save(self.SERVICE_OPTS)
        finally:
            rawFileStore.close()
        return OriginalFileWrapper(self, originalFile)

    def createOriginalFileFromLocalFile(self, localPath,
                                        origFilePathAndName=None,
                                        mimetype=None, ns=None):
        """
        Creates a :class:`OriginalFileWrapper` from a local file.
        File is uploaded to create an omero.model.OriginalFileI.
        Returns a new :class:`OriginalFileWrapper`

        :param conn:                    Blitz connection
        :param localPath:               Location to find the local file
                                        to upload
        :param origFilePathAndName:     Provides the 'path' and 'name' of the
                                        OriginalFile. If None, use localPath
        :param mimetype:                The mimetype of the file. String.
                                        E.g. 'text/plain'
        :param ns:                      Deprecated in 5.4.0. This is ignored
        :return:                        New :class:`OriginalFileWrapper`
        """
        if ns is not None:
            warnings.warn(
                "Deprecated in 5.4.0. The ns parameter was added in error"
                " and has always been ignored",
                DeprecationWarning)
        if origFilePathAndName is None:
            origFilePathAndName = localPath
        path, name = os.path.split(origFilePathAndName)
        fileSize = os.path.getsize(localPath)
        with open(localPath, 'rb') as fileHandle:
            return self.createOriginalFileFromFileObj(fileHandle, path, name,
                                                      fileSize, mimetype)

    def createFileAnnfromLocalFile(self, localPath, origFilePathAndName=None,
                                   mimetype=None, ns=None, desc=None):
        """
        Class method to create a :class:`FileAnnotationWrapper` from a local
        file. File is uploaded to create an omero.model.OriginalFileI
        referenced from this File Annotation. Returns a new
        :class:`FileAnnotationWrapper`

        :param conn:                    Blitz connection
        :param localPath:               Location to find the local file
                                        to upload
        :param origFilePathAndName:     Provides the 'path' and 'name' of the
                                        OriginalFile. If None, use localPath
        :param mimetype:                The mimetype of the file. String.
                                        E.g. 'text/plain'
        :param ns:                      The namespace of the file.
        :param desc:                    A description for the file annotation.
        :return:                        New :class:`FileAnnotationWrapper`
        """
        updateService = self.getUpdateService()

        # create and upload original file
        originalFile = self.createOriginalFileFromLocalFile(
            localPath, origFilePathAndName, mimetype)

        # create FileAnnotation, set ns & description and return wrapped obj
        fa = omero.model.FileAnnotationI()
        fa.setFile(originalFile._obj)
        if desc:
            fa.setDescription(rstring(desc))
        if ns:
            fa.setNs(rstring(ns))
        fa = updateService.saveAndReturnObject(fa, self.SERVICE_OPTS)
        return FileAnnotationWrapper(self, fa)

    def getObjectsByAnnotations(self, obj_type, annids):
        """
        Retrieve objects linked to the given annotation IDs
        controlled by the security system.

        :param annids:      Annotation IDs
        :type annids:       :class:`Long`
        :return:            Generator yielding Objects
        :rtype:             :class:`BlitzObjectWrapper` generator
        """

        wrapper = KNOWN_WRAPPERS.get(obj_type.lower(), None)
        if not wrapper:
            raise AttributeError("Don't know how to handle '%s'" % obj_type)

        sql = "select ob from %s ob " \
              "left outer join fetch ob.annotationLinks obal " \
              "left outer join fetch obal.child ann " \
              "where ann.id in (:oids)" % wrapper().OMERO_CLASS

        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["oids"] = rlist([rlong(o) for o in set(annids)])
        for e in q.findAllByQuery(sql, p, self.SERVICE_OPTS):
            yield wrapper(self, e)

    ################
    # Enumerations #

    def getEnumerationEntries(self, klass):
        """
        Get all enumerations by class

        :param klass:   Class
        :type klass:    Class or string
        :return:        Generator of Enumerations
        :rtype:         :class:`EnumerationWrapper` generator
        """

        types = self.getTypesService()
        for e in types.allEnumerations(str(klass)):
            yield EnumerationWrapper(self, e)

    def getEnumeration(self, klass, string):
        """
        Get enumeration by class and value

        :param klass:   Class
        :type klass:    Class or string
        :param string:  Enum value
        :type string:   String
        :return:        Enumeration or None
        :rtype:         :class:`EnumerationWrapper`
        """

        types = self.getTypesService()
        obj = types.getEnumeration(str(klass), str(string))
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None

    def getEnumerationById(self, klass, eid):
        """
        Get enumeration by class and ID

        :param klass:   Class
        :type klass:    Class or string
        :param eid:     Enum ID
        :type eid:      Long
        :return:        Enumeration or None
        :rtype:         :class:`EnumerationWrapper`
        """

        query_serv = self.getQueryService()
        obj = query_serv.find(klass, int(eid), self.SERVICE_OPTS)
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None

    def getOriginalEnumerations(self):
        """
        Gets original enumerations. Returns a dictionary of enumeration class:
        list of Enumerations

        :return:    Original enums
        :rtype:     Dict of <string: :class:`EnumerationWrapper` list >
        """

        types = self.getTypesService()
        rv = dict()
        for e in types.getOriginalEnumerations():
            if rv.get(e.__class__.__name__) is None:
                rv[e.__class__.__name__] = list()
            rv[e.__class__.__name__].append(EnumerationWrapper(self, e))
        return rv

    def getEnumerations(self):
        """
        Gets list of enumeration types

        :return:    List of enum types
        :rtype:     List of Strings
        """

        types = self.getTypesService()
        return types.getEnumerationTypes()

    def getEnumerationsWithEntries(self):
        """
        Get enumeration types, with lists of Enum entries

        :return:    Dictionary of type: entries
        :rtype:     Dict of <string: :class:`EnumerationWrapper` list >
        """

        types = self.getTypesService()
        rv = dict()
        for key, value in list(types.getEnumerationsWithEntries().items()):
            r = list()
            for e in value:
                r.append(EnumerationWrapper(self, e))
            rv[key+"I"] = r
        return rv

    def deleteEnumeration(self, obj):
        """
        Deletes an enumeration object

        :param obj:     Enumeration object
        :type obj:      omero.model.IObject
        """

        types = self.getTypesService()
        types.deleteEnumeration(obj)

    def createEnumeration(self, obj):
        """
        Create an enumeration with given object

        :param obj:     Object
        :type obj:      omero.model.IObject
        """

        types = self.getTypesService()
        types.createEnumeration(obj)

    def resetEnumerations(self, klass):
        """
        Resets the enumerations by type

        :param klass:   Type of enum to reset
        :type klass:    String
        """

        types = self.getTypesService()
        types.resetEnumerations(klass)

    def updateEnumerations(self, new_entries):
        """
        Updates enumerations with new entries

        :param new_entries:   List of objects
        :type new_entries:    List of omero.model.IObject
        """

        types = self.getTypesService()
        types.updateEnumerations(new_entries)

    ###################
    # Delete          #

    def deleteObjectDirect(self, obj):
        """
        Directly Delete object (removes row from database).
        This may fail with various constraint violations if the object is
        linked to others in the database

        :param obj:     Object to delete
        :type obj:      IObject

        ** Deprecated ** Use :meth:`deleteObject` or :meth:`deleteObjects`.
        """
        warnings.warn(
            "Deprecated. Use deleteObject() or deleteObjects()",
            DeprecationWarning)

        type = obj.__class__.__name__.rstrip('I')
        delete = Delete2(targetObjects={type: [obj.getId().val]})
        self.c.submit(delete, self.SERVICE_OPTS)

    def deleteObject(self, obj):
        """
        Delete a single object.

        :param obj:     Object to delete
        :type obj:      IObject
        """

        objType = obj.__class__.__name__.rstrip('I')
        self.deleteObjects(objType, [obj.id.val], wait=True)

    def deleteObjects(self, graph_spec, obj_ids, deleteAnns=False,
                      deleteChildren=False, dryRun=False, wait=False):
        """
        Generic method for deleting using the delete queue. Options allow to
        delete 'independent' Annotations (Tag, Term, File) and to delete
        child objects.

        :param graph_spec:      String to indicate the object type or graph
                                specification. Examples include:

                                * 'Project'
                                * 'Dataset'
                                * 'Image'
                                * 'Screen'
                                * 'Plate'
                                * 'Well'
                                * 'Annotation'
                                * 'OriginalFile'
                                * 'Roi'
                                * 'Image/Pixels/Channel'

                                As of OMERO 4.4.0 the correct case is now
                                explicitly required, the use of 'project'
                                or 'dataset' is no longer supported.
        :param obj_ids:         List of IDs for the objects to delete
        :param deleteAnns:      If true, delete linked Tag, Term and File
                                annotations
        :param deleteChildren:  If true, delete children. E.g. Delete Project
                                AND it's Datasets & Images.
        :return:                Delete handle
        :rtype:                 :class:`omero.api.delete.DeleteHandle`
        """

        if '+' in graph_spec:
            raise AttributeError(
                "Graph specs containing '+'' no longer supported: '%s'"
                % graph_spec)
        if not isinstance(obj_ids, list) or len(obj_ids) < 1:
            raise AttributeError('Must be a list of object IDs')

        graph = graph_spec.lstrip('/').split('/')
        obj_ids = list(map(int, obj_ids))
        delete = Delete2(targetObjects={graph[0]: obj_ids}, dryRun=dryRun)

        exc = list()
        if not deleteAnns and graph[0] not in ["Annotation",
                                               "TagAnnotation"]:
            exc.extend(
                ["TagAnnotation", "TermAnnotation", "FileAnnotation"])

        childTypes = {'Project': ['Dataset', 'Image'],
                      'Dataset': ['Image'],
                      'Image': [],
                      'Screen': ['Plate'],
                      'Plate': ['Image'],
                      'Well': [],
                      'Annotation': []}

        if not deleteChildren:
            try:
                for c in childTypes[graph[0]]:
                    exc.append(c)
            except KeyError:
                pass

        if len(exc) > 1:
            delete.childOptions = [ChildOption(excludeType=exc)]

        if len(graph) > 1:
            skiphead = SkipHead()
            skiphead.request = delete
            skiphead.targetObjects = delete.targetObjects
            skiphead.childOptions = delete.childOptions
            skiphead.startFrom = [graph[-1]]
            skiphead.dryRun = dryRun
            delete = skiphead

        logger.debug('Deleting %s [%s]. Options: %s' %
                     (graph_spec, str(obj_ids), exc))

        logger.debug('Delete2: \n%s' % str(delete))

        handle = self.c.sf.submit(delete, self.SERVICE_OPTS)
        if wait:
            try:
                self._waitOnCmd(handle)
            finally:
                handle.close()

        return handle

    def _waitOnCmd(self, handle, loops=10, ms=500,
                   failonerror=True,
                   failontimeout=False,
                   closehandle=False):

        return self.c.waitOnCmd(handle, loops=loops, ms=ms,
                                failonerror=failonerror,
                                failontimeout=failontimeout,
                                closehandle=closehandle)

    def chmodGroup(self, group_Id, permissions):
        """
        Change the permissions of a particular Group.
        Returns the proxy 'prx' handle that can be processed like this:
        callback = CmdCallbackI(self.gateway.c, prx)
        callback.loop(20, 500)
        rsp = prx.getResponse()
        """
        chmod = omero.cmd.Chmod2(
            targetObjects={'ExperimenterGroup': [group_Id]},
            permissions=permissions)
        prx = self.c.sf.submit(chmod)
        return prx

    def chgrpObjects(self, graph_spec, obj_ids, group_id, container_id=None):
        """
        Change the Group for a specified objects using queue.

        :param graph_spec:      String to indicate the object type or graph
                                specification. Examples include:

                                * 'Image'
                                * 'Project'   # will move contents too.
                                * NB: Also supports '/Image' etc for backwards
                                  compatibility.
        :param obj_ids:         IDs for the objects to move.
        :param group_id:        The group to move the data to.
        """

        if '+' in graph_spec:
            raise AttributeError(
                "Graph specs containing '+'' no longer supported: '%s'"
                % graph_spec)
        if not isinstance(obj_ids, list) or len(obj_ids) < 1:
            raise AttributeError('Must be a list of object IDs')

        graph = graph_spec.lstrip('/').split('/')
        obj_ids = list(map(int, obj_ids))
        chgrp = Chgrp2(targetObjects={graph[0]: obj_ids}, groupId=group_id)

        if len(graph) > 1:
            skiphead = SkipHead()
            skiphead.request = chgrp
            skiphead.targetObjects = chgrp.targetObjects
            skiphead.startFrom = [graph[-1]]
            chgrp = skiphead

        requests = [chgrp]

        # (link, child, parent)
        parentLinkClasses = {
            "Image": (omero.model.DatasetImageLinkI,
                      omero.model.ImageI,
                      omero.model.DatasetI),
            "Dataset": (omero.model.ProjectDatasetLinkI,
                        omero.model.DatasetI,
                        omero.model.ProjectI),
            "Plate": (omero.model.ScreenPlateLinkI,
                      omero.model.PlateI,
                      omero.model.ScreenI)}
        da = DoAll()
        saves = []

        ownerId = self.SERVICE_OPTS.getOmeroUser() or self.getUserId()
        for obj_id in obj_ids:
            obj_id = int(obj_id)
            if container_id is not None and graph_spec in parentLinkClasses:
                # get link class for graph_spec objects
                link_klass = parentLinkClasses[graph_spec][0]
                link = link_klass()
                link.child = parentLinkClasses[graph_spec][1](obj_id, False)
                link.parent = parentLinkClasses[
                    graph_spec][2](container_id, False)
                link.details.owner = omero.model.ExperimenterI(ownerId, False)
                save = Save()
                save.obj = link
                saves.append(save)

        requests.extend(saves)
        da.requests = requests

        logger.debug('DoAll Chgrp2: type: %s, ids: %s, grp: %s' %
                     (graph_spec, obj_ids, group_id))

        logger.debug('Chgrp2: \n%s' % str(da))

        ctx = self.SERVICE_OPTS.copy()
        # NB: For Save to work, we need to be in target group
        ctx.setOmeroGroup(group_id)
        prx = self.c.sf.submit(da, ctx)
        return prx

    ###################
    # Searching stuff #

    def searchObjects(self, obj_types, text, created=None, fields=(),
                      batchSize=1000, page=0, searchGroup=None, ownedBy=None,
                      useAcquisitionDate=False, rawQuery=True):
        """
        Search objects of type "Project", "Dataset", "Image", "Screen", "Plate"
        Returns a list of results

        :param obj_types:   E.g. ["Dataset", "Image"]
        :param text:        The text to search for
        :param created:     :class:`omero.rtime` list or tuple (start, stop)
        :param useAcquisitionDate: if True, then use Image.acquisitionDate
                                   rather than import date for queries.
        :param rawQuery     If True, text is passed directly to byFullText()
                            without processing. fields is ignored.
        :return:            List of Object wrappers. E.g. :class:`ImageWrapper`
        """
        if not text:
            return []
        if isinstance(text, UnicodeType):
            text = text.encode('utf8')
        if obj_types is None:
            types = (ProjectWrapper, DatasetWrapper, ImageWrapper)
        else:
            def getWrapper(obj_type):
                objs = ["project", "dataset", "image", "screen",
                        "plateacquisition", "plate", "well"]
                if obj_type.lower() not in objs:
                    raise AttributeError(
                        "%s not recognised. Can only search for 'Project',"
                        "'Dataset', 'Image', 'Screen', 'Plate', 'Well'"
                        % obj_type)
                return KNOWN_WRAPPERS.get(obj_type.lower(), None)
            types = [getWrapper(o) for o in obj_types]
        search = self.createSearchService()

        ctx = self.SERVICE_OPTS.copy()
        if searchGroup is not None:
            ctx.setOmeroGroup(searchGroup)

        search.setBatchSize(batchSize, ctx)
        if ownedBy is not None:
            ownedBy = int(ownedBy)
            if ownedBy >= 0:
                details = omero.model.DetailsI()
                details.setOwner(omero.model.ExperimenterI(ownedBy, False))
                search.onlyOwnedBy(details, ctx)

        # Matching OMEROGateway.search()
        search.setAllowLeadingWildcard(True)
        search.setCaseSensitive(False)

        def parse_time(c, i):
            try:
                t = c[i]
                t = unwrap(t)
                if t is not None:
                    t = time.localtime(old_div(t, 1000))
                    t = time.strftime("%Y%m%d", t)
                    return t
            except:
                pass
            return None

        d_from = parse_time(created, 0)
        d_to = parse_time(created, 1)
        d_type = (useAcquisitionDate and
                  "acquisitionDate" or
                  "details.creationEvent.time")

        try:
            rv = []
            for t in types:
                def actualSearch():
                    search.onlyType(t().OMERO_CLASS, ctx)
                    if rawQuery:
                        if created is not None and len(created) > 1:
                            search.onlyCreatedBetween(created[0], created[1])
                        search.byFullText(text, ctx)
                    else:
                        search.byLuceneQueryBuilder(
                            ",".join(fields),
                            d_from, d_to, d_type,
                            text, ctx)

                timeit(actualSearch)()
                # get results

                def searchProcessing():
                    return search.results(ctx)
                p = 0
                # we do pagination by loading until the required page
                while search.hasNext(ctx):
                    results = timeit(searchProcessing)()
                    if p == page:
                        rv.extend([t(self, x) for x in results])
                        break
                    p += 1

        finally:
            search.close()
        return rv

    def getThumbnailSet(self, image_ids, max_size=64):
        """
        Retrieves a number of thumbnails for image sets. If the Thumbnails
        exist in the on-disk cache they will be returned directly,
        otherwise they will be created, for more details
        see ome.api.ThumbnailStore.getThumbnailByLongestSideSet

        :param image_ids:   A list of image ids
        :param max_size:    The longest side of the image will be used
                            to calculate the size for the smaller side
                            in order to keep the aspect ratio of
                            the original image.
        :return:            dictionary of strings holding a rendered JPEG
                            of the thumbnails.
        """
        tb = None
        _resp = dict()
        try:
            ctx = self.SERVICE_OPTS.copy()
            if ctx.getOmeroGroup() is None:
                ctx.setOmeroGroup(-1)
            tb = self.createThumbnailStore()
            p = omero.sys.ParametersI().addIds(image_ids)
            sql = """select new map(
                        i.id as im_id, p.id as pix_id
                     )
                     from Pixels as p join p.image as i
                     where i.id in (:ids) """

            img_pixel_ids = self.getQueryService().projection(
                sql, p, ctx)
            _temp = dict()
            for e in img_pixel_ids:
                e = unwrap(e)
                _temp[e[0]['pix_id']] = e[0]['im_id']

            thumbs_map = tb.getThumbnailByLongestSideSet(
                rint(max_size), list(_temp), ctx)
            for (pix, thumb) in list(thumbs_map.items()):
                _resp[_temp[pix]] = thumb
        except Exception:
            logger.error(traceback.format_exc())
        finally:  # pragma: no cover
            if tb is not None:
                tb.close()
        return _resp


class OmeroGatewaySafeCallWrapper(object):  # pragma: no cover
    """
    Function or method wrapper that handles certain types of server side
    exceptions and debugging of errors.
    """

    def __init__(self, proxyObjectWrapper, attr, f):
        """
        Initialises the function call wrapper.

        :param attr:    Function name
        :type attr:     String
        :param f:       Function to wrap
        :type f:        Function
        """
        self.proxyObjectWrapper = proxyObjectWrapper
        self.attr = attr
        self.f = f
        try:
            self.__f__name = f.__self__.ice_getIdentity().name
        except:
            self.__f__name = "unknown"

    def debug(self, exc_class, args, kwargs):
        logger.warn("%s on %s to <%s> %s(%r, %r)",
                    exc_class, self.__class__, self.__f__name, self.attr,
                    args, kwargs, exc_info=True)

    def handle_exception(self, e, *args, **kwargs):
        r"""
        Exception handler that is expected to be overridden by sub-classes.
        The expected behaviour is either to handle a type of exception and
        return the server side result or to raise the already thrown
        exception. The calling context is an except block and the original
        \*args and \**kwargs from the wrapped function or method are provided
        to allow re-execution of the original.

        :param e:    The exception that has already been raised.
        :type e:     Exception
        """
        raise

    def __call__(self, *args, **kwargs):
        try:
            return self.f(*args, **kwargs)
        except Exception as e:
            self.debug(e.__class__.__name__, args, kwargs)
            return self.handle_exception(e, *args, **kwargs)

# Extension point for API users who want to customise the semantics of
# safe call wrap. (See #6365)
#
#  Since: OMERO Beta-4.3.2 (Tue  2 Aug 2011 09:59:47 BST)
SafeCallWrapper = OmeroGatewaySafeCallWrapper

BlitzGateway = _BlitzGateway


def splitHTMLColor(color):
    """
    splits an hex stream of characters into an array of bytes
    in format (R,G,B,A).
    - abc      -> (0xAA, 0xBB, 0xCC, 0xFF)
    - abcd     -> (0xAA, 0xBB, 0xCC, 0xDD)
    - abbccd   -> (0xAB, 0xBC, 0xCD, 0xFF)
    - abbccdde -> (0xAB, 0xBC, 0xCD, 0xDE)

    :param color:   Characters to split.
    :return:        rgba
    :rtype:         list of Ints
    """
    try:
        out = []
        if len(color) in (3, 4):
            c = color
            color = ''
            for e in c:
                color += e + e
        if len(color) == 6:
            color += 'FF'
        if len(color) == 8:
            for i in range(0, 8, 2):
                out.append(int(color[i:i+2], 16))
            return out
    except:
        pass
    return None


class ProxyObjectWrapper (object):
    """
    Wrapper for services. E.g. Admin Service, Delete Service etc.
    Maintains reference to connection.
    Handles creation of service when requested.
    """

    def __init__(self, conn, func_str, cast_to=None, service_name=None):
        """
        Initialisation of proxy object wrapper.

        :param conn:         The :class:`BlitzGateway` connection
        :type conn:          :class:`BlitzGateway`
        :param func_str:     The name of the service creation method.
                             E.g 'getAdminService'
        :type func_str:      String
        :param cast_to:      the checkedCast function to call with service name
                             (only if func_str is None)
        :type cast_to:       function
        :param service_name: Service name to use with cast_to
                             (only if func_str is None)

        """
        self._obj = None
        self._func_str = func_str
        self._cast_to = cast_to
        self._service_name = service_name
        self._resyncConn(conn)
        self._tainted = False

    def clone(self):
        """
        Creates and returns a new :class:`ProxyObjectWrapper` with the same
        connection and service creation method name as this one.

        :return:    Cloned service wrapper
        :rtype:     :class:`ProxyObjectWrapper`
        """

        return ProxyObjectWrapper(
            self._conn, self._func_str, self._cast_to, self._service_name)

    def _connect(self, forcejoin=False):  # pragma: no cover
        """
        Returns True if connected.
        If connection OK, wrapped service is also created.

        :param forcejoin: if True forces the connection to only succeed if we
                          can rejoin the current sessionid
        :type forcejoin:  Boolean

        :return:    True if connection OK
        :rtype:     Boolean
        """
        logger.debug("proxy_connect: a")
        if forcejoin:
            sUuid = self._conn._sessionUuid
        else:
            sUuid = None
        if not self._conn.connect(sUuid=sUuid):
            logger.debug('connect failed')
            logger.debug('/n'.join(traceback.format_stack()))
            return False
        logger.debug("proxy_connect: b")
        self._resyncConn(self._conn)
        logger.debug("proxy_connect: c")
        self._obj = self._create_func()
        logger.debug("proxy_connect: d")
        return True

    def taint(self):
        """ Sets the tainted flag to True """
        self._tainted = True

    def untaint(self):
        """ Sets the tainted flag to False """
        self._tainted = False

    def close(self, *args, **kwargs):
        """
        Closes the underlying service, so next call to the proxy will create
        a new instance of it.
        """

        if self._obj and isinstance(
                self._obj, omero.api.StatefulServiceInterfacePrx):
            self._conn._unregister_service(str(self._obj))
            self._obj.close(*args, **kwargs)
        self._obj = None

    def _resyncConn(self, conn):
        """
        Reset refs to connection and session factory. Resets session creation
        function. Attempts to reload the wrapped service - if already created
        (doesn't create service)

        :param conn:    Connection
        :type conn:     :class:`BlitzGateway`
        """

        self._conn = conn

        def cf():
            if self._func_str is None:
                return self._cast_to(
                    self._conn.c.sf.getByName(self._service_name)
                )
            else:
                obj = getattr(self._conn.c.sf, self._func_str)()
                if isinstance(obj, omero.api.StatefulServiceInterfacePrx):
                    conn._register_service(str(obj), traceback.extract_stack())
                return obj
        self._create_func = cf
        if self._obj is not None:
            try:
                logger.debug("## - refreshing %s" %
                             (self._func_str or self._service_name))
                obj = conn.c.ic.stringToProxy(str(self._obj))
                self._obj = self._obj.checkedCast(obj)
            except Ice.ObjectNotExistException:
                self._obj = None

    def _getObj(self):
        """
        Returns the wrapped service. If it is None, service is created.

        :return:    The wrapped service
        :rtype:     omero.api.ServiceInterface subclass
        """

        if not self._obj:
            try:
                self._obj = self._create_func()
            except Ice.ConnectionLostException:
                logger.debug('... lost, reconnecting (_getObj)')
                self._connect()
                # self._obj = self._create_func()
        else:
            self._ping()
        return self._obj

    def _ping(self):  # pragma: no cover
        """
        For some reason, it seems that keepAlive doesn't, so every so often I
        need to recreate the objects. Calls serviceFactory.keepAlive(service).
        If this returns false, attempt to create service.

        :return:    True if no exception thrown
        :rtype:     Boolean
        """

        try:
            if not self._conn.c.sf.keepAlive(self._obj):
                logger.debug("... died, recreating ...")
                self._obj = self._create_func()
        except Ice.ObjectNotExistException:
            # The connection is there, but it has been reset, because the proxy
            # no longer exists...
            logger.debug("... reset, reconnecting")
            self._connect()
            return False
        except Ice.ConnectionLostException:
            # The connection was lost. This shouldn't happen, as we keep
            # pinging it, but does so...
            logger.debug(traceback.format_stack())
            logger.debug("... lost, reconnecting (_ping)")
            self._conn._connected = False
            self._connect()
            return False
        except Ice.ConnectionRefusedException:
            # The connection was refused. We lost contact with
            # glacier2router...
            logger.debug(traceback.format_stack())
            logger.debug("... refused, reconnecting")
            self._connect()
            return False
        except omero.RemovedSessionException:
            # Session died on us
            logger.debug(traceback.format_stack())
            logger.debug("... session has left the building, reconnecting")
            self._connect()
            return False
        except Ice.UnknownException:
            # Probably a wrapped RemovedSession
            logger.debug(traceback.format_stack())
            logger.debug("... ice says something bad happened, reconnecting")
            self._connect()
            return False
        return True

    def __getattr__(self, attr):
        """
        Returns named attribute of the wrapped service.
        If attribute is a method, the method is wrapped to handle exceptions,
        connection etc.

        :param attr:    Attribute name
        :type attr:     String
        :return:        Attribute or wrapped method
        """
        # safe call wrapper
        obj = self._obj or self._getObj()
        rv = getattr(obj, attr)
        if callable(rv):
            rv = SafeCallWrapper(self, attr, rv)
        # self._conn.updateTimeout()
        return rv


from omero_model_FileAnnotationI import FileAnnotationI


class FileAnnotationWrapper (AnnotationWrapper, OmeroRestrictionWrapper):
    """
    omero_model_FileAnnotationI class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = FileAnnotationI

    def __init__(self, *args, **kwargs):
        super(FileAnnotationWrapper, self).__init__(*args, **kwargs)
        self._file = None

    _attrs = ('file|OriginalFileWrapper',)

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("FileAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from FileAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent join fetch obj.file")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """ Not implemented """
        pass

    def setValue(self, val):
        """ Not implemented """
        pass

    def getFile(self):
        """
        Returns an OriginalFileWrapper for the file.
        Wrapper object will load the file if it isn't already loaded.
        File is cached to prevent repeated loading of the file.
        """
        if self._file is None:
            self._file = OriginalFileWrapper(self._conn, self._obj.file)
        return self._file

    def setFile(self, originalfile):
        """
        """
        self._obj.file = omero.model.OriginalFileI(originalfile.getId(), False)

    def setDescription(self, val):
        """
        """
        self._obj.description = omero_type(val)

    def isOriginalMetadata(self):
        """
        Checks if this file annotation is an 'original_metadata' file

        :return:    True if namespace and file name follow metadata convention
        :rtype:     Boolean
        """

        try:
            if (self._obj.ns is not None and
                    self._obj.ns.val ==
                    omero.constants.namespaces.NSCOMPANIONFILE and
                    self.getFile().getName() ==
                    omero.constants.annotation.file.ORIGINALMETADATA):
                return True
        except:
            logger.info(traceback.format_exc())
        return False

    def getFileSize(self):
        """
        Looks up the size of the file in bytes

        :return:    File size (bytes)
        :rtype:     Long
        """
        return self.getFile().size

    def getFileName(self):
        """
        Gets the file name

        :return:    File name
        :rtype:     String
        """
        f = self.getFile()
        if f is None or f._obj is None:
            return None
        return f.getName()

    def getFileInChunks(self, buf=2621440):
        """
        Returns a generator yielding chunks of the file data.

        :return:    Data from file in chunks
        :rtype:     Generator
        """

        return self.getFile().getFileInChunks(buf=buf)

AnnotationWrapper._register(FileAnnotationWrapper)


from ._files import OriginalFileWrapper

from ._annotations import BooleanAnnotationWrapper
from ._annotations import CommentAnnotationWrapper
from ._annotations import DoubleAnnotationWrapper
from ._annotations import LongAnnotationWrapper
from ._annotations import MapAnnotationWrapper
from ._annotations import TagAnnotationWrapper
from ._annotations import TermAnnotationWrapper
from ._annotations import TimestampAnnotationWrapper
# TODO: Delete class?
from ._annotations import XmlAnnotationWrapper #noqa

class _RoiWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterI class wrapper extends BlitzObjectWrapper.
    """
    OMERO_CLASS = 'Roi'
    # TODO: test listChildren() to use ShapeWrapper? or remove?
    CHILD_WRAPPER_CLASS = 'ShapeWrapper'

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle loading of Shapes.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'load_shapes': boolean.
                        'image': <image_id> to filter by Image

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _RoiWrapper, cls)._getQueryString(opts)
        if opts is None:
            opts = {}
        if opts.get('load_shapes'):
            query += ' left outer join fetch obj.shapes'
        if 'image' in opts:
            clauses.append('obj.image.id = :image_id')
            params.add('image_id', rlong(opts['image']))
        return (query, clauses, params)

    def getImage(self):
        """
        Returns the Image for this ROI.

        :return:    The Image
        :rtype:     :class:`ImageWrapper`
        """

        if self._obj.image is not None:
            return ImageWrapper(self._conn, self._obj.image)

RoiWrapper = _RoiWrapper


class _ShapeWrapper (BlitzObjectWrapper):
    """
    omero_model_ShapeI class wrapper extends BlitzObjectWrapper.
    """
    OMERO_CLASS = 'Shape'

ShapeWrapper = _ShapeWrapper


class _ExperimenterWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Experimenter'
    LINK_CLASS = "GroupExperimenterMap"
    CHILD_WRAPPER_CLASS = None
    PARENT_WRAPPER_CLASS = 'ExperimenterGroupWrapper'

    def simpleMarshal(self, xtra=None, parents=False):
        rv = super(_ExperimenterWrapper, self).simpleMarshal(
            xtra=xtra, parents=parents)
        isAdmin = (len([x for x in self._conn.getAdminService().containedGroups(self.getId()) if x.name.val == 'system']) == 1)
        rv.update(
            {'firstName': self.firstName,
             'middleName': self.middleName,
             'lastName': self.lastName,
             'email': self.email,
             'isAdmin': isAdmin, })
        return rv

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Returns string for building queries, loading Experimenters only.

        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select distinct obj from Experimenter as obj "
                 "left outer join fetch obj.groupExperimenterMap as map "
                 "left outer join fetch map.parent g")
        return query, [], omero.sys.ParametersI()

    def getRawPreferences(self):
        """
        Returns the experimenter's preferences annotation contents, as a
        ConfigParser instance

        :return:    See above
        :rtype:     ConfigParser
        """

        self._obj.unloadAnnotationLinks()
        cp = configparser.SafeConfigParser()
        prefs = self.getAnnotation('TODO.changeme.preferences')
        if prefs is not None:
            prefs = prefs.getValue()
            if prefs is not None:
                cp.readfp(StringIO(prefs))
        return cp

    def setRawPreferences(self, prefs):
        """
        Sets the experimenter's preferences annotation contents, passed in as
        a ConfigParser instance

        :param prefs:       ConfigParser of preferences
        :type prefs:        ConfigParser
        """

        ann = self.getAnnotation('TODO.changeme.preferences')
        t = StringIO()
        prefs.write(t)
        if ann is None:
            ann = CommentAnnotationWrapper()
            ann.setNs('TODO.changeme.preferences')
            ann.setValue(t.getvalue())
            self.linkAnnotation(ann)
        else:
            ann.setValue(t.getvalue())
            ann.save()
            self._obj.unloadAnnotationLinks()

    def getPreference(self, key, default='', section=None):
        """
        Gets a preference for the experimenter

        :param key:     Preference key
        :param default: Default value to return
        :param section: Preferences section
        :return:        Preference value
        """

        if section is None:
            section = 'DEFAULT'
        try:
            return self.getRawPreferences().get(section, key)
        except configparser.Error:
            return default
        return default

    def getPreferences(self, section=None):
        """
        Gets all preferences for section

        :param section: Preferences section
        :return:        Dict of preferences
        """

        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if prefs.has_section(section) or section == 'DEFAULT':
            return dict(prefs.items(section))
        return {}

    def setPreference(self, key, value, section=None):
        """
        Sets a preference for the experimenter

        :param key:     Preference key
        :param value:   Value to set
        :param section: Preferences section - created if needed
        """

        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if section not in prefs.sections():
            prefs.add_section(section)
        prefs.set(section, key, value)
        self.setRawPreferences(prefs)

    def getName(self):
        """
        Returns Experimenter's omeName

        :return:    Name
        :rtype:     String
        """

        return self.omeName

    def getDescription(self):
        """
        Returns Experimenter's Full Name

        :return:    Full Name or None
        :rtype:     String
        """

        return self.getFullName()

    def getFullName(self):
        """
        Gets full name of this experimenter. E.g. 'William James. Moore' or
        'William Moore' if no middle name

        :return:    Full Name or None
        :rtype:     String
        """

        try:
            lastName = self.lastName
            firstName = self.firstName
            middleName = self.middleName

            if middleName is not None and middleName != '':
                name = "%s %s %s" % (firstName, middleName, lastName)
            else:
                if firstName == "" and lastName == "":
                    name = self.omeName
                else:
                    name = "%s %s" % (firstName, lastName)
            return name
        except:
            logger.error(traceback.format_exc())
            return None

    def getNameWithInitial(self):
        """
        Returns first initial and Last name. E.g. 'W. Moore'

        :return:    Initial and last name
        :rtype:     String
        """

        try:
            if self.firstName is not None and self.lastName is not None:
                name = "%s. %s" % (self.firstName[:1], self.lastName)
            else:
                name = self.omeName
            return name
        except:
            logger.error(traceback.format_exc())
            return _("Unknown name")

    def isAdmin(self):
        """
        Returns true if Experimenter is Admin (if they are in any group named
        'system')

        :return:    True if experimenter is Admin
        :rtype:     Boolean
        """

        for ob in self._obj.copyGroupExperimenterMap():
            if ob is None:
                continue
            if ob.parent.name.val == "system":
                return True
        return False

    def isActive(self):
        """
        Returns true if Experimenter is Active (if they are in any group named
        'user')

        :return:    True if experimenter is Active
        :rtype:     Boolean
        """

        for ob in self._obj.copyGroupExperimenterMap():
            if ob is None:
                continue
            if ob.parent.name.val == "user":
                return True
        return False

    def isGuest(self):
        """
        Returns true if Experimenter is Guest (if they are in any group named
        'guest')

        :return:    True if experimenter is Admin
        :rtype:     Boolean
        """

        for ob in self._obj.copyGroupExperimenterMap():
            if ob is None:
                continue
            if ob.parent.name.val == "guest":
                return True
        return False

    def is_self(self):
        """ Returns True if this Experimenter is the current user """
        return self.getId() == self._conn.getUserId()

ExperimenterWrapper = _ExperimenterWrapper


class _ExperimenterGroupWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterGroupI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'ExperimenterGroup'
    LINK_CLASS = "GroupExperimenterMap"
    CHILD_WRAPPER_CLASS = 'ExperimenterWrapper'
    PARENT_WRAPPER_CLASS = None

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Returns string for building queries, loading Experimenters for each
        group.
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select distinct obj from ExperimenterGroup as obj "
                 "left outer join fetch obj.groupExperimenterMap as map "
                 "left outer join fetch map.child e")
        return query, [], omero.sys.ParametersI()

    def groupSummary(self, exclude_self=False):
        """
        Returns tuple of unsorted lists of 'leaders' and 'members' of
        the group.

        :return:    (list :class:`ExperimenterWrapper`,
                     list :class:`ExperimenterWrapper`)
        :rtype:     tuple
        """

        userId = None
        if exclude_self:
            userId = self._conn.getUserId()
        colleagues = []
        leaders = []
        if (not self.isPrivate() or self._conn.isLeader(self.id) or
                self._conn.isAdmin()):
            for d in self.copyGroupExperimenterMap():
                if d is None or d.child.id.val == userId:
                    continue
                if d.owner.val:
                    leaders.append(ExperimenterWrapper(self._conn, d.child))
                else:
                    colleagues.append(ExperimenterWrapper(self._conn, d.child))
        else:
            if self._conn.isLeader(self.id):
                leaders = [self._conn.getUser()]
            else:
                colleagues = [self._conn.getUser()]

        return (leaders, colleagues)

ExperimenterGroupWrapper = _ExperimenterGroupWrapper


class DetailsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetailsI class wrapper extends BlitzObjectWrapper.
    """

    def __init__(self, *args, **kwargs):
        super(DetailsWrapper, self).__init__(*args, **kwargs)
        self._owner = None
        self._group = None

    def getOwner(self):
        """
        Returns the Owner of the object that these details apply to

        :return:    Owner
        :rtype:     :class:`ExperimenterWrapper`
        """
        if self._owner is None:
            owner = self._obj.getOwner()
            self._owner = owner and ExperimenterWrapper(
                self._conn, self._obj.getOwner()) or None
        return self._owner

    def getGroup(self):
        """
        Returns the Group that these details refer to

        :return:    Group
        :rtype:     :class:`ExperimenterGroupWrapper`
        """
        if self._group is None:
            group = self._obj.getGroup()
            self._group = group and ExperimenterGroupWrapper(
                self._conn, self._obj.getGroup()) or None
        return self._group


from ._containers import DatasetWrapper
from ._containers import PlateAcquisitionWrapper
from ._containers import PlateWrapper
from ._containers import ProjectWrapper
from ._containers import ScreenWrapper
from ._containers import WellSampleWrapper
from ._containers import WellWrapper
from ._containers import _letterGridLabel

from ._files import FilesetWrapper

from ._images import ChannelWrapper
from ._images import ColorHolder
from ._images import ImageWrapper
from ._images import LightPathWrapper
from ._images import LogicalChannelWrapper
from ._images import PixelsWrapper
from ._images import PlaneInfoWrapper

from ._instruments import ArcWrapper
from ._instruments import BinningWrapper
from ._instruments import DetectorSettingsWrapper
from ._instruments import DetectorWrapper
from ._instruments import DichroicWrapper
from ._instruments import FilamentWrapper
from ._instruments import FilterSetWrapper
from ._instruments import FilterWrapper
from ._instruments import ImageStageLabelWrapper
from ._instruments import ImageStageLabelWrapper
from ._instruments import ImagingEnviromentWrapper
from ._instruments import ImagingEnvironmentWrapper
from ._instruments import InstrumentWrapper
from ._instruments import LaserWrapper
from ._instruments import LightEmittingDiodeWrapper
from ._instruments import LightSettingsWrapper
from ._instruments import MicroscopeWrapper
from ._instruments import OTFWrapper
from ._instruments import ObjectiveSettingsWrapper
from ._instruments import ObjectiveWrapper
from ._instruments import TransmittanceRangeWrapper

from._wrappers import KNOWN_WRAPPERS

def refreshWrappers():
    """
    this needs to be called by modules that extend the base wrappers
    """
    KNOWN_WRAPPERS.update({"project": ProjectWrapper,
                           "dataset": DatasetWrapper,
                           "image": ImageWrapper,
                           "screen": ScreenWrapper,
                           "plate": PlateWrapper,
                           "plateacquisition": PlateAcquisitionWrapper,
                           "acquisition": PlateAcquisitionWrapper,
                           "well": WellWrapper,
                           "wellsample": WellSampleWrapper,
                           "roi": RoiWrapper,
                           "shape": ShapeWrapper,
                           "experimenter": ExperimenterWrapper,
                           "experimentergroup": ExperimenterGroupWrapper,
                           "originalfile": OriginalFileWrapper,
                           "fileset": FilesetWrapper,
                           "commentannotation": CommentAnnotationWrapper,
                           "tagannotation": TagAnnotationWrapper,
                           "longannotation": LongAnnotationWrapper,
                           "booleanannotation": BooleanAnnotationWrapper,
                           "fileannotation": FileAnnotationWrapper,
                           "doubleannotation": DoubleAnnotationWrapper,
                           "termannotation": TermAnnotationWrapper,
                           "timestampannotation": TimestampAnnotationWrapper,
                           "mapannotation": MapAnnotationWrapper,
                           # allows for getObjects("Annotation", ids)
                           "annotation": AnnotationWrapper._wrap})


refreshWrappers()
