
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
import os

import warnings
from types import IntType, LongType, UnicodeType, ListType
from types import TupleType, StringTypes
from datetime import datetime
from cStringIO import StringIO
import ConfigParser

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
import omero.scripts as scripts

import Ice
import Glacier2

import traceback
import time
import array
import math
from decimal import Decimal

from gettext import gettext as _

import logging
from math import sqrt

from omero.rtypes import rstring, rint, rlong, rbool
from omero.rtypes import rtime, rlist, unwrap

logger = logging.getLogger(__name__)
THISPATH = os.path.dirname(os.path.abspath(__file__))

try:
    from PIL import Image, ImageDraw, ImageFont     # see ticket:2597
except:  # pragma: nocover
    try:
        # see ticket:2597
        import Image
        import ImageDraw
        import ImageFont
    except:
        logger.error(
            'No Pillow installed, line plots and split channel will fail!')

from ._core import omero_type
from ._core import fileread
from ._core import fileread_gen
from ._core import getPixelsQuery
from ._core import getChannelsQuery
from ._core import add_plate_filter
from ._core import OmeroRestrictionWrapper
from ._core import BlitzObjectWrapper
from ._core import AnnotationWrapper
from ._core import AnnotationLinkWrapper

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
        self.ice_config = map(
            lambda x: os.path.abspath(str(x)), filter(None, self.ice_config))

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
        except Exception, e:
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
        except Ice.UnknownException, x:  # pragma: no cover
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
        for proxy in self._proxies.values():
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
            for k, p in self._proxies.items():
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
                except Exception, x:  # pragma: no cover
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
                for key, value in self._ic_props.items():
                    if isinstance(value, unicode):
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
        except Ice.LocalException, x:  # pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        except Exception, x:  # pragma: no cover
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
            gid = long(gid)
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
        key_regex = '^omero\.cluster\.read_only\.runtime\.'
        properties = self.getConfigService().getConfigValues(key_regex)
        values = frozenset(properties.values())
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

        if obj_type not in links.keys():
            raise AttributeError("obj_type must be in %s" % str(links.keys()))

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
        dgr = admin_serv.getDefaultGroup(long(eid))
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
        for gr in admin_serv.containedGroups(long(eid)):
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
        for exp in admin_serv.containedExperimenters(long(gid)):
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
                    ['Image'], rtime(long(tfrom)),
                    rtime(long(tto)), p, False)['Image']:
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
            for k, v in attributes.items():
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
            wrapper_types = ", ".join(KNOWN_WRAPPERS.keys())
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
                    channelList = range(sizeC)
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
                channelList = range(sizeC)
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
                        plane = zctPlanes.next()
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
        except Exception, e:
            logger.error(
                "Failed to setPlane() on rawPixelsStore while creating Image",
                exc_info=True)
            exc = e
        try:
            rawPixelsStore.close(self.SERVICE_OPTS)
        except Exception, e:
            logger.error("Failed to close rawPixelsStore", exc_info=True)
            if exc is None:
                exc = e
        if exc is not None:
            raise exc

        # simply completing the generator - to avoid a GeneratorExit error.
        try:
            zctPlanes.next()
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
            imageIds = [long(i) for i in ids]
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
            for pos in range(0, long(fileSize), buf):
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
        obj = query_serv.find(klass, long(eid), self.SERVICE_OPTS)
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
        for key, value in types.getEnumerationsWithEntries().items():
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
        obj_ids = map(long, obj_ids)
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
        obj_ids = map(long, obj_ids)
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
            obj_id = long(obj_id)
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
                      useAcquisitionDate=False):
        """
        Search objects of type "Project", "Dataset", "Image", "Screen", "Plate"
        Returns a list of results

        :param obj_types:   E.g. ["Dataset", "Image"]
        :param text:        The text to search for
        :param created:     :class:`omero.rtime` list or tuple (start, stop)
        :param useAcquisitionDate: if True, then use Image.acquisitionDate
                                   rather than import date for queries.
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
            ownedBy = long(ownedBy)
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
                    t = time.localtime(t / 1000)
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
                        rv.extend(map(lambda x: t(self, x), results))
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
            for (pix, thumb) in thumbs_map.items():
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
            self.__f__name = f.im_self.ice_getIdentity().name
        except:
            self.__f__name = "unknown"

    def debug(self, exc_class, args, kwargs):
        logger.warn("%s on %s to <%s> %s(%r, %r)",
                    exc_class, self.__class__, self.__f__name, self.attr,
                    args, kwargs, exc_info=True)

    def handle_exception(self, e, *args, **kwargs):
        """
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
        except Exception, e:
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


class _OriginalFileAsFileObj(object):
    """
    Based on
    https://docs.python.org/2/library/stdtypes.html#file-objects
    """
    def __init__(self, originalfile, buf=2621440):
        self.originalfile = originalfile
        self.bufsize = buf
        # Can't use BlitzGateway.createRawFileStore as it always returns the
        # same store https://trello.com/c/lC8hFFix/522
        self.rfs = originalfile._conn.c.sf.createRawFileStore()
        self.rfs.setFileId(originalfile.id, originalfile._conn.SERVICE_OPTS)
        self.pos = 0

    def seek(self, n, mode=0):
        if mode == os.SEEK_SET:
            self.pos = n
        elif mode == os.SEEK_CUR:
            self.pos += n
        elif mode == os.SEEK_END:
            self.pos = self.rfs.size() + n
        else:
            raise ValueError('Invalid mode: %s' % mode)

    def tell(self):
        return self.pos

    def read(self, n=-1):
        buf = ''
        if n < 0:
            endpos = self.rfs.size()
        else:
            endpos = min(self.pos + n, self.rfs.size())
        while self.pos < endpos:
            nread = min(self.bufsize, endpos - self.pos)
            buf += self.rfs.read(self.pos, nread)
            self.pos += nread
        return buf

    def close(self):
        self.rfs.close()

    def __iter__(self):
        while self.pos < self.rfs.size():
            yield self.read(self.bufsize)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class _OriginalFileWrapper (BlitzObjectWrapper, OmeroRestrictionWrapper):
    """
    omero_model_OriginalFileI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'OriginalFile'

    def getFileInChunks(self, buf=2621440):
        """
        Returns a generator yielding chunks of the file data.

        :return:    Data from file in chunks
        :rtype:     Generator
        """
        with self.asFileObj(buf) as f:
            for chunk in f:
                yield chunk

    def asFileObj(self, buf=2621440):
        """
        Return a read-only file-like object.
        Caller must call close() on the file object after use.
        This can be done automatically by using the object as a
        ContextManager.
        For example:

            with f.asFileObj() as fo:
                content = fo.read()

        :return:    File-like object wrapping the OriginalFile
        :rtype:     File-like object
        """
        return _OriginalFileAsFileObj(self, buf)


OriginalFileWrapper = _OriginalFileWrapper

from ._annotations import BooleanAnnotationWrapper
from ._annotations import CommentAnnotationWrapper
from ._annotations import DoubleAnnotationWrapper
from ._annotations import LongAnnotationWrapper
from ._annotations import MapAnnotationWrapper
from ._annotations import TagAnnotationWrapper
from ._annotations import TermAnnotationWrapper
from ._annotations import TimestampAnnotationWrapper
from ._annotations import XmlAnnotationWrapper

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
        isAdmin = (len(filter(
            lambda x: x.name.val == 'system',
            self._conn.getAdminService().containedGroups(self.getId()))) == 1)
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
        cp = ConfigParser.SafeConfigParser()
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
        except ConfigParser.Error:
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


class _DatasetWrapper (BlitzObjectWrapper):
    """
    omero_model_DatasetI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Dataset'
    LINK_CLASS = "DatasetImageLink"
    CHILD_WRAPPER_CLASS = 'ImageWrapper'
    PARENT_WRAPPER_CLASS = 'ProjectWrapper'

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of Datasets by Projects.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'project': <project_id> to filter by Project
                        'image': <image_id> to filter by child Image
                        'orphaned': <bool>. Filter by 'not in Project'

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _DatasetWrapper, cls)._getQueryString(opts)
        if opts is None:
            opts = {}
        if 'project' in opts:
            query += ' join obj.projectLinks projectLinks'
            clauses.append('projectLinks.parent.id = :pid')
            params.add('pid', rlong(opts['project']))
        if 'image' in opts:
            query += ' join obj.imageLinks imagelinks'
            clauses.append('imagelinks.child.id = :iid')
            params.add('iid', rlong(opts['image']))
        if opts.get('orphaned'):
            clauses.append(
                """
                not exists (
                    select pdlink from ProjectDatasetLink as pdlink
                    where pdlink.child = obj.id
                )
                """
            )
        return (query, clauses, params)

    def __loadedHotSwap__(self):
        """
        In addition to loading the Dataset, this method also loads the Images
        """

        super(_DatasetWrapper, self).__loadedHotSwap__()
        if not self._obj.isImageLinksLoaded():
            links = self._conn.getQueryService().findAllByQuery(
                "select l from DatasetImageLink as l join fetch l.child as a "
                "where l.parent.id=%i"
                % (self._oid), None, self._conn.SERVICE_OPTS)
            self._obj._imageLinksLoaded = True
            self._obj._imageLinksSeq = links

DatasetWrapper = _DatasetWrapper


class _ProjectWrapper (BlitzObjectWrapper):
    """
    omero_model_ProjectI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Project'
    LINK_CLASS = "ProjectDatasetLink"
    CHILD_WRAPPER_CLASS = 'DatasetWrapper'
    PARENT_WRAPPER_CLASS = None

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of Projects by Datasets.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'dataset': <dataset_id> to filter by Dataset

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _ProjectWrapper, cls)._getQueryString(opts)
        if opts is None:
            opts = {}
        if 'dataset' in opts:
            query += ' join obj.datasetLinks datasetLinks'
            clauses.append('datasetLinks.child.id = :dataset_id')
            params.add('dataset_id', rlong(opts['dataset']))
        return (query, clauses, params)

ProjectWrapper = _ProjectWrapper


class _ScreenWrapper (BlitzObjectWrapper):
    """
    omero_model_ScreenI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Screen'
    LINK_CLASS = "ScreenPlateLink"
    CHILD_WRAPPER_CLASS = 'PlateWrapper'
    PARENT_WRAPPER_CLASS = None

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of Screens by Plate.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'plate': <plate_id> to filter by Plate

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _ScreenWrapper, cls)._getQueryString(opts)
        if opts is None:
            opts = {}
        if 'plate' in opts:
            query += ' join obj.plateLinks plateLinks'
            clauses.append('plateLinks.child.id = :plate_id')
            params.add('plate_id', rlong(opts['plate']))
        return (query, clauses, params)

ScreenWrapper = _ScreenWrapper


def _letterGridLabel(i):
    """  Convert number to letter label. E.g. 0 -> 'A' and 100 -> 'CW'  """
    r = chr(ord('A') + i % 26)
    i = i/26
    while i > 0:
        i -= 1
        r = chr(ord('A') + i % 26) + r
        i = i/26
    return r


class _PlateWrapper (BlitzObjectWrapper, OmeroRestrictionWrapper):
    """
    omero_model_PlateI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Plate'
    LINK_CLASS = None
    CHILD_WRAPPER_CLASS = 'WellWrapper'
    PARENT_WRAPPER_CLASS = 'ScreenWrapper'

    def __prepare__(self):
        self.__reset__()

    def __reset__(self):
        """
        Clears child cache, so next _listChildren will query the server
        """
        self._childcache = None
        self._gridSize = None

    def _loadPlateAcquisitions(self):
        p = omero.sys.Parameters()
        p.map = {}
        p.map["pid"] = self._obj.id
        sql = ("select pa from PlateAcquisition as pa "
               "join fetch pa.plate as p where p.id=:pid")
        self._obj._plateAcquisitionsSeq = self._conn.getQueryService(
            ).findAllByQuery(sql, p, self._conn.SERVICE_OPTS)
        self._obj._plateAcquisitionsLoaded = True

    def countPlateAcquisitions(self):
        if self._obj.sizeOfPlateAcquisitions() < 0:
            self._loadPlateAcquisitions()
        return self._obj.sizeOfPlateAcquisitions()

    def listPlateAcquisitions(self):
        if not self._obj._plateAcquisitionsLoaded:
            self._loadPlateAcquisitions()
        for pa in self._obj.copyPlateAcquisitions():
            yield PlateAcquisitionWrapper(self._conn, pa)

    @timeit
    def getNumberOfFields(self, pid=None):
        """
        Returns tuple of min and max of indexed collection of well samples
        per plate acquisition if exists
        """

        q = self._conn.getQueryService()
        sql = "select minIndex(ws), maxIndex(ws) from Well w " \
            "join w.wellSamples ws where w.plate.id=:oid"

        p = omero.sys.Parameters()
        p.map = {}
        p.map["oid"] = self._obj.id
        if pid is not None:
            sql += " and ws.plateAcquisition.id=:pid"
            p.map["pid"] = rlong(pid)

        fields = None
        try:
            res = [r for r in unwrap(
                q.projection(
                    sql, p, self._conn.SERVICE_OPTS))[0] if r is not None]
            if len(res) == 2:
                fields = tuple(res)
        except:
            pass
        return fields

    def _listChildren(self, **kwargs):
        """
        Lists Wells in this plate, not sorted. Saves wells to
        :attr:`_childcache` map, where key is (row, column).

        :rtype: list of :class:`omero.model.WellI` objects
        :return: child objects.
        """
        if self._childcache is None:
            q = self._conn.getQueryService()
            params = omero.sys.Parameters()
            params.map = {}
            params.map["oid"] = omero_type(self.getId())
            query = ("select well from Well as well "
                     "join fetch well.details.creationEvent "
                     "join fetch well.details.owner "
                     "join fetch well.details.group "
                     "left outer join fetch well.plate as pt "
                     "left outer join fetch well.wellSamples as ws "
                     "left outer join fetch ws.image as img "
                     "where well.plate.id = :oid")

            self._childcache = {}
            for well in q.findAllByQuery(
                    query, params, self._conn.SERVICE_OPTS):
                self._childcache[(well.row.val, well.column.val)] = well
        return self._childcache.values()

    def countChildren(self):
        return len(self._listChildren())

    def setGridSizeConstraints(self, row, col):
        """
        Makes sure the grid side count is the exact power of two of row and
        col arguments, keeping their ratio, that fits the existing well count.
        """
        gs = self.getGridSize()
        mul = 0
        while gs['rows'] > (row*(2**mul)) or gs['columns'] > (col*(2**mul)):
            mul += 1
        self._gridSize['rows'] = row * (2**mul)
        self._gridSize['columns'] = col * (2**mul)

    def getGridSize(self):
        """
        Iterates all wells on plate to retrieve grid size as {'rows': rSize,
        'columns':cSize} dict.

        :rtype:     dict of {'rows': rSize, 'columns':cSize}
        """
        if self._gridSize is None:
            q = self._conn.getQueryService()
            params = omero.sys.ParametersI()
            params.addId(self.getId())
            query = "select max(row), max(column) from Well "\
                    "where plate.id = :id"
            res = q.projection(query, params, self._conn.SERVICE_OPTS)
            (row, col) = res[0]
            self._gridSize = {'rows': row.val+1, 'columns': col.val+1}
        return self._gridSize

    def getWellGrid(self, index=0):
        """
        Returns a grid of WellWrapper objects, indexed by [row][col].

        :rtype:     2D array of :class:`WellWrapper`. Empty well positions
                    are None
        """
        grid = self.getGridSize()
        childw = self._getChildWrapper()
        rv = [[None]*grid['columns'] for x in range(grid['rows'])]
        for child in self._listChildren():
            rv[child.row.val][child.column.val] = childw(
                self._conn, child, index=index)
        return rv

    def getColumnLabels(self):
        """
        Returns a list of labels for the columns on this plate.
        E.g. [1, 2, 3...] or ['A', 'B', 'C'...] etc
        """
        if (self.columnNamingConvention and
                self.columnNamingConvention.lower() == 'letter'):
            # this should simply be precalculated!
            return [_letterGridLabel(x)
                    for x in range(self.getGridSize()['columns'])]
        else:
            return range(1, self.getGridSize()['columns']+1)

    def getRowLabels(self):
        """
        Returns a list of labels for the rows on this plate.
        E.g. [1, 2, 3...] or ['A', 'B', 'C'...] etc
        """
        if (self.rowNamingConvention and
                self.rowNamingConvention.lower() == 'number'):
            return range(1, self.getGridSize()['rows']+1)
        else:
            # this should simply be precalculated!
            return [_letterGridLabel(x)
                    for x in range(self.getGridSize()['rows'])]

#        if self._childcache is None:
#            q = self._conn.getQueryService()
#            params = omero.sys.Parameters()
#            params.map = {}
#            params.map["oid"] = omero_type(self.getId())
#            query = "select well from Well as well "\
#                    "left outer join fetch well.wellSamples as ws " \
#                    "where well.plate.id = :oid"
#            children = q.findAllByQuery(query, params)
#        else:
#            children = self._listChildren()
#        f = 0
#        for child in children:
#            f = max(len(child._wellSamplesSeq), f)
#        return f

    def exportOmeTiff(self):
        """
        Make sure full project export doesn't pick up wellsample images
        TODO: do we want to support this at all?
        """
        return None

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Custom query to load Screen with Plate.

        Also handles filtering of Plates by Screens.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'screen': <screen_id> to filter by Screen
                        'well': <well_id> to filter by Well
                        'orphaned': <bool>. Filter by 'not in Screen'

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from Plate as obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent "
                 "left outer join fetch obj.screenLinks spl "
                 "left outer join fetch spl.parent sc")
        # NB: we don't use base _getQueryString.
        clauses = []
        params = omero.sys.ParametersI()
        if opts is None:
            opts = {}
        if 'screen' in opts:
            clauses.append('spl.parent.id = :sid')
            params.add('sid', rlong(opts['screen']))
        if 'well' in opts:
            query += ' join obj.wells wells'
            clauses.append('wells.id = :well_id')
            params.add('well_id', rlong(opts['well']))
        if opts.get('orphaned'):
            clauses.append(
                """
                not exists (
                    select splink from ScreenPlateLink as splink
                    where splink.child = obj.id
                )
                """
            )
        return (query, clauses, params)

PlateWrapper = _PlateWrapper


class _PlateAcquisitionWrapper (BlitzObjectWrapper):

    OMERO_CLASS = 'PlateAcquisition'

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of PlateAcquisitions by Plate.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'plate': <plate_id> to filter by Plate

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _PlateAcquisitionWrapper, cls)._getQueryString(opts)
        add_plate_filter(clauses, params, opts)
        return (query, clauses, params)

    def getName(self):
        name = super(_PlateAcquisitionWrapper, self).getName()
        if name is None:
            if self.startTime is not None and self.endTime is not None:
                name = "%s - %s" % (
                    datetime.fromtimestamp(self.startTime/1000),
                    datetime.fromtimestamp(self.endTime/1000))
            else:
                name = "Run %i" % self.id
        return name
    name = property(getName)

    def listParents(self, withlinks=False):
        """
        Because PlateAcquisitions are direct children of plates, with no links
        in between, a special listParents is needed
        """
        rv = self._conn.getObject('Plate', self.plate.id.val)
        if withlinks:
            return [(rv, None)]
        return [rv]

    def getStartTime(self):
        """Get the StartTime as a datetime object or None if not set."""
        if self.startTime:
            return datetime.fromtimestamp(self.startTime/1000)

    def getEndTime(self):
        """Get the EndTime as a datetime object or None if not set."""
        if self.endTime:
            return datetime.fromtimestamp(self.endTime/1000)

PlateAcquisitionWrapper = _PlateAcquisitionWrapper


class _WellWrapper (BlitzObjectWrapper, OmeroRestrictionWrapper):
    """
    omero_model_WellI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Well'
    LINK_CLASS = None
    CHILD_WRAPPER_CLASS = 'WellSampleWrapper'
    PARENT_WRAPPER_CLASS = 'PlateWrapper'

    def __prepare__(self, **kwargs):
        try:
            self.index = int(kwargs['index'])
        except:
            self.index = 0
        self.__reset__()

    def __reset__(self):
        """
        Clears child cache, so next _listChildren will query the server
        """
        self._childcache = None

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of Wells by Plate.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'plate': <plate_id> to filter by Plate
                        'load_images': <bool> to load WellSamples and Images
                        'load_pixels': <bool> to load Image Pixels
                        'load_channels': <bool> to load Pixels and Channels

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _WellWrapper, cls)._getQueryString(opts)
        if opts is None:
            opts = {}
        add_plate_filter(clauses, params, opts)
        load_images = opts.get('load_images')
        load_pixels = opts.get('load_pixels')
        load_channels = opts.get('load_channels')
        if 'plateacquisition' in opts:
            clauses.append('plateAcquisition.id = :plateAcq')
            params.add('plateAcq', rlong(opts['plateacquisition']))
            load_images = True
        if 'wellsample_index' in opts:
            clauses.append('index(wellSamples) = :wellsample_index')
            params.add('wellsample_index', rint(opts['wellsample_index']))
        if load_images or load_pixels or load_channels:
            # NB: Using left outer join, we may get Wells with no Images
            query += " left outer join fetch obj.wellSamples as wellSamples"\
                     " left outer join fetch wellSamples.image as image"\
                     " left outer join fetch wellSamples.plateAcquisition"\
                     " as plateAcquisition"
        if load_pixels or load_channels:
            query += getPixelsQuery("image")
        if load_channels:
            query += getChannelsQuery()

        return (query, clauses, params)

    def __loadedHotSwap__(self):
        query = ("select well from Well as well "
                 "join fetch well.details.creationEvent "
                 "join fetch well.details.owner "
                 "join fetch well.details.group "
                 "left outer join fetch well.wellSamples as ws "
                 "left outer join fetch ws.image as img "
                 "where well.id = %d" % self.getId())

        self._obj = self._conn.getQueryService().findByQuery(
            query, None, self._conn.SERVICE_OPTS)

    def _listChildren(self, **kwargs):
        if self._childcache is None:
            if not self.isWellSamplesLoaded():
                self.__loadedHotSwap__()
            if self.isWellSamplesLoaded():
                self._childcache = self.copyWellSamples()
        return self._childcache

    def simpleMarshal(self, xtra=None, parents=False):
        """
        Marshals the Well ID, label and Plate ID with
        simple Marshal of the first image in the Well.
        """
        rv = self.getImage().simpleMarshal(xtra=xtra)
        rv['wellPos'] = self.getWellPos()
        rv['plateId'] = self._obj.plate.id.val
        rv['wellId'] = self.getId()
        return rv

    def getWellPos(self):
        """
        Gets the Well's label according to the row and column
        naming convention on the Plate. E.g. 'A1'
        """
        plate = self.getParent()
        rv = "%s%s" % (
            plate.getRowLabels()[self.row],
            plate.getColumnLabels()[self.column])
        return rv

    def listParents(self, withlinks=False):
        """
        Because wells are direct children of plates, with no links in between,
        a special listParents is needed
        """
        # Create PlateWrapper with plate - will load plate if unloaded
        rv = PlateWrapper(self._conn, self._obj.plate)
        # Cache the loaded plate
        self._obj.plate = rv._obj
        if withlinks:
            return [(rv, None)]
        return [rv]

    def getScreens(self):
        """ returns the screens that link to plates that link to this well """
        params = omero.sys.Parameters()
        params.map = {'id': omero_type(self.getId())}
        query = """select s from Well w
        left outer join w.plate p
        left outer join p.screenLinks spl
        left outer join spl.parent s
        where spl.parent.id=s.id and spl.child.id=p.id and w.plate.id=p.id
        and w.id=:id"""
        return [omero.gateway.ScreenWrapper(self._conn, x) for x in
                self._conn.getQueryService().findAllByQuery(
                    query, params, self._conn.SERVICE_OPTS)]

    def isWellSample(self):
        """
        Return True if well samples exist (loaded)

        :return:    True if well samples loaded
        :rtype:     Boolean
        """

        if self.isWellSamplesLoaded():
            childnodes = self.copyWellSamples()
            logger.debug(
                'listChildren for %s %d: already loaded, %d samples'
                % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            if len(childnodes) > 0:
                return True
        return False

    def countWellSample(self):
        """
        Return the number of well samples loaded

        :return:    well sample count
        :rtype:     Int
        """
        return len(self._listChildren())

    def getWellSample(self, index=None):
        """
        Return the well sample at the specified index. If index is omitted,
        the currently selected index is used instead (self.index) and if
        that is not defined, the first one (index 0) is returned.

        :param index: the well sample index
        :type index: integer
        :return:    The Well Sample
        :rtype:     :class:`WellSampleWrapper`
        """
        if index is None:
            index = self.index
        if index is None:
            index = 0
        index = int(index)
        childnodes = self._listChildren()
        if len(childnodes) > index:
            return self._getChildWrapper()(self._conn, childnodes[index])
        return None

    def getImage(self, index=None):
        """
        Return the image at the specified well sample index. If index is
        omitted, the currently selected index is used instead (self.index) and
        if that is not defined, the first one (index 0) is returned.

        :param index: the well sample index
        :type index: integer
        :return:    The Image
        :rtype:     :class:`ImageWrapper`
        """
        wellsample = self.getWellSample(index)
        if wellsample:
            return wellsample.getImage()
        return None

    def selectedWellSample(self):
        """
        Return the well sample at the current index (0 if not set)

        :return:    The Well Sample wrapper
        :rtype:     :class:`WellSampleWrapper`

        """
        return self.getWellSample()

#    def loadWellSamples (self):
#        """
#        Return a generator yielding child objects
#
#        :return:    Well Samples
#        :rtype:     :class:`WellSampleWrapper` generator
#        """
#
#        if getattr(self, 'isWellSamplesLoaded')():
#            childnodes = getattr(self, 'copyWellSamples')()
#            logger.debug(
#                'listChildren for %s %d: already loaded, %d samples'
#                % (self.OMERO_CLASS, self.getId(), len(childnodes)))
#            for ch in childnodes:
#                yield WellSampleWrapper(self._conn, ch)
#
#    def plate(self):
#        """
#        Gets the Plate.
#
#        :return:    The Plate
#        :rtype:     :class:`PlateWrapper`
#        """
#
#        return PlateWrapper(self._conn, self._obj.plate)

WellWrapper = _WellWrapper


class _WellSampleWrapper (BlitzObjectWrapper):
    """
    omero_model_WellSampleI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'WellSample'
    CHILD_WRAPPER_CLASS = 'ImageWrapper'
    PARENT_WRAPPER_CLASS = 'WellWrapper'
    LINK_CLASS = 'WellSample'
    LINK_CHILD = 'image'

    @staticmethod
    def LINK_PARENT(link):
        """Direct parent is Well. No Link between Well and WellSample."""
        return link

    def listParents(self, withlinks=False):
        """
        Because wellsamples are direct children of wells, with no links in
        between, a special listParents is needed
        """
        rv = self._conn.getQueryService().findAllByQuery(
            ("select w from Well w "
             "left outer join fetch w.wellSamples as ws "
             "where ws.id=%d" % self.getId()),
            None, self._conn.SERVICE_OPTS)
        if not len(rv):
            rv = [None]
        # rv = self._conn.getObject('Plate', self.plate.id.val)
        pwc = self._getParentWrappers()
        if withlinks:
            return [(pwc[0](self._conn, x), None) for x in rv]
        return [pwc[0](self._conn, x) for x in rv]

    def getImage(self):
        """
        Gets the Image for this well sample.

        :return:    The Image
        :rtype:     :class:`ImageWrapper`
        """
        return self._getChildWrapper()(self._conn, self._obj.image)

    def image(self):
        """
        Gets the Image for this well sample.

        :return:    The Image
        :rtype:     :class:`ImageWrapper`
        """
        return self.getImage()

    def getPlateAcquisition(self):
        """
        Gets the PlateAcquisition for this well sample, or None

        :return:    The PlateAcquisition
        :rtype:     :class:`PlateAcquisitionWrapper` or None
        """
        aquisition = self._obj.plateAcquisition
        if aquisition is None:
            return None
        return PlateAcquisitionWrapper(self._conn, aquisition)

WellSampleWrapper = _WellSampleWrapper


# IMAGE #


class ColorHolder (object):
    """
    Stores color internally as (R,G,B,A) and allows setting and getting in
    multiple formats
    """

    _color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}

    def __init__(self, colorname=None):
        """
        If colorname is 'red', 'green' or 'blue', set color accordingly
        - Otherwise black

        :param colorname:   'red', 'green' or 'blue'
        :type colorname:    String
        """

        self._color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}
        if colorname and colorname.lower() in self._color.keys():
            self._color[colorname.lower()] = 255

    @classmethod
    def fromRGBA(cls, r, g, b, a):
        """
        Class method for creating a ColorHolder from r,g,b,a values

        :param r:   red 0 - 255
        :type r:    int
        :param g:   green 0 - 255
        :type g:    int
        :param b:   blue 0 - 255
        :type b:    int
        :param a:   alpha 0 - 255
        :type a:    int
        :return:    new Color object
        :rtype:     :class:`ColorHolder`
        """

        rv = cls()
        rv.setRed(r)
        rv.setGreen(g)
        rv.setBlue(b)
        rv.setAlpha(a)
        return rv

    def getRed(self):
        """
        Gets the Red component

        :return:    red
        :rtype:     int
        """

        return self._color['red']

    def setRed(self, val):
        """
        Set red, as int 0..255

        :param val: value of Red.
        :type val:  Int
        """

        self._color['red'] = max(min(255, int(val)), 0)

    def getGreen(self):
        """
        Gets the Green component

        :return:    green
        :rtype:     int
        """

        return self._color['green']

    def setGreen(self, val):
        """
        Set green, as int 0..255

        :param val: value of Green.
        :type val:  Int
        """

        self._color['green'] = max(min(255, int(val)), 0)

    def getBlue(self):
        """
        Gets the Blue component

        :return:    blue
        :rtype:     int
        """

        return self._color['blue']

    def setBlue(self, val):
        """
        Set Blue, as int 0..255

        :param val: value of Blue.
        :type val:  Int
        """

        self._color['blue'] = max(min(255, int(val)), 0)

    def getAlpha(self):
        """
        Gets the Alpha component

        :return:    alpha
        :rtype:     int
        """

        return self._color['alpha']

    def setAlpha(self, val):
        """
        Set alpha, as int 0..255.

        :param val: value of alpha.
        """

        self._color['alpha'] = max(min(255, int(val)), 0)

    def getHtml(self):
        """
        Gets the html usable color. Dumps the alpha information. E.g. 'FF0000'

        :return:    html color
        :rtype:     String
        """

        return "%(red)0.2X%(green)0.2X%(blue)0.2X" % (self._color)

    def getCss(self):
        """
        Gets the css string: rgba(r,g,b,a)

        :return:    css color
        :rtype:     String
        """

        c = self._color.copy()
        c['alpha'] /= 255.0
        return "rgba(%(red)i,%(green)i,%(blue)i,%(alpha)0.3f)" % (c)

    def getRGB(self):
        """
        Gets the (r,g,b) as a tuple.

        :return:    Tuple of (r,g,b) values
        :rtype:     tuple of ints
        """

        return (self._color['red'], self._color['green'], self._color['blue'])

    def getInt(self):
        """
        Returns the color as an Integer

        :return:    Integer
        :rtype:     int
        """

        r = self.getRed() << 24
        g = self.getGreen() << 16
        b = self.getBlue() << 8
        a = self.getAlpha()
        rgba_int = r+g+b+a
        if (rgba_int > (2**31-1)):       # convert to signed 32-bit int
            rgba_int = rgba_int - 2**32
        return int(rgba_int)


class _LogicalChannelWrapper (BlitzObjectWrapper):
    """
    omero_model_LogicalChannelI class wrapper extends BlitzObjectWrapper.
    Specifies a number of _attrs for the channel metadata.
    """
    _attrs = ('name',
              'pinHoleSize',
              '#illumination',
              'contrastMethod',
              'excitationWave',
              'emissionWave',
              'fluor',
              'ndFilter',
              'otf',
              'detectorSettings|DetectorSettingsWrapper',
              'lightSourceSettings|LightSettingsWrapper',
              'filterSet|FilterSetWrapper',
              'samplesPerPixel',
              '#photometricInterpretation',
              'mode',
              'pockelCellSetting',
              '()lightPath|',
              'version')

    def __loadedHotSwap__(self):
        """ Loads the logical channel using the metadata service """
        if self._obj is not None:
            ctx = self._conn.SERVICE_OPTS.copy()
            if ctx.getOmeroGroup() is None:
                ctx.setOmeroGroup(-1)
            self._obj = self._conn.getMetadataService(
                ).loadChannelAcquisitionData([self._obj.id.val], ctx)[0]

    def getLightPath(self):
        """
        Make sure we have the channel fully loaded, then return
        :class:`LightPathWrapper`
        """
        self.__loadedHotSwap__()
        if self._obj.lightPath is not None:
            return LightPathWrapper(self._conn, self._obj.lightPath)

LogicalChannelWrapper = _LogicalChannelWrapper


class _LightPathWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('dichroic|DichroicWrapper',
              '()emissionFilters|',
              '()excitationFilters|')

    OMERO_CLASS = 'LightPath'

    def getExcitationFilters(self):
        """ Returns list of excitation :class:`FilterWrapper`. Ordered
        collections can contain nulls"""
        return [FilterWrapper(self._conn, link.child)
                for link in self.copyExcitationFilterLink()
                if link is not None]

    def getEmissionFilters(self):
        """ Returns list of emission :class:`FilterWrapper` """
        return [FilterWrapper(self._conn, link.child)
                for link in self.copyEmissionFilterLink()]

LightPathWrapper = _LightPathWrapper


class _PlaneInfoWrapper (BlitzObjectWrapper):
    """
    omero_model_PlaneInfo class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = "PlaneInfo"

    def getDeltaT(self, units=None):
        """
        Gets the PlaneInfo deltaT with units support
        If units is True, return omero.model.TimeI
        If units specifies a different unit E.g. "MILLISECOND", we convert

        :param units:       Option to include units in tuple
        :type units:        True or unit string, e.g. "S"

        :return:            DeltaT value or omero.model.TimeI
        """
        return self._unwrapunits(self._obj.getDeltaT(), units=units)

    def getExposureTime(self, units=None):
        """
        Gets the PlaneInfo ExposureTime with units support
        If units is True, return omero.model.TimeI
        If units specifies a different unit E.g. "MILLISECOND", we convert

        :param units:       Option to include units in tuple
        :type units:        True or unit string

        :return:            ExposureTime value or omero.model.TimeI
        """
        return self._unwrapunits(self._obj.getExposureTime(), units=units)

PlaneInfoWrapper = _PlaneInfoWrapper


class _PixelsWrapper (BlitzObjectWrapper):
    """
    omero_model_PixelsI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Pixels'

    def _prepareRawPixelsStore(self):
        """
        Creates RawPixelsStore and sets the id etc
        """
        ps = self._conn.createRawPixelsStore()
        ps.setPixelsId(self._obj.id.val, True, self._conn.SERVICE_OPTS)
        return ps

    def getPixelsType(self):
        """
        This simply wraps the :class:`omero.model.PixelsType` object in a
        BlitzObjectWrapper. Shouldn't be needed when this is done
        automatically.

        It has the methods :meth:`getValue` and :meth:`getBitSize`.
        """
        return BlitzObjectWrapper(self._conn, self._obj.getPixelsType())

    def copyPlaneInfo(self, theC=None, theT=None, theZ=None):
        """
        Loads plane infos and returns sequence of omero.model.PlaneInfo objects
        wrapped in BlitzObjectWrappers ordered by planeInfo.deltaT.
        Set of plane infos can be filtered by C, T or Z

        :param theC:    Filter plane infos by Channel index
        :type  theC:    int or None
        :param theT:    Filter plane infos by Time index
        :type  theT:    int or None
        :param theZ:    Filter plane infos by Z index
        :type  theT:    int or None

        :return:  Generator of PlaneInfo wrapped in BlitzObjectWrappers
        """

        params = omero.sys.Parameters()
        params.map = {}
        params.map["pid"] = rlong(self._obj.id)
        query = "select info from PlaneInfo as info" \
                " join fetch info.deltaT as dt" \
                " join fetch info.exposureTime as et" \
                " where info.pixels.id=:pid"
        if theC is not None:
            params.map["theC"] = rint(theC)
            query += " and info.theC=:theC"
        if theT is not None:
            params.map["theT"] = rint(theT)
            query += " and info.theT=:theT"
        if theZ is not None:
            params.map["theZ"] = rint(theZ)
            query += " and info.theZ=:theZ"
        query += " order by info.deltaT"
        queryService = self._conn.getQueryService()
        result = queryService.findAllByQuery(
            query, params, self._conn.SERVICE_OPTS)
        for pi in result:
            yield PlaneInfoWrapper(self._conn, pi)

    def getPlanes(self, zctList):
        """
        Returns generator of numpy 2D planes from this set of pixels for a
        list of Z, C, T indexes.

        :param zctList:     A list of indexes: [(z,c,t), ]
        """

        zctTileList = []
        for zct in zctList:
            z, c, t = zct
            zctTileList.append((z, c, t, None))
        return self.getTiles(zctTileList)

    def getPlane(self, theZ=0, theC=0, theT=0):
        """
        Gets the specified plane as a 2D numpy array by calling
        :meth:`getPlanes`
        If a range of planes are required, :meth:`getPlanes` is approximately
        30% faster.
        """
        planeList = list(self.getPlanes([(theZ, theC, theT)]))
        return planeList[0]

    def getTiles(self, zctTileList):
        """
        Returns generator of numpy 2D planes from this set of pixels for a
        list of (Z, C, T, tile) where tile is (x, y, width, height) or None if
        you want the whole plane.

        :param zctrList:     A list of indexes: [(z,c,t, region), ]
        """

        import numpy
        from struct import unpack

        pixelTypes = {PixelsTypeint8: ['b', numpy.int8],
                      PixelsTypeuint8: ['B', numpy.uint8],
                      PixelsTypeint16: ['h', numpy.int16],
                      PixelsTypeuint16: ['H', numpy.uint16],
                      PixelsTypeint32: ['i', numpy.int32],
                      PixelsTypeuint32: ['I', numpy.uint32],
                      PixelsTypefloat: ['f', numpy.float32],
                      PixelsTypedouble: ['d', numpy.float64]}
        rawPixelsStore = None
        sizeX = self.sizeX
        sizeY = self.sizeY
        pixelType = self.getPixelsType().value
        numpyType = pixelTypes[pixelType][1]
        exc = None
        try:
            rawPixelsStore = self._prepareRawPixelsStore()
            for zctTile in zctTileList:
                z, c, t, tile = zctTile
                if tile is None:
                    rawPlane = rawPixelsStore.getPlane(z, c, t)
                    planeY = sizeY
                    planeX = sizeX
                else:
                    x, y, width, height = tile
                    rawPlane = rawPixelsStore.getTile(
                        z, c, t, x, y, width, height)
                    planeY = height
                    planeX = width
                # +str(sizeX*sizeY)+pythonTypes[pixelType]
                convertType = '>%d%s' % (
                    (planeY*planeX), pixelTypes[pixelType][0])
                convertedPlane = unpack(convertType, rawPlane)
                remappedPlane = numpy.array(convertedPlane, numpyType)
                remappedPlane.resize(planeY, planeX)
                yield remappedPlane
        except Exception, e:
            logger.error(
                "Failed to getPlane() or getTile() from rawPixelsStore",
                exc_info=True)
            exc = e
        try:
            if rawPixelsStore is not None:
                rawPixelsStore.close()
        except Exception, e:
            logger.error("Failed to close rawPixelsStore", exc_info=True)
            if exc is None:
                exc = e
        if exc is not None:
            raise exc

    def getTile(self, theZ=0, theC=0, theT=0, tile=None):
        """
        Gets the specified plane as a 2D numpy array by calling
        :meth:`getTiles`
        If a range of tile are required, :meth:`getTiles` is approximately 30%
        faster.
        """
        tileList = list(self.getTiles([(theZ, theC, theT, tile)]))
        return tileList[0]

PixelsWrapper = _PixelsWrapper


class _FilesetWrapper (BlitzObjectWrapper):
    """
    omero_model_FilesetI class wrapper extends BlitzObjectWrapper
    """

    OMERO_CLASS = 'Fileset'

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("Fileset").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = "select obj from Fileset obj "\
            "left outer join fetch obj.images as image "\
            "left outer join fetch obj.usedFiles as usedFile " \
            "join fetch usedFile.originalFile"
        return query, [], omero.sys.ParametersI()

    def copyImages(self):
        """ Returns a list of :class:`ImageWrapper` linked to this Fileset """
        return [ImageWrapper(self._conn, i) for i in self._obj.copyImages()]

    def listFiles(self):
        """
        Returns a list of :class:`OriginalFileWrapper` linked to this Fileset
        via Fileset Entries
        """
        return [OriginalFileWrapper(self._conn, f.originalFile)
                for f in self._obj.copyUsedFiles()]

FilesetWrapper = _FilesetWrapper


class _ChannelWrapper (BlitzObjectWrapper):
    """
    omero_model_ChannelI class wrapper extends BlitzObjectWrapper.
    """

    BLUE_MIN = 400
    BLUE_MAX = 500
    GREEN_MIN = 501
    GREEN_MAX = 600
    RED_MIN = 601
    RED_MAX = 700
    COLOR_MAP = ((BLUE_MIN, BLUE_MAX, ColorHolder('Blue')),
                 (GREEN_MIN, GREEN_MAX, ColorHolder('Green')),
                 (RED_MIN, RED_MAX, ColorHolder('Red')),
                 )

    OMERO_CLASS = 'Channel'

    def __prepare__(self, idx=-1, re=None, img=None):
        """
        Sets values of idx, re and img
        """
        self._re = re
        self._idx = idx
        self._img = img

    def save(self):
        """
        Extends the superclass save method to save Pixels. Returns result of
        saving superclass (TODO: currently this is None)
        """

        self._obj.setPixels(
            omero.model.PixelsI(self._obj.getPixels().getId(), False))
        return super(_ChannelWrapper, self).save()

    def isActive(self):
        """
        Returns True if the channel is active (turned on in rendering settings)

        :return:    True if Channel is Active
        :rtype:     Boolean
        """

        if self._re is None:
            return False
        return self._re.isActive(self._idx, self._conn.SERVICE_OPTS)

    def getLogicalChannel(self):
        """
        Returns the logical channel

        :return:    Logical Channel
        :rtype:     :class:`LogicalChannelWrapper`
        """

        if self._obj.logicalChannel is not None:
            return LogicalChannelWrapper(self._conn, self._obj.logicalChannel)

    def getLabel(self):
        """
        Returns the logical channel name, emission wave or index. The first
        that is not null in the described order.

        :return:    The logical channel string representation
        :rtype:     String
        """

        lc = self.getLogicalChannel()
        rv = lc.name
        if rv is None or len(rv.strip()) == 0:
            rv = lc.emissionWave
            if rv is not None:
                rv = rv.getValue()  # FIXME: units ignored for wavelength
                # Don't show as double if it's really an int
                if int(rv) == rv:
                    rv = int(rv)
        if rv is None or len(unicode(rv).strip()) == 0:
            rv = self._idx
        return unicode(rv)

    def getName(self):
        """
        Returns the logical channel name or None

        :return:    The logical channel string representation
        :rtype:     String
        """

        lc = self.getLogicalChannel()
        rv = lc.name
        if rv is not None:
            return unicode(rv)

    def getEmissionWave(self, units=None):
        """
        Returns the emission wave or None.
        If units is true, returns omero.model.LengthI
        If units specifies a unit e,g, "METER", we convert.

        :return:    Emission wavelength or None
        :rtype:     float or omero.model.LengthI
        """

        lc = self.getLogicalChannel()
        return self._unwrapunits(lc.emissionWave, units=units)

    def getExcitationWave(self, units=None):
        """
        Returns the excitation wave or None.
        If units is true, returns omero.model.LengthI
        If units specifies a unit e,g, "METER", we convert.

        :return:    Excitation wavelength or None
        :rtype:     float or omero.model.LengthI
        """

        lc = self.getLogicalChannel()
        return self._unwrapunits(lc.excitationWave, units=units)

    def getColor(self):
        """
        Returns the rendering settings color of this channel

        :return:    Channel color
        :rtype:     :class:`ColorHolder`
        """

        if self._re is None:
            return None
        return ColorHolder.fromRGBA(
            *self._re.getRGBA(self._idx, self._conn.SERVICE_OPTS))

    def getLut(self):
        """
        Returns the Lookup Table name for the Channel.
        E.g. "cool.lut" or None if no LUT.

        :return:    Lut name.
        :rtype:     String
        """

        if self._re is None:
            return None
        lut = self._re.getChannelLookupTable(self._idx)
        if not lut or len(lut) == 0:
            return None
        return lut

    def getWindowStart(self):
        """
        Returns the rendering settings window-start of this channel

        :return:    Window start
        :rtype:     double
        """

        if self._re is None:
            return None
        return self._re.getChannelWindowStart(
            self._idx, self._conn.SERVICE_OPTS)

    def setWindowStart(self, val):
        self.setWindow(val, self.getWindowEnd())

    def getWindowEnd(self):
        """
        Returns the rendering settings window-end of this channel

        :return:    Window end
        :rtype:     double
        """

        if self._re is None:
            return None
        return self._re.getChannelWindowEnd(
            self._idx, self._conn.SERVICE_OPTS)

    def setWindowEnd(self, val):
        self.setWindow(self.getWindowStart(), val)

    def setWindow(self, minval, maxval):
        self._re.setChannelWindow(
            self._idx, float(minval), float(maxval), self._conn.SERVICE_OPTS)

    def getWindowMin(self):
        """
        Returns the minimum pixel value of the channel

        :return:    Min pixel value
        :rtype:     double
        """
        si = self._obj.getStatsInfo()
        if si is None:
            logger.info("getStatsInfo() is null. See #9695")
            try:
                if self._re is not None:
                    return self._re.getPixelsTypeLowerBound(0)
                else:
                    minVals = {PixelsTypeint8: -128,
                               PixelsTypeuint8: 0,
                               PixelsTypeint16: -32768,
                               PixelsTypeuint16: 0,
                               PixelsTypeint32: -2147483648,
                               PixelsTypeuint32: 0,
                               PixelsTypefloat: -2147483648,
                               PixelsTypedouble: -2147483648}
                    pixtype = self._obj.getPixels(
                        ).getPixelsType().getValue().getValue()
                    return minVals[pixtype]
            except:     # Just in case we don't support pixType above
                return None
        return si.getGlobalMin().val

    def getWindowMax(self):
        """
        Returns the maximum pixel value of the channel

        :return:    Min pixel value
        :rtype:     double
        """
        si = self._obj.getStatsInfo()
        if si is None:
            logger.info("getStatsInfo() is null. See #9695")
            try:
                if self._re is not None:
                    return self._re.getPixelsTypeUpperBound(0)
                else:
                    maxVals = {PixelsTypeint8: 127,
                               PixelsTypeuint8: 255,
                               PixelsTypeint16: 32767,
                               PixelsTypeuint16: 65535,
                               PixelsTypeint32: 2147483647,
                               PixelsTypeuint32: 4294967295,
                               PixelsTypefloat: 2147483647,
                               PixelsTypedouble: 2147483647}
                    pixtype = self._obj.getPixels(
                        ).getPixelsType().getValue().getValue()
                    return maxVals[pixtype]
            except:     # Just in case we don't support pixType above
                return None
        return si.getGlobalMax().val

    def isReverseIntensity(self):
        """Deprecated in 5.4.0. Use isInverted()."""
        warnings.warn("Deprecated. Use isInverted()", DeprecationWarning)
        return self.isInverted()

    def isInverted(self):
        """
        Returns True if this channel has ReverseIntensityContext
        set on it.

        :return:    True if ReverseIntensityContext found
        :rtype:     Boolean
        """
        if self._re is None:
            return None
        ctx = self._re.getCodomainMapContext(self._idx)
        reverse = False
        for c in ctx:
            if isinstance(c, omero.model.ReverseIntensityContext):
                reverse = True
        return reverse

    def getFamily(self):
        """
        Returns the channel family

        :return:    the channel family
        :rtype:     String
        """
        if self._re is None:
            return None

        f = self._re.getChannelFamily(self._idx)
        if f is None:
            return f

        return f.getValue()

    def getCoefficient(self):
        """
        Returns the channel coefficient

        :return:    the channel coefficient
        :rtype:     float
        """
        if self._re is None:
            return None

        return self._re.getChannelCurveCoefficient(self._idx)

ChannelWrapper = _ChannelWrapper


class assert_re (object):
    """
    Function decorator to make sure that rendering engine is prepared before
    call. Is configurable by various options.
    """

    def __init__(self, onPrepareFailureReturnNone=True, ignoreExceptions=None):
        """
        Initialises the decorator.

        :param onPrepareFailureReturnNone: Whether or not on a failure to
        prepare the rendering engine the decorator should return 'None' or
        allow the execution of the decorated function or method. Defaults to
        'True'.
        :type onPrepareFailureReturnNone: Boolean
        :param ignoreExceptions: A set of exceptions thrown during the
        preparation of the rendering engine for which the decorator should
        ignore and allow the execution of the decorated function or method.
        Defaults to 'None'.
        :type ignoreExceptions: Set
        """
        self.onPrepareFailureReturnNone = onPrepareFailureReturnNone
        self.ignoreExceptions = ignoreExceptions

    def __call__(ctx, f):
        """
        Tries to prepare rendering engine, then calls function and return the
        result.
        """

        def wrapped(self, *args, **kwargs):
            try:
                if not self._prepareRenderingEngine() \
                   and ctx.onPrepareFailureReturnNone:
                    logger.debug('Preparation of rendering engine failed, '
                                 'returning None for %r!' % f)
                    return None
            except ctx.ignoreExceptions:
                logger.debug('Ignoring exception thrown during preparation '
                             'of rendering engine for %r!' % f, exc_info=True)
                pass
            return f(self, *args, **kwargs)
        return wrapped


def assert_pixels(func):
    """
    Function decorator to make sure that pixels are loaded before call

    :param func:    Function
    :type func:     Function
    :return:        Decorated function
    :rtype:         Function
    """

    def wrapped(self, *args, **kwargs):
        """ Tries to load pixels, then call function and return the result"""

        if not self._loadPixels():
            return None
        return func(self, *args, **kwargs)
    return wrapped


class _ImageWrapper (BlitzObjectWrapper, OmeroRestrictionWrapper):
    """
    omero_model_ImageI class wrapper extends BlitzObjectWrapper.
    """

    _re = None
    _pd = None
    _rm = {}
    _qf = {}
    _pixels = None
    _archivedFileCount = None
    _filesetFileCount = None
    _importedFilesInfo = None

    _pr = None  # projection
    _prStart = None
    _prEnd = None

    _invertedAxis = False

    PROJECTIONS = {
        'normal': -1,
        'intmax': omero.constants.projection.ProjectionType.MAXIMUMINTENSITY,
        'intmean': omero.constants.projection.ProjectionType.MEANINTENSITY,
        'intsum': omero.constants.projection.ProjectionType.SUMINTENSITY,
        }

    PLANEDEF = omero.romio.XY

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Extend base query to handle filtering of Images by Datasets.
        Returns a tuple of (query, clauses, params).
        Supported opts: 'dataset': <dataset_id> to filter by Dataset
                        'load_pixels': <bool> to load Pixel objects
                        'load_channels': <bool> to load Channels and
                                                    Logical Channels
                        'orphaned': <bool> Images not in Dataset or WellSample

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query, clauses, params = super(
            _ImageWrapper, cls)._getQueryString(opts)
        if opts is not None and 'dataset' in opts:
            query += ' join obj.datasetLinks dlink'
            clauses.append('dlink.parent.id = :did')
            params.add('did', rlong(opts['dataset']))
        load_pixels = False
        load_channels = False
        orphaned = False
        if opts is not None:
            load_pixels = opts.get('load_pixels')
            load_channels = opts.get('load_channels')
            orphaned = opts.get('orphaned')
        if load_pixels or load_channels:
            # We use 'left outer join', since we still want images if no pixels
            query += getPixelsQuery("obj")
        if load_channels:
            query += getChannelsQuery()
        if orphaned:
            clauses.append(
                """
                not exists (
                    select dilink from DatasetImageLink as dilink
                    where dilink.child = obj.id
                )
                """
            )
            clauses.append(
                """
                not exists (
                    select ws from WellSample ws
                    where ws.image.id = obj.id
                )
                """
            )
        return (query, clauses, params)

    @classmethod
    def fromPixelsId(cls, conn, pid):
        """
        Creates a new Image wrapper with the image specified by pixels ID

        :param conn:    The connection
        :type conn:     :class:`BlitzGateway`
        :param pid:     Pixels ID
        :type pid:      Long
        :return:        New Image wrapper
        :rtype:         :class:`ImageWrapper`
        """

        q = conn.getQueryService()
        p = q.find('Pixels', pid, conn.SERVICE_OPTS)
        if p is None:
            return None
        return ImageWrapper(conn, p.image)

    OMERO_CLASS = 'Image'
    LINK_CLASS = None
    CHILD_WRAPPER_CLASS = None
    PARENT_WRAPPER_CLASS = ['DatasetWrapper', 'WellSampleWrapper']
    _thumbInProgress = False

    def __loadedHotSwap__(self):
        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.getDetails().group.id.val)
        self._obj = self._conn.getContainerService().getImages(
            self.OMERO_CLASS, (self._oid,), None, ctx)[0]

    def getAcquisitionDate(self):
        """
        Returns the acquisition date for the image or None if not set.

        :return:    A :meth:`datetime.datetime` object
        :rtype:     datetime
        """

        t = unwrap(self._obj.acquisitionDate)
        if t is not None and t > 0:
            try:
                return datetime.fromtimestamp(t/1000)
            except ValueError:
                return None

    def getInstrument(self):
        """

        Returns the Instrument for this image (or None) making sure the
        instrument is loaded.

        :return:    Instrument (microscope)
        :rtype:     :class:`InstrumentWrapper`
        """

        i = self._obj.instrument
        if i is None:
            return None
        if not i.loaded:
            meta_serv = self._conn.getMetadataService()
            ctx = self._conn.SERVICE_OPTS.copy()
            if ctx.getOmeroGroup() is None:
                ctx.setOmeroGroup(-1)
            i = self._obj.instrument = meta_serv.loadInstrument(i.id.val, ctx)
        return InstrumentWrapper(self._conn, i)

    def _loadPixels(self):
        """
        Checks that pixels are loaded

        :return:    True if loaded
        :rtype:     Boolean
        """

        if not self._obj.pixelsLoaded:
            self.__loadedHotSwap__()
        return self._obj.sizeOfPixels() > 0

    def _getRDef(self):
        """
        Return a rendering def ID based on custom logic.

        :return:            Rendering definition ID or None if no custom
                            logic has found a rendering definition.
        """
        rdefns = self._conn.CONFIG.IMG_RDEFNS
        if rdefns is None:
            return
        ann = self.getAnnotation(rdefns)
        rdid = ann and ann.getValue() or None
        if rdid is None:
            return
        logger.debug('_getRDef: %s, annid=%d' % (str(rdid), ann.getId()))
        logger.debug('now load render options: %s' %
                     str(self._loadRenderOptions()))
        self.loadRenderOptions()
        return rdid

    def _onResetDefaults(self, rdid):
        """
        Called whenever a reset defaults is called by the preparation of
        the rendering engine or the thumbnail bean.

        :param rdid:         Current Rendering Def ID
        :type rdid:          Long
        """
        rdefns = self._conn.CONFIG.IMG_RDEFNS
        if rdefns is None:
            return
        ann = self.getAnnotation(rdefns)
        if ann is None:
            a = LongAnnotationWrapper(self)
            a.setNs(rdefns)
            a.setValue(rdid)
            self.linkAnnotation(a, sameOwner=False)

    def _prepareRE(self, rdid=None):
        """
        Prepare the rendering engine with pixels ID and existing or new
        rendering def.

        :return:            The Rendering Engine service
        :rtype:             :class:`ProxyObjectWrapper`
        """

        pid = self.getPrimaryPixels().id
        re = self._conn.createRenderingEngine()
        ctx = self._conn.SERVICE_OPTS.copy()

        ctx.setOmeroGroup(self.details.group.id.val)
        # if self._conn.canBeAdmin():
        #     ctx.setOmeroUser(self.details.owner.id.val)
        re.lookupPixels(pid, ctx)
        if rdid is None:
            rdid = self._getRDef()
        if rdid is None:
            if not re.lookupRenderingDef(pid, ctx):
                re.resetDefaultSettings(True, ctx)
                re.lookupRenderingDef(pid, ctx)
            self._onResetDefaults(re.getRenderingDefId(ctx))
        else:
            re.loadRenderingDef(rdid, ctx)
        re.load(ctx)
        return re

    def _prepareRenderingEngine(self, rdid=None):
        """
        Checks that the rendering engine is prepared, calling
        :meth:`_prepareRE` if needed.
        Used by the :meth:`assert_re` method to wrap calls requiring rendering
        engine

        :return:    True if rendering engine is created
        :rtype:     Boolean
        """

        self._loadPixels()
        if self._re is None:
            if self._obj.sizeOfPixels() < 1:
                return False
            if self._pd is None:
                self._pd = omero.romio.PlaneDef(self.PLANEDEF)
            try:
                self._re = self._prepareRE(rdid=rdid)
            except omero.ValidationException:
                logger.debug('on _prepareRE()', exc_info=True)
                self._closeRE()
        return self._re is not None

    def resetRDefs(self):
        logger.debug('resetRDefs')
        if self.canAnnotate():
            self._deleteSettings()
            rdefns = self._conn.CONFIG.IMG_RDEFNS
            logger.debug(rdefns)
            if rdefns:
                # Use the same group as the image in the context
                ctx = self._conn.SERVICE_OPTS.copy()
                self._conn.SERVICE_OPTS.setOmeroGroup(
                    self.details.group.id.val)
                try:
                    self.removeAnnotations(rdefns)
                finally:
                    self._conn.SERVICE_OPTS = ctx
            return True
        return False

    def simpleMarshal(self, xtra=None, parents=False):
        """
        Creates a dict representation of the Image, including author and date
        info.

        :param xtra: controls the optional parts of simpleMarshal;
                     - thumbUrlPrefix - allows customizing the thumb URL by
                     either a static string prefix or a callable function
                     that will take a single ImgId int argument and return the
                     customized URL string
                     - tiled - if passed and value evaluates to true, add
                     information on whether this image is tiled on this server.
        :type: Dict
        :return:    Dict
        :rtype:     Dict
        """

        rv = super(_ImageWrapper, self).simpleMarshal(
            xtra=xtra, parents=parents)
        rv.update({'author': self.getAuthor(),
                   'date': time.mktime(self.getDate().timetuple()), })
        if xtra:
            if 'thumbUrlPrefix' in xtra:
                if callable(xtra['thumbUrlPrefix']):
                    rv['thumb_url'] = xtra['thumbUrlPrefix'](str(self.id))
                else:
                    rv['thumb_url'] = xtra[
                        'thumbUrlPrefix'] + str(self.id) + '/'
            if xtra.get('tiled', False):
                # Since we need to calculate sizes, store them too in the
                # marshaled value
                maxplanesize = self._conn.getMaxPlaneSize()
                rv['size'] = {'width': self.getSizeX(),
                              'height': self.getSizeY(),
                              }
                if rv['size']['height'] and rv['size']['width']:
                    rv['tiled'] = ((rv['size']['height'] *
                                    rv['size']['width']) >
                                   (maxplanesize[0] * maxplanesize[1]))
                else:
                    rv['tiled'] = False

        return rv

    def getStageLabel(self):
        """
        Returns the stage label or None

        :return:    Stage label
        :rtype:     :class:`ImageStageLabelWrapper`
        """

        if self._obj.stageLabel is None:
            return None
        else:
            return ImageStageLabelWrapper(self._conn, self._obj.stageLabel)

    def shortname(self, length=20, hist=5):
        """
        Provides a truncated name of the image.
        E.g. ...catedNameOfTheImage.tiff

        :param length:  The ideal length to return.
                        If truncated, will be ...length
        :type length:   Int
        :param hist:    The amount of leeway allowed before truncation
                        (avoid truncating 1 or 2 letters)
        :type hist:     Int
        :return:        Truncated ...name
        :type:          String
        """

        name = self.name
        if not name:
            return ""
        l = len(name)
        if l < length+hist:
            return name
        return "..." + name[l - length:]

    def getAuthor(self):
        """
        Returns 'Firstname Lastname' of image owner

        :return:    Image owner
        :rtype:     String
        """

        q = self._conn.getQueryService()
        e = q.findByQuery(
            "select e from Experimenter e where e.id = %i"
            % self._obj.details.owner.id.val, None, self._conn.SERVICE_OPTS)
        self._author = e.firstName.val + " " + e.lastName.val
        return self._author

    def getProject(self):
        """
        Gets the Project that image is in, or None.
        TODO: Assumes image is in only 1 Project.
        Why not use getAncestory()[-1]
        Returns None if Image is in more than one Dataset & Project.

        :return:    Project
        :rtype:     :class:`ProjectWrapper`
        """

        try:
            q = ("select p from Image i join i.datasetLinks dl "
                 "join dl.parent ds join ds.projectLinks pl "
                 "join pl.parent p where i.id = %i"
                 % self._obj.id.val)
            query = self._conn.getQueryService()
            prj = query.findAllByQuery(q, None, self._conn.SERVICE_OPTS)
            if prj and len(prj) == 1:
                return ProjectWrapper(self._conn, prj[0])
        except:  # pragma: no cover
            logger.debug('on getProject')
            logger.debug(traceback.format_exc())
            return None

    def getPlate(self):
        """
        If the image is in a Plate/Well hierarchy, returns the parent Plate,
        otherwise None

        :return:    Plate
        :rtype:     :class:`PlateWrapper`
        """

        params = omero.sys.Parameters()
        params.map = {}
        params.map["oid"] = omero.rtypes.rlong(self.getId())
        query = ("select well from Well as well "
                 "join fetch well.details.creationEvent "
                 "join fetch well.details.owner "
                 "join fetch well.details.group "
                 "join fetch well.plate as pt "
                 "left outer join fetch well.wellSamples as ws "
                 "left outer join fetch ws.image as img "
                 "where ws.image.id = :oid")
        q = self._conn.getQueryService()
        for well in q.findAllByQuery(query, params):
            return PlateWrapper(self._conn, well.plate)

    def getObjectiveSettings(self):
        """
        Gets the Objective Settings of the Image, or None

        :return:    Objective Settings
        :rtype:     :class:`ObjectiveSettingsWrapper`
        """

        rv = self.objectiveSettings
        if self.objectiveSettings is not None:
            rv = ObjectiveSettingsWrapper(self._conn, self.objectiveSettings)
            if not self.objectiveSettings.loaded:
                self.objectiveSettings = rv._obj
        return rv

    def getImagingEnvironment(self):
        """
        Gets the Imaging Environment of the Image, or None

        :return:    Imaging Environment
        :rtype:     :class:`ImagingEnvironmentWrapper`
        """

        rv = self.imagingEnvironment
        if self.imagingEnvironment is not None:
            rv = ImagingEnvironmentWrapper(self._conn, self.imagingEnvironment)
            if not self.imagingEnvironment.loaded:
                self.imagingEnvironment = rv._obj
        return rv

    @assert_pixels
    def getPixelsId(self):
        """
        Returns the Primary Pixels ID for the image.

        :return:    Pixels ID
        :rtype:     Long
        """

        return self._obj.getPrimaryPixels().getId().val

    # @setsessiongroup
    def _prepareTB(self, _r=False, rdefId=None):
        """
        Prepares Thumbnail Store for the image.

        :param _r:          If True, don't reset default rendering
                            (return None if no rDef exists)
        :type _r:           Boolean
        :param rdefId:      Rendering def ID to use for rendering thumbnail
        :type rdefId:       Long
        :return:            Thumbnail Store or None
        :rtype:             :class:`ProxyObjectWrapper`
        """

        pid = self.getPrimaryPixels().id
        if rdefId is None:
            rdefId = self._getRDef()
        tb = self._conn.createThumbnailStore()

        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.details.group.id.val)
        has_rendering_settings = tb.setPixelsId(pid, ctx)
        logger.debug("tb.setPixelsId(%d) = %s " %
                     (pid, str(has_rendering_settings)))
        if rdefId is not None:
            try:
                tb.setRenderingDefId(rdefId, ctx)
            except omero.ValidationException:
                # The annotation exists, but not the rendering def?
                logger.error(
                    'IMG %d, defrdef == %d but object does not exist?'
                    % (self.getId(), rdefId))
                rdefId = None
        if rdefId is None:
            if not has_rendering_settings:
                if self._conn.canBeAdmin():
                    ctx.setOmeroUser(self.details.owner.id.val)
                try:
                    # E.g. May throw Missing Pyramid Exception
                    tb.resetDefaults(ctx)
                except omero.ConcurrencyException, ce:
                    logger.info(
                        "ConcurrencyException: resetDefaults() failed "
                        "in _prepareTB with backOff: %s" % ce.backOff)
                    return tb
                tb.setPixelsId(pid, ctx)
                try:
                    rdefId = tb.getRenderingDefId(ctx)
                # E.g. No rendering def (because of missing pyramid!)
                except omero.ApiUsageException:
                    logger.info(
                        "ApiUsageException: getRenderingDefId() failed "
                        "in _prepareTB")
                    return tb
                self._onResetDefaults(rdefId)
        return tb

    def loadOriginalMetadata(self, sort=True):
        """
        Gets original metadata from the file annotation.
        Returns the File Annotation, list of Global Metadata,
        list of Series Metadata in a tuple.
        Metadata lists are lists of (key, value) tuples.

        :param sort:    If True, we sort Metadata by key
        :return:    Tuple (file-annotation, global-metadata, series-metadata)
        :rtype:     Tuple (:class:`FileAnnotationWrapper`, [], [])
        """

        req = omero.cmd.OriginalMetadataRequest()
        req.imageId = self.id

        handle = self._conn.c.sf.submit(req)
        try:
            cb = self._conn._waitOnCmd(handle, failontimeout=True)
            rsp = cb.getResponse()
        finally:
            handle.close()

        global_metadata = list()
        series_metadata = list()

        for l, m in ((global_metadata, rsp.globalMetadata),
                     (series_metadata, rsp.seriesMetadata)):

            for k, v in m.items():
                l.append((k, unwrap(v)))  # was RType!

        if sort:
            global_metadata.sort(key=lambda x: x[0].lower())
            series_metadata.sort(key=lambda x: x[0].lower())
        return (None, (global_metadata), (series_metadata))

    @assert_re()
    def _getProjectedThumbnail(self, size, pos):
        """
        Returns a string holding a rendered JPEG of the projected image, sized
        to mimic a thumbnail. This is an 'internal' method of this class, used
        to generate a thumbnail from a full-sized projected image (since
        thumbnails don't support projection). SetProjection should be called
        before this method is called, so that this returns a projected, scaled
        image.

        :param size:    The length of the longest size, in a list or tuple.
                        E.g. (100,)
        :type size:     list or tuple
        :param pos:     The (z, t) position
        :type pos:      Tuple (z,t)
        """

        if pos is None:
            t = z = 0
        else:
            z, t = pos
        img = self.renderImage(z, t)
        if len(size) == 1:
            w = self.getSizeX()
            h = self.getSizeY()
            ratio = float(w) / h
            if ratio > 1:
                h = h * size[0] / w
                w = size[0]
            else:
                w = w * size[0] / h
                h = size[0]
        elif len(size) == 2:
            w, h = size
        img = img.resize((w, h), Image.NEAREST)
        rv = StringIO()
        img.save(rv, 'jpeg', quality=70)
        return rv.getvalue()

    # @setsessiongroup
    def getThumbnail(self, size=(64, 64), z=None, t=None, direct=True,
                     rdefId=None):
        """
        Returns a string holding a rendered JPEG of the thumbnail.

        :type size:         tuple or number
        :param size:        A tuple with one or two ints, or an integer.
                            If a tuple holding a single int, or a single int is
                            passed as param, then that will be used as the
                            longest size on the rendered thumb, and image
                            aspect ratio is kept.
                            If two ints are passed in a tuple, they set the
                            width and height of the rendered thumb.
        :type z:            number
        :param z:           the Z position to use for rendering the thumbnail.
                            If not provided default is used.
        :type t:            number
        :param t:           the T position to use for rendering the thumbnail.
                            If not provided default is used.
        :param direct:      If true, force creation of new thumbnail
                            (don't use cached)
        :param rdefId:      The rendering def to apply to the thumbnail.
        :rtype:             string or None
        :return:            the rendered JPEG, or None if there was an error.
        """
        tb = None
        try:
            tb = self._prepareTB(rdefId=rdefId)
            if tb is None:
                return None
            if isinstance(size, IntType):
                size = (size,)
            if z is not None or t is not None:
                if z is None:
                    z = self.getDefaultZ()
                if t is None:
                    t = self.getDefaultT()
                pos = z, t
            else:
                pos = None
                # The following was commented out in the context of
                # omero:#5191. Preparing the rendering engine has the
                # potential to cause the raising of ConcurrencyException's
                # which prevent OMERO.web from executing the thumbnail methods
                # below and consequently showing "in-progress" thumbnails.
                # Tue 24 May 2011 10:42:47 BST -- cxallan
                # re = self._prepareRE()
                # if re:
                #     if z is None:
                #         z = re.getDefaultZ()
                #     if t is None:
                #         t = re.getDefaultT()
                #     pos = z,t
                # else:
                #     pos = None
            if self.getProjection() != 'normal':
                return self._getProjectedThumbnail(size, pos)
            if len(size) == 1:
                if pos is None:
                    if direct:
                        thumb = tb.getThumbnailByLongestSideDirect
                    else:
                        thumb = tb.getThumbnailByLongestSide
                else:
                    thumb = tb.getThumbnailForSectionByLongestSideDirect
            else:
                if pos is None:
                    if direct:
                        thumb = tb.getThumbnailDirect
                    else:
                        thumb = tb.getThumbnail
                else:
                    thumb = tb.getThumbnailForSectionDirect
            args = map(lambda x: rint(x), size)
            if pos is not None:
                args = list(pos) + args
            ctx = self._conn.SERVICE_OPTS.copy()
            ctx.setOmeroGroup(self.details.group.id.val)
            args += [ctx]
            rv = thumb(*args)
            self._thumbInProgress = tb.isInProgress()
            return rv
        except Exception:  # pragma: no cover
            logger.error(traceback.format_exc())
            return None
        finally:
            if tb is not None:
                tb.close()

    @assert_pixels
    def getPixelRange(self):
        """
        Returns (min, max) values for the pixels type of this image.
        TODO: Does not handle floats correctly, though.

        :return:    Tuple (min, max)
        """

        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        try:
            rp.setPixelsId(pixels_id, True, self._conn.SERVICE_OPTS)
            pmax = 2 ** (8 * rp.getByteWidth())
            if rp.isSigned():
                return (-(pmax / 2), pmax / 2 - 1)
            else:
                return (0, pmax-1)
        finally:
            rp.close()

    @assert_pixels
    def getPrimaryPixels(self):
        """
        Loads pixels and returns object in a :class:`PixelsWrapper`
        """
        return PixelsWrapper(self._conn, self._obj.getPrimaryPixels())

    @assert_pixels
    def getThumbVersion(self):
        """
        Return the version of (latest) thumbnail owned by current user,
        or None if no thumbnail exists

        :return:        Long or None
        """
        eid = self._conn.getUserId()
        if self._obj.getPrimaryPixels()._thumbnailsLoaded:
            tvs = [t.version.val
                   for t in self._obj.getPrimaryPixels().copyThumbnails()
                   if t.getDetails().owner.id.val == eid]
        else:
            pid = self.getPixelsId()
            params = omero.sys.ParametersI()
            params.addLong('pid', pid)
            params.addLong('ownerId', eid)
            query = ("select t.version from Thumbnail t "
                     "where t.pixels.id = :pid "
                     "and t.details.owner.id = :ownerId")
            tbs = self._conn.getQueryService().projection(
                query, params, self._conn.SERVICE_OPTS)
            tvs = [t[0].val for t in tbs]
        if len(tvs) > 0:
            return max(tvs)
        return None

    def getChannels(self, noRE=False):
        """
        Returns a list of Channels, each initialised with rendering engine.
        If noRE is True, Channels will not have rendering engine enabled.
        In this case, calling channel.getColor() or getWindowStart() etc
        will return None.

        :return:    Channels
        :rtype:     List of :class:`ChannelWrapper`
        """
        if not noRE:
            try:
                if not self._prepareRenderingEngine():
                    return None
            except omero.ConcurrencyException:
                logger.debug('Ignoring exception thrown during '
                             '_prepareRenderingEngine '
                             'for getChannels()', exc_info=True)

            if self._re is not None:
                return [ChannelWrapper(self._conn, c, idx=n,
                                       re=self._re, img=self)
                        for n, c in enumerate(
                            self._re.getPixels(
                                self._conn.SERVICE_OPTS).iterateChannels())]

        # If we have silently failed to load rendering engine
        # E.g. ConcurrencyException OR noRE is True,
        # load channels by hand, use pixels to order channels
        pid = self.getPixelsId()
        params = omero.sys.Parameters()
        params.map = {"pid": rlong(pid)}
        query = ("select p from Pixels p join fetch p.channels as c "
                 "join fetch c.logicalChannel as lc where p.id=:pid")
        pixels = self._conn.getQueryService().findByQuery(
            query, params, self._conn.SERVICE_OPTS)
        return [ChannelWrapper(self._conn, c, idx=n, re=self._re, img=self)
                for n, c in enumerate(pixels.iterateChannels())]

    def getChannelLabels(self):
        """
        Returns a list of the labels for the Channels for this image
        """
        q = self._conn.getQueryService()
        params = omero.sys.ParametersI()
        params.addId(self.getId())
        query = "select lc.name, lc.emissionWave.value, index(chan) "\
                "from Pixels p "\
                "join p.image as img "\
                "join p.channels as chan "\
                "join chan.logicalChannel as lc "\
                "where img.id = :id order by index(chan)"
        res = q.projection(query, params, self._conn.SERVICE_OPTS)
        ret = []
        for name, emissionWave, idx in res:
            if name is not None and len(name.val.strip()) > 0:
                ret.append(name.val)
            elif emissionWave is not None and\
                    len(unicode(emissionWave.val).strip()) > 0:
                # FIXME: units ignored for wavelength
                rv = emissionWave.getValue()
                # Don't show as double if it's really an int
                if int(rv) == rv:
                    rv = int(rv)
                ret.append(unicode(rv))
            else:
                ret.append(unicode(idx.val))
        return ret

    @assert_re()
    def getZoomLevelScaling(self):
        """
        Returns a dict of zoomLevels:scale (fraction) for tiled 'Big' images.
        eg {0: 1.0, 1: 0.25, 2: 0.062489446727078291, 3: 0.031237687848258006}
        Returns None if this image doesn't support tiles.
        """
        if not self._re.requiresPixelsPyramid():
            return None
        levels = self._re.getResolutionDescriptions()
        rv = {}
        sizeXList = [level.sizeX for level in levels]
        for i, level in enumerate(sizeXList):
            rv[i] = float(level)/sizeXList[0]
        return rv

    @assert_re()
    def set_active_channels(self, channels, windows=None, colors=None,
                            invertMaps=None, reverseMaps=None, noRE=False):
        """
        Sets the active channels on the rendering engine.
        Also sets rendering windows and channel colors
        (for channels that are active)

        Examples:
        # Turn first channel ON, others OFF
        image.setActiveChannels([1])
        # First OFF, second ON, windows and colors for both
        image.setActiveChannels(
            [-1, 2], [[20, 300], [50, 500]], ['00FF00', 'FF0000'])
        # Second Channel ON with windows. All others OFF
        image.setActiveChannels([2], [[20, 300]])

        :param channels:    List of active channel indexes ** 1-based index **
        :type channels:     List of int
        :param windows:     Start and stop values for active channel rendering
                            settings
        :type windows:      List of [start, stop].
                            [[20, 300], [None, None], [50, 500]].
                            Must be list for each channel
        :param colors:      List of colors. ['F00', None, '00FF00'].
                            Must be item for each channel
        :param invertMaps:  List of boolean (or None). If True/False then
                            set/remove reverseIntensityMap on channel
        :param noRE:        If True Channels will not have rendering engine
                            enabled. In this case, calling channel.getColor()
                            or getWindowStart() etc. will return None.
        """
        if reverseMaps is not None:
            warnings.warn(
                "setActiveChannels() reverseMaps parameter"
                "deprecated in OMERO 5.4.0. Use invertMaps",
                DeprecationWarning)
            if invertMaps is None:
                invertMaps = reverseMaps
        abs_channels = [abs(c) for c in channels]
        idx = 0     # index of windows/colors args above
        for c in range(len(self.getChannels(noRE=noRE))):
            self._re.setActive(c, (c+1) in channels, self._conn.SERVICE_OPTS)
            if (c+1) in channels:
                if (invertMaps is not None and
                        invertMaps[idx] is not None):
                    self.setReverseIntensity(c, invertMaps[idx])
                if (windows is not None and
                        windows[idx][0] is not None and
                        windows[idx][1] is not None):
                    self._re.setChannelWindow(
                        c, float(windows[idx][0]), float(windows[idx][1]),
                        self._conn.SERVICE_OPTS)
                if colors is not None and colors[idx]:
                    if colors[idx].endswith('.lut'):
                        self._re.setChannelLookupTable(c, colors[idx])
                    else:
                        rgba = splitHTMLColor(colors[idx])
                        if rgba:
                            self._re.setRGBA(
                                c, *(rgba + [self._conn.SERVICE_OPTS]))
                            # disable LUT
                            self._re.setChannelLookupTable(c, None)
            if (c+1 in abs_channels):
                idx += 1
        return True

    @assert_re()
    def setActiveChannels(self, channels, windows=None, colors=None,
                          invertMaps=None, reverseMaps=None):
        warnings.warn("setActiveChannels() is deprecated in OMERO 5.4.0."
                      "Use set_active_channels", DeprecationWarning)
        return self.set_active_channels(channels, windows, colors,
                                        invertMaps, reverseMaps, False)

    def getProjections(self):
        """
        Returns list of available keys for projection.
        E.g. ['intmax', 'intmean']

        :return:    Projection options
        :rtype:     List of strings
        """

        return self.PROJECTIONS.keys()

    def getProjection(self):
        """
        Returns the current projection option (checking it is valid).

        :return:    Projection key. E.g. 'intmax'
        :rtype:     String
        """

        if self._pr in self.PROJECTIONS.keys():
            return self._pr
        return 'normal'

    def setProjection(self, proj):
        """
        Sets the current projection option.

        :param proj:    Projection Option. E.g. 'intmax' or 'normal'
        :type proj:     String
        """

        self._pr = proj

    def getProjectionRange(self):
        """
        Gets the range used for Z-projection as tuple (proStart, proEnd)
        """
        return (self._prStart, self._prEnd)

    def setProjectionRange(self, projStart, projEnd):
        """
        Sets the range used for Z-projection. Will only be used
        if E.g. setProjection('intmax') is not 'normal'
        """
        if projStart is not None:
            projStart = max(0, int(projStart))
        if projEnd is not None:
            projEnd = min(int(projEnd), self.getSizeZ()-1)
        self._prStart = projStart
        self._prEnd = projEnd

    def isInvertedAxis(self):
        """
        Returns the inverted axis flag

        :return:    Inverted Axis
        :rtype:     Boolean
        """

        return self._invertedAxis

    def setInvertedAxis(self, inverted):
        """
        Sets the inverted axis flag

        :param inverted:    Inverted Axis
        :type inverted:     Boolean
        """

        self._invertedAxis = inverted

    LINE_PLOT_DTYPES = {
        (4, True, True): 'f',  # signed float
        (2, False, False): 'H',  # unsigned short
        (2, False, True): 'h',  # signed short
        (1, False, False): 'B',  # unsigned char
        (1, False, True): 'b',  # signed char
        }

    @assert_pixels
    def getHistogram(self, channels, binCount, globalRange=True,
                     theZ=0, theT=0):
        """
        Get pixel intensity histogram of a single plane for specified channels.

        Returns a map of channelIndex: integer list.
        If globalRange is True, use the min/max for that channel over ALL
        planes.
        If False, use the pixel intensity range for the specified plane.

        :param channels:        List of channel integers we want
        :param binCount:        Number of bins in the histogram
        :param globalRange:     If false, use min/max intensity for this plane
        :param theZ:            Z index of plane
        :param theT:            T index of plane
        :return:                Dict of channelIndex: integer list
        """

        pixels_id = self.getPixelsId()
        rp = self._conn.createRawPixelsStore()
        try:
            rp.setPixelsId(pixels_id, True, self._conn.SERVICE_OPTS)
            plane = omero.romio.PlaneDef(self.PLANEDEF)
            plane.z = long(theZ)
            plane.t = long(theT)
            histogram = rp.getHistogram(channels, binCount, globalRange, plane)
            return histogram
        finally:
            rp.close()

    def getPixelLine(self, z, t, pos, axis, channels=None, range=None):
        """
        Grab a horizontal or vertical line from the image pixel data, for the
        specified channels (or 'active' if not specified) and using the
        specified range (or 1:1 relative to the image size). Axis may be 'h'
        or 'v', for horizontal or vertical respectively.

        :param z:           Z index
        :param t:           T index
        :param pos:         X or Y position
        :param axis:        Axis 'h' or 'v'
        :param channels:    map of {index: :class:`ChannelWrapper` }
        :param range:       height of scale
                            (use image height (or width) by default)
        :return: rv         List of lists (one per channel)
        """

        if not self._loadPixels():
            logger.debug("No pixels!")
            return None
        axis = axis.lower()[:1]
        if channels is None:
            channels = map(
                lambda x: x._idx, filter(
                    lambda x: x.isActive(), self.getChannels()))
        if range is None:
            range = axis == 'h' and self.getSizeY() or self.getSizeX()
        if not isinstance(channels, (TupleType, ListType)):
            channels = (channels,)
        chw = map(
            lambda x: (x.getWindowMin(), x.getWindowMax()), self.getChannels())
        rv = []
        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        try:
            rp.setPixelsId(pixels_id, True, self._conn.SERVICE_OPTS)
            for c in channels:
                bw = rp.getByteWidth()
                key = self.LINE_PLOT_DTYPES.get(
                    (bw, rp.isFloat(), rp.isSigned()), None)
                if key is None:
                    logger.error(
                        "Unknown data type: " +
                        str((bw, rp.isFloat(), rp.isSigned())))
                plot = array.array(key, (axis == 'h' and
                                   rp.getRow(pos, z, c, t) or
                                   rp.getCol(pos, z, c, t)))
                plot.byteswap()  # TODO: Assuming ours is a little endian
                # system now move data into the windowMin..windowMax range
                offset = -chw[c][0]
                if offset != 0:
                    plot = map(lambda x: x+offset, plot)
                try:
                    normalize = 1.0/chw[c][1]*(range-1)
                except ZeroDivisionError:
                    # This channel has zero sized window, no plot here
                    continue
                if normalize != 1.0:
                    plot = map(lambda x: x*normalize, plot)
                if isinstance(plot, array.array):
                    plot = plot.tolist()
                rv.append(plot)
            return rv
        finally:
            rp.close()

    def getRow(self, z, t, y, channels=None, range=None):
        """
        Grab a horizontal line from the image pixel data,
        for the specified channels (or active ones)

        :param z:           Z index
        :param t:           T index
        :param y:           Y position of row
        :param channels:    map of {index: :class:`ChannelWrapper` }
        :param range:       height of scale (use image height by default)
        :return: rv         List of lists (one per channel)
        """

        return self.getPixelLine(z, t, y, 'h', channels, range)

    def getCol(self, z, t, x, channels=None, range=None):
        """
        Grab a horizontal line from the image pixel data,
        for the specified channels (or active ones)

        :param z:           Z index
        :param t:           T index
        :param x:           X position of column
        :param channels:    map of {index: :class:`ChannelWrapper` }
        :param range:       height of scale (use image width by default)
        :return: rv         List of lists (one per channel)
        """

        return self.getPixelLine(z, t, x, 'v', channels, range)

    def getRenderingModels(self):
        """
        Gets a list of available rendering models.

        :return:    Rendering models
        :rtype:     List of :class:`BlitzObjectWrapper`
        """

        if not len(self._rm):
            for m in self._conn.getEnumerationEntries('RenderingModel'):
                self._rm[m.value] = m
        return self._rm.values()

    @assert_re()
    def getRenderingModel(self):
        """
        Get the current rendering model.

        :return:    Rendering model
        :rtype:     :class:`BlitzObjectWrapper`
        """

        return BlitzObjectWrapper(self._conn, self._re.getModel())

    @assert_re()
    def setGreyscaleRenderingModel(self):
        """
        Sets the Greyscale rendering model on this image's current renderer
        """

        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('greyscale', rm[0])._obj)

    @assert_re()
    def setColorRenderingModel(self):
        """
        Sets the HSB rendering model on this image's current renderer
        """

        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('rgb', rm[0])._obj)

    def isGreyscaleRenderingModel(self):
        """
        Returns True if the current rendering model is 'greyscale'

        :return:    isGreyscale
        :rtype:     Boolean
        """
        return self.getRenderingModel().value.lower() == 'greyscale'

    @assert_re()
    def setReverseIntensity(self, channelIndex, reverse=True):
        """Deprecated in 5.4.0. Use setChannelInverted()."""
        warnings.warn("Deprecated in 5.4.0. Use setChannelInverted()",
                      DeprecationWarning)
        self.setChannelInverted(channelIndex, reverse)

    @assert_re()
    def setChannelInverted(self, channelIndex, inverted=True):
        """
        Sets or removes a ReverseIntensityMapContext from the
        specified channel. If set, the intensity of the channel
        is inverted: brightest -> darkest.

        :param channelIndex:    The index of channel (int)
        :param inverted:        If True, set inverted (boolean)
        """
        r = omero.romio.ReverseIntensityMapContext()
        # Always remove map from channel
        # (doesn't throw exception, even if not on channel)
        self._re.removeCodomainMapFromChannel(r, channelIndex)
        # If we want to invert, add it to the channel (again)
        if inverted:
            self._re.addCodomainMapToChannel(r, channelIndex)

    def getFamilies(self):
        """
        Gets a dict of available families.

        :return:    Families
        :rtype:     Dict
        """
        if not len(self._qf):
            for f in self._conn.getEnumerationEntries('Family'):
                self._qf[f.value] = f
        return self._qf

    @assert_re()
    def setQuantizationMap(self, channelIndex, family, coefficient):
        """
        Sets the quantization strategy to the given family
        and coefficient

        :param channelIndex:    The index of channel (int)
        :param family:          The family (string)
        :param coefficient:     The coefficient (float)
        """
        f = self.getFamilies().get(family)
        self._re.setQuantizationMap(channelIndex, f._obj, coefficient, False)

    @assert_re()
    def setQuantizationMaps(self, maps):
        """
        Sets the quantization strategy using the given list
        of mapping information (for each entry, i.e. channel)
        e.g. [{'family': 'linear', coefficient: 1.0}]

        :param maps:     list of quantization settings
        """
        if not isinstance(maps, list):
            return

        for i, m in enumerate(maps):
            if isinstance(m, dict):
                family = m.get('family', None)
                coefficient = m.get('coefficient', 1.0)
                self.setQuantizationMap(i, family, coefficient)

    @assert_re(ignoreExceptions=(omero.ConcurrencyException))
    def getRenderingDefId(self):
        """
        Returns the ID of the current rendering def on the image.
        Loads and initialises the rendering engine if needed.
        If rendering engine fails (E.g. MissingPyramidException)
        then returns None.

        :return:    current rendering def ID
        :rtype:     Long
        """
        if self._re is not None:
            return self._re.getRenderingDefId()

    def getAllRenderingDefs(self, eid=-1):
        """
        Returns a dict of the rendering settings that exist for this Image
        Can be filtered by owner using the eid parameter.

        :return:    Rdef dict
        :rtype:     Dict
        """

        rv = []
        pixelsId = self.getPixelsId()
        if pixelsId is None:
            return rv
        pixelsService = self._conn.getPixelsService()
        rdefs = pixelsService.retrieveAllRndSettings(
            pixelsId, eid, self._conn.SERVICE_OPTS)
        for rdef in rdefs:
            d = {}
            owner = rdef.getDetails().owner
            d['id'] = rdef.getId().val
            d['owner'] = {'id': owner.id.val,
                          'firstName': owner.getFirstName().val,
                          'lastName': owner.getLastName().val}
            d['z'] = rdef.getDefaultZ().val
            d['t'] = rdef.getDefaultT().val
            # greyscale / rgb
            d['model'] = rdef.getModel().getValue().val
            waves = rdef.iterateWaveRendering()
            d['c'] = []
            for w in waves:
                reverse = False
                for c in w.copySpatialDomainEnhancement():
                    if isinstance(c, omero.model.ReverseIntensityContext):
                        reverse = True
                color = ColorHolder.fromRGBA(
                    w.getRed().val, w.getGreen().val, w.getBlue().val, 255)
                r = {
                    'active': w.getActive().val,
                    'start': w.getInputStart().val,
                    'end': w.getInputEnd().val,
                    'color': color.getHtml(),
                    # 'reverseIntensity' is deprecated. Use 'inverted'
                    'inverted': reverse,
                    'reverseIntensity': reverse,
                    'family': unwrap(w.getFamily().getValue()),
                    'coefficient': unwrap(w.getCoefficient()),
                    'rgb': {'red': w.getRed().val,
                            'green': w.getGreen().val,
                            'blue': w.getBlue().val}
                    }
                lut = unwrap(w.getLookupTable())
                if lut is not None and len(lut) > 0:
                    r['lut'] = lut
                d['c'].append(r)
            rv.append(d)
        return rv

    @assert_re()
    def renderBirdsEyeView(self, size):
        """
        Returns the data from rendering the bird's eye view of the image.

        :param size:   Maximum size of the longest side of
                       the resulting bird's eye view.
        :return:       Data containing a bird's eye view jpeg
        """
        # Prepare the rendering engine parameters on the ImageWrapper.
        re = self._prepareRE()
        try:
            z = re.getDefaultZ()
            t = re.getDefaultT()
            x = 0
            y = 0
            size_x = self.getSizeX()
            size_y = self.getSizeY()
            tile_width, tile_height = re.getTileSize()
            tiles_wide = math.ceil(float(size_x) / tile_width)
            tiles_high = math.ceil(float(size_y) / tile_height)
            # Since the JPEG 2000 algorithm is iterative and rounds pixel
            # counts at each resolution level we're doing the resulting tile
            # size calculations in a loop. Also, since the image is physically
            # tiled the resulting size is a multiple of the tile size and not
            # the iterative quotient of a 2**(resolutionLevels - 1).
            for i in range(1, re.getResolutionLevels()):
                tile_width = round(tile_width / 2.0)
                tile_height = round(tile_height / 2.0)
            width = int(tiles_wide * tile_width)
            height = int(tiles_high * tile_height)
            jpeg_data = self.renderJpegRegion(
                z, t, x, y, width, height, level=0)
            if size is None:
                return jpeg_data
            # We've been asked to scale the image by its longest side so we'll
            # perform that operation until the server has the capability of
            # doing so.
            ratio = float(size) / max(width, height)
            if width > height:
                size = (int(size), int(height * ratio))
            else:
                size = (int(width * ratio), int(size))
            jpeg_data = Image.open(StringIO(jpeg_data))
            jpeg_data.thumbnail(size, Image.ANTIALIAS)
            ImageDraw.Draw(jpeg_data)
            f = StringIO()
            jpeg_data.save(f, "JPEG")
            f.seek(0)
            return f.read()
        finally:
            re.close()

    @assert_re()
    def renderJpegRegion(self, z, t, x, y, width, height, level=None,
                         compression=0.9):
        """
        Return the data from rendering a region of an image plane.
        NB. Projection not supported by the API currently.

        :param z:               The Z index. Ignored if projecting image.
        :param t:               The T index.
        :param x:               The x coordinate of region (int)
        :param y:               The y coordinate of region (int)
        :param width:           The width of region (int)
        :param height:          The height of region (int)
        :param compression:     Compression level for jpeg
        :type compression:      Float
        """

        self._pd.z = long(z)
        self._pd.t = long(t)

        regionDef = omero.romio.RegionDef()
        regionDef.x = int(x)
        regionDef.y = int(y)
        regionDef.width = int(width)
        regionDef.height = int(height)
        self._pd.region = regionDef
        try:
            if level is not None:
                self._re.setResolutionLevel(level)
            if compression is not None:
                try:
                    self._re.setCompressionLevel(float(compression))
                except omero.SecurityViolation:  # pragma: no cover
                    self._obj.clearPixels()
                    self._obj.pixelsLoaded = False
                    self._closeRE()
                    return self.renderJpeg(z, t, None)
            rv = self._re.renderCompressed(self._pd, self._conn.SERVICE_OPTS)
            return rv
        except (omero.ApiUsageException, omero.InternalException):
            logger.debug('On renderJpegRegion', exc_info=True)
            return None
        except Ice.MemoryLimitException:  # pragma: no cover
            # Make sure renderCompressed isn't called again on this re,
            # as it hangs
            self._obj.clearPixels()
            self._obj.pixelsLoaded = False
            self._closeRE()
            raise

    def _closeRE(self):
        try:
            if self._re is not None:
                self._re.close()
        except Exception, e:
            logger.warn("Failed to close " + self._re)
            logger.debug(e)
        finally:
            self._re = None  # This should be the ONLY location to null _re!

    @assert_re()
    def renderJpeg(self, z=None, t=None, compression=0.9):
        """
        Return the data from rendering image, compressed (and projected).
        Projection (or not) is specified by calling :meth:`setProjection`
        before renderJpeg.

        :param z:               The Z index. Ignored if projecting image.
                                If None, use defaultZ
        :param t:               The T index. If None, use defaultT
        :param compression:     Compression level for jpeg
        :type compression:      Float
        """

        if z is None:
            z = self._re.getDefaultZ()
        self._pd.z = long(z)
        if t is None:
            t = self._re.getDefaultT()
        self._pd.t = long(t)
        try:
            if compression is not None:
                try:
                    self._re.setCompressionLevel(float(compression))
                except omero.SecurityViolation:  # pragma: no cover
                    self._obj.clearPixels()
                    self._obj.pixelsLoaded = False
                    self._closeRE()
                    return self.renderJpeg(z, t, None)
            projection = self.PROJECTIONS.get(self._pr, -1)
            if not isinstance(
                    projection, omero.constants.projection.ProjectionType):
                rv = self._re.renderCompressed(
                    self._pd, self._conn.SERVICE_OPTS)
            else:
                prStart, prEnd = 0, self.getSizeZ()-1
                if self._prStart is not None:
                    prStart = self._prStart
                if self._prEnd is not None:
                    prEnd = self._prEnd
                rv = self._re.renderProjectedCompressed(
                    projection, self._pd.t, 1, prStart, prEnd,
                    self._conn.SERVICE_OPTS)
            return rv
        except omero.InternalException:  # pragma: no cover
            logger.debug('On renderJpeg')
            logger.debug(traceback.format_exc())
            return None
        except Ice.MemoryLimitException:  # pragma: no cover
            # Make sure renderCompressed isn't called again on this re, as it
            # hangs
            self._obj.clearPixels()
            self._obj.pixelsLoaded = False
            self._closeRE()
            raise

    def exportOmeTiff(self, bufsize=0):
        """
        Exports the OME-TIFF representation of this image.

        :type bufsize: int or tuple
        :param bufsize: if 0 return a single string buffer with the whole
                        OME-TIFF
                        if >0 return a tuple holding total size and generator
                        of chunks (string buffers) of bufsize bytes each
        :return:        OME-TIFF file data
        :rtype:         String or (size, data generator)
        """

        # the exporter is closed in the fileread* methods
        e = self._conn.createExporter()
        e.addImage(self.getId())
        size = e.generateTiff(self._conn.SERVICE_OPTS)
        if bufsize == 0:
            # Read it all in one go
            return fileread(e, size, 65536)
        else:
            # generator using bufsize
            return (size, fileread_gen(e, size, bufsize))

    def _wordwrap(self, width, text, font):
        """
        Wraps text into lines that are less than a certain width (when rendered
        in specified font)

        :param width:   The max width to wrap text (pixels)
        :type width:    Int
        :param text:    The text to wrap
        :type text:     String
        :param font:    Font to use.
        :type font:     E.g. PIL ImageFont
        :return:        List of text lines
        :rtype:         List of Strings
        """

        rv = []
        tokens = filter(None, text.split(' '))
        while len(tokens) > 1:
            p1 = 0
            p2 = 1
            while (p2 <= len(tokens) and
                   font.getsize(' '.join(tokens[p1:p2]))[0] < width):
                p2 += 1
            rv.append(' '.join(tokens[p1:p2-1]))
            tokens = tokens[p2-1:]
        if len(tokens):
            rv.append(' '.join(tokens))
        logger.debug(rv)
        return rv

    @assert_re()
    def createMovie(self, outpath, zstart, zend, tstart, tend, opts=None):
        """
        Creates a movie file from this image.
        TODO:   makemovie import is commented out in 4.2+

        :type outpath: string
        :type zstart: int
        :type zend: int
        :type tstart: int
        :type tend: int
        :type opts: dict
        :param opts: dictionary of extra options.
                     Currently processed options are:
                     - watermark:string: path to image to use as watermark
                     - slides:tuple: tuple of tuples with slides to prefix
                       and postfix video with in format
                       (secs:int,
                        topline:text[, middleline:text[, bottomline:text]])
                       If more than 2 slides are provided they will be ignored
                     - fps:int: frames per second
                     - minsize: tuple of (minwidth, minheight, bgcolor)
                     - format:string: one of video/mpeg or video/quicktime

        :return:    Tuple of (file-ext, format)
        :rtype:     (String, String)
        """
        todel = []
        svc = self._conn.getScriptService()
        mms = filter(lambda x: x.name.val == 'Make_Movie.py', svc.getScripts())
        if not len(mms):
            logger.error('No Make_Movie.py script found!')
            return None, None
        mms = mms[0]
        params = svc.getParams(mms.id.val)
        args = ['IDs=%d' % self.getId()]
        args.append('Do_Link=False')
        args.append('Z_Start=%d' % zstart)
        args.append('Z_End=%d' % zend)
        args.append('T_Start=%d' % tstart)
        args.append('T_End=%d' % tend)
        if 'fps' in opts:
            args.append('FPS=%d' % opts['fps'])
        if 'format' in opts:
            if opts['format'] == 'video/mpeg':
                args.append('Format=MPEG')
            elif opts['format'] == 'video/wmv':
                args.append('Format=WMV')
            else:
                args.append('Format=Quicktime')
        rdid = self._getRDef()
        if rdid is not None:
            args.append('RenderingDef_ID=%d' % rdid)

        # Lets prepare the channel settings
        channels = self.getChannels()
        args.append(
            'ChannelsExtended=%s'
            % (','.join(
                ["%d|%s:%s$%s"
                 % (x._idx+1,
                    Decimal(str(x.getWindowStart())),
                    Decimal(str(x.getWindowEnd())),
                    x.getColor().getHtml())
                    for x in channels if x.isActive()])))

        watermark = opts.get('watermark', None)
        logger.debug('watermark: %s' % watermark)
        if watermark:
            origFile = self._conn.createOriginalFileFromLocalFile(watermark)
            args.append('Watermark=OriginalFile:%d' % origFile.getId())
            todel.append(origFile.getId())

        w, h = self.getSizeX(), self.getSizeY()
        if 'minsize' in opts:
            args.append('Min_Width=%d' % opts['minsize'][0])
            w = max(w, opts['minsize'][0])
            args.append('Min_Height=%d' % opts['minsize'][1])
            h = max(h, opts['minsize'][1])
            args.append('Canvas_Colour=%s' % opts['minsize'][2])

        scalebars = (1, 1, 2, 2, 5, 5, 5, 5, 10, 10, 10, 10)
        scalebar = scalebars[max(min(int(w / 256)-1, len(scalebars)), 1) - 1]
        args.append('Scalebar=%d' % scalebar)
        fsizes = (8, 8, 12, 18, 24, 32, 32, 40, 48, 56, 56, 64)
        fsize = fsizes[max(min(int(w / 256)-1, len(fsizes)), 1) - 1]
        font = ImageFont.load('%s/pilfonts/B%0.2d.pil' % (THISPATH, fsize))
        slides = opts.get('slides', [])
        for slidepos in range(min(2, len(slides))):
            t = slides[slidepos]
            slide = Image.new("RGBA", (w, h))
            for i, line in enumerate(t[1:4]):
                line = line.decode('utf8').encode('iso8859-1')
                wwline = self._wordwrap(w, line, font)
                for j, line in enumerate(wwline):
                    tsize = font.getsize(line)
                    draw = ImageDraw.Draw(slide)
                    if i == 0:
                        y = 10+j*tsize[1]
                    elif i == 1:
                        y = h / 2 - \
                            ((len(wwline)-j)*tsize[1]) + \
                            (len(wwline)*tsize[1])/2
                    else:
                        y = h - (len(wwline) - j)*tsize[1] - 10
                    draw.text((w/2-tsize[0]/2, y), line, font=font)
            fp = StringIO()
            slide.save(fp, "JPEG")
            fileSize = len(fp.getvalue())
            origFile = self._conn.createOriginalFileFromFileObj(
                fp, 'slide', '', fileSize)
            if slidepos == 0:
                args.append('Intro_Slide=OriginalFile:%d' % origFile.getId())
                args.append('Intro_Duration=%d' % t[0])
            else:
                args.append('Ending_Slide=OriginalFile:%d' % origFile.getId())
                args.append('Ending_Duration=%d' % t[0])
            todel.append(origFile.getId())

        m = scripts.parse_inputs(args, params)

        try:
            proc = svc.runScript(mms.id.val, m, None)
            proc.getJob()
        except omero.ValidationException, ve:
            logger.error('Bad Parameters:\n%s' % ve)
            return None, None

        # Adding notification to wait on result
        cb = scripts.ProcessCallbackI(self._conn.c, proc)
        try:
            while proc.poll() is None:
                cb.block(1000)
            rv = proc.getResults(3)
        finally:
            cb.close()

        if 'File_Annotation' not in rv:
            logger.error('Error in createMovie:')
            if 'stderr' in rv:
                x = StringIO()
                self._conn.c.download(ofile=rv['stderr'].val, filehandle=x)
                logger.error(x.getvalue())
            return None, None

        f = rv['File_Annotation'].val
        ofw = OriginalFileWrapper(self._conn, f)
        todel.append(ofw.getId())
        logger.debug('writing movie on %s' % (outpath,))
        outfile = file(outpath, 'w')
        for chunk in ofw.getFileInChunks():
            outfile.write(chunk)
        outfile.close()
        handle = self._conn.deleteObjects('OriginalFile', todel)
        try:
            self._conn._waitOnCmd(handle)
        finally:
            handle.close()

        return os.path.splitext(f.name.val)[-1], f.mimetype.val

    def renderImage(self, z, t, compression=0.9):
        """
        Render the Image, (projected) and compressed.
        For projection, call :meth:`setProjection` before renderImage.

        :param z:       Z index
        :param t:       T index
        :param compression:   Image compression level
        :return:        A PIL Image or None
        :rtype:         PIL Image.
        """

        rv = self.renderJpeg(z, t, compression)
        if rv is not None:
            i = StringIO(rv)
            rv = Image.open(i)
        return rv

    def renderSplitChannel(self, z, t, compression=0.9, border=2):
        """
        Prepares a jpeg representation of a 2d grid holding a render of each
        channel, along with one for all channels at the set Z and T points.

        :param z:       Z index
        :param t:       T index
        :param compression: Image compression level
        :param border:
        :return: value
        """

        img = self.renderSplitChannelImage(z, t, compression, border)
        rv = StringIO()
        img.save(rv, 'jpeg', quality=int(compression*100))
        return rv.getvalue()

    def splitChannelDims(self, border=2):
        """
        Returns a dict of layout parameters for generating split channel image.
        E.g. row count, column count etc.  for greyscale and color layouts.

        :param border:  spacing between panels
        :type border:   int
        :return:        Dict of parameters
        :rtype:         Dict
        """

        c = self.getSizeC()
        # Greyscale, no channel overlayed image
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv = {'g': {'width': self.getSizeX()*x + border*(x+1),
                    'height': self.getSizeY()*y+border*(y+1),
                    'border': border,
                    'gridx': x,
                    'gridy': y, }
              }
        # Color, one extra image with all channels overlayed
        c += 1
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv['c'] = {'width': self.getSizeX()*x + border*(x+1),
                   'height': self.getSizeY()*y+border*(y+1),
                   'border': border,
                   'gridx': x,
                   'gridy': y, }
        return rv

    def _renderSplit_channelLabel(self, channel):
        return str(channel.getLabel())

    def renderSplitChannelImage(self, z, t, compression=0.9, border=2):
        """
        Prepares a PIL Image with a 2d grid holding a render of each channel,
        along with one for all channels at the set Z and T points.

        :param z:   Z index
        :param t:   T index
        :param compression: Compression level
        :param border:  space around each panel (int)
        :return:        canvas
        :rtype:         PIL Image
        """

        dims = self.splitChannelDims(
            border=border)[self.isGreyscaleRenderingModel() and 'g' or 'c']
        canvas = Image.new('RGBA', (dims['width'], dims['height']), '#fff')
        cmap = [
            ch.isActive() and i+1 or 0
            for i, ch in enumerate(self.getChannels())]
        c = self.getSizeC()
        pxc = 0
        px = dims['border']
        py = dims['border']

        # Font sizes depends on image width
        w = self.getSizeX()
        if w >= 640:
            fsize = (int((w-640)/128)*8) + 24
            if fsize > 64:
                fsize = 64
        elif w >= 512:
            fsize = 24
        elif w >= 384:  # pragma: no cover
            fsize = 18
        elif w >= 298:  # pragma: no cover
            fsize = 14
        elif w >= 256:  # pragma: no cover
            fsize = 12
        elif w >= 213:  # pragma: no cover
            fsize = 10
        elif w >= 96:  # pragma: no cover
            fsize = 8
        else:  # pragma: no cover
            fsize = 0
        if fsize > 0:
            font = ImageFont.load('%s/pilfonts/B%0.2d.pil' % (THISPATH, fsize))

        for i in range(c):
            if cmap[i]:
                self.setActiveChannels((i+1,))
                img = self.renderImage(z, t, compression)
                if fsize > 0:
                    draw = ImageDraw.ImageDraw(img)
                    draw.text(
                        (2, 2),
                        "%s" % (self._renderSplit_channelLabel(
                            self.getChannels()[i])),
                        font=font, fill="#fff")
                canvas.paste(img, (px, py))
            pxc += 1
            if pxc < dims['gridx']:
                px += self.getSizeX() + border
            else:
                pxc = 0
                px = border
                py += self.getSizeY() + border
        # Render merged panel with all current channels in color
        self.setActiveChannels(cmap)
        self.setColorRenderingModel()
        img = self.renderImage(z, t, compression)
        if fsize > 0:
            draw = ImageDraw.ImageDraw(img)
            draw.text((2, 2), "merged", font=font, fill="#fff")
        canvas.paste(img, (px, py))
        return canvas

    LP_PALLETE = [0, 0, 0, 0, 0, 0, 255, 255, 255]
    LP_TRANSPARENT = 0  # Some color
    LP_BGCOLOR = 1  # Black
    LP_FGCOLOR = 2  # white

    def prepareLinePlotCanvas(self):
        """
        Common part of horizontal and vertical line plot rendering.

        :returns: (Image, width, height).
        """
        channels = filter(lambda x: x.isActive(), self.getChannels())
        width = self.getSizeX()
        height = self.getSizeY()

        pal = list(self.LP_PALLETE)
        # Prepare the palette taking channel colors in consideration
        for channel in channels:
            pal.extend(channel.getColor().getRGB())

        # Prepare the PIL classes we'll be using
        im = Image.new('P', (width, height))
        im.putpalette(pal)
        return im, width, height

    @assert_re()
    def renderRowLinePlotGif(self, z, t, y, linewidth=1):
        """
        Draws the Row plot as a gif file. Returns gif data.

        :param z:   Z index
        :param t:   T index
        :param y:   Y position
        :param linewidth:   Width of plot line
        :return:    gif data as String
        :rtype:     String
        """

        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas()
        base = height - 1

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle(
            [0, 0, width-1, base], fill=self.LP_TRANSPARENT,
            outline=self.LP_TRANSPARENT)
        draw.line(((0, y), (width, y)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab row data
        rows = self.getRow(z, t, y)

        for r in range(len(rows)):
            chrow = rows[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = base-chrow[0]
            for i in range(len(chrow)):
                draw.line(
                    ((i, last_point), (i, base-chrow[i])), fill=color,
                    width=linewidth)
                last_point = base-chrow[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re()
    def renderColLinePlotGif(self, z, t, x, linewidth=1):
        """
        Draws the Column plot as a gif file. Returns gif data.

        :param z:   Z index
        :param t:   T index
        :param x:   X position
        :param linewidth:   Width of plot line
        :return:    gif data as String
        :rtype:     String
        """

        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas()

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle([0, 0, width-1, height-1],
                       fill=self.LP_TRANSPARENT, outline=self.LP_TRANSPARENT)
        draw.line(((x, 0), (x, height)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab col data
        cols = self.getCol(z, t, x)

        for r in range(len(cols)):
            chcol = cols[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = chcol[0]
            for i in range(len(chcol)):
                draw.line(
                    ((last_point, i), (chcol[i], i)), fill=color,
                    width=linewidth)
                last_point = chcol[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re()
    def getZ(self):
        """
        Returns the last used value of Z (E.g. for renderingJpeg or line plot)
        Returns 0 if these methods not been used yet.
        TODO: How to get default-Z?

        :return:    current Z index
        :rtype:     int
        """

        return self._pd.z

    @assert_re()
    def getT(self):
        """
        Returns the last used value of T (E.g. for renderingJpeg or line plot)
        Returns 0 if these methods not been used yet.
        TODO: How to get default-T?

        :return:    current T index
        :rtype:     int
        """

        return self._pd.t

    @assert_re()
    def getDefaultZ(self):
        """
        Gets the default Z index from the rendering engine
        """
        return self._re.getDefaultZ()

    @assert_re()
    def getDefaultT(self):
        """
        Gets the default T index from the rendering engine
        """
        return self._re.getDefaultT()

    @assert_re()
    def setDefaultZ(self, z):
        """
        Sets the default Z index to the rendering engine
        """
        return self._re.setDefaultZ(z)

    @assert_re()
    def setDefaultT(self, t):
        """
        Sets the default T index to the rendering engine
        """
        return self._re.setDefaultT(t)

    @assert_pixels
    def getPixelsType(self):
        """
        Gets name of pixel data type.

        :return:    name of the image precision, e.g., float, uint8, etc.
        :rtype:     String
        """
        rv = self._obj.getPrimaryPixels().getPixelsType().value
        return rv is not None and rv.val or 'unknown'

    @assert_pixels
    def getPixelSizeX(self, units=None):
        """
        Gets the physical size X of pixels in microns.
        If units is True, or a valid length, e.g. "METER"
        return omero.model.LengthI.

        :return:    Size of pixel in x or None
        :rtype:     float or omero.model.LengthI
        """
        return self._unwrapunits(
            self._obj.getPrimaryPixels().getPhysicalSizeX(), units)

    @assert_pixels
    def getPixelSizeY(self, units=None):
        """
        Gets the physical size Y of pixels in microns.
        If units is True, or a valid length, e.g. "METER"
        return omero.model.LengthI.

        :return:    Size of pixel in y or None
        :rtype:     float or omero.model.LengthI
        """
        return self._unwrapunits(
            self._obj.getPrimaryPixels().getPhysicalSizeY(), units)

    @assert_pixels
    def getPixelSizeZ(self, units=None):
        """
        Gets the physical size Z of pixels in microns.
        If units is True, or a valid length, e.g. "METER"
        return omero.model.LengthI.

        :return:    Size of pixel in z or None
        :rtype:     float or omero.model.LengthI
        """
        return self._unwrapunits(
            self._obj.getPrimaryPixels().getPhysicalSizeZ(), units)

    @assert_pixels
    def getSizeX(self):
        """
        Gets width (size X) of the image (in pixels)

        :return:    width
        :rtype:     int
        """

        return self._obj.getPrimaryPixels().getSizeX().val

    @assert_pixels
    def getSizeY(self):
        """
        Gets height (size Y) of the image (in pixels)

        :return:    height
        :rtype:     int
        """

        return self._obj.getPrimaryPixels().getSizeY().val

    @assert_pixels
    def getSizeZ(self):
        """
        Gets Z count of the image

        :return:    size Z
        :rtype:     int
        """

        if self.isInvertedAxis():
            return self._obj.getPrimaryPixels().getSizeT().val
        else:
            return self._obj.getPrimaryPixels().getSizeZ().val

    @assert_pixels
    def getSizeT(self):
        """
        Gets T count of the image

        :return:    size T
        :rtype:     int
        """

        if self.isInvertedAxis():
            return self._obj.getPrimaryPixels().getSizeZ().val
        else:
            return self._obj.getPrimaryPixels().getSizeT().val

    @assert_pixels
    def getSizeC(self):
        """
        Gets C count of the image (number of channels)

        :return:    size C
        :rtype:     int
        """

        return self._obj.getPrimaryPixels().getSizeC().val

    def requiresPixelsPyramid(self):
        """Returns True if Image Plane is over the max plane size."""
        max_sizes = self._conn.getMaxPlaneSize()
        return self.getSizeX() * self.getSizeY() > max_sizes[0] * max_sizes[1]

    def clearDefaults(self):
        """
        Removes specific color settings from channels

        :return:    True if allowed to do this
        :rtype:     Boolean
        """

        if not self.canWrite():
            return False
        for c in self.getChannels():
            c.unloadRed()
            c.unloadGreen()
            c.unloadBlue()
            c.unloadAlpha()
            c.save()
        self._deleteSettings()
        return True

    def _deleteSettings(self):
        handle = self._conn.deleteObjects("Image/RenderingDef", [self.getId()])
        try:
            self._conn._waitOnCmd(handle)
        finally:
            handle.close()

    def _collectRenderOptions(self):
        """
        Returns a map of rendering options not stored in rendering settings.
            - 'p' : projection
            - 'ia' : inverted axis (swap Z and T)

        :return:    Dict of render options
        :rtype:     Dict
        """

        rv = {}
        rv['p'] = self.getProjection()
        rv['ia'] = self.isInvertedAxis() and "1" or "0"
        return rv

    def _loadRenderOptions(self):
        """
        Loads rendering options from an Annotation on the Image.

        :return:    Dict of rendering options
        :rtype:     Dict
        """
        ns = self._conn.CONFIG.IMG_ROPTSNS
        if ns:
            ann = self.getAnnotation(ns)
            if ann is not None:
                opts = dict([x.split('=') for x in ann.getValue().split('&')])
                return opts
        return {}

    def loadRenderOptions(self):
        """
        Loads rendering options from an Annotation on the Image and applies
        them to the Image.

        :return:    True!    TODO: Always True??
        """
        opts = self._loadRenderOptions()
        self.setProjection(opts.get('p', None))
        self.setInvertedAxis(opts.get('ia', "0") == "1")
        return True

    @assert_re()
    def saveDefaults(self):
        """
        Limited support for saving the current prepared image rendering defs.
        Right now only channel colors are saved back.

        :return: Boolean
        """

        if not self.canAnnotate():
            return False
        ns = self._conn.CONFIG.IMG_ROPTSNS
        if ns:
            opts = self._collectRenderOptions()
            self.removeAnnotations(ns)
            ann = omero.gateway.CommentAnnotationWrapper()
            ann.setNs(ns)
            ann.setValue(
                '&'.join(['='.join(map(str, x)) for x in opts.items()]))
            self.linkAnnotation(ann)
        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.details.group.id.val)
        self._re.saveCurrentSettings(ctx)
        return True

    @assert_re()
    def resetDefaults(self, save=True):
        ns = self._conn.CONFIG.IMG_ROPTSNS
        if ns and self.canAnnotate():
            opts = self._collectRenderOptions()
            self.removeAnnotations(ns)
            ann = omero.gateway.CommentAnnotationWrapper()
            ann.setNs(ns)
            ann.setValue(
                '&'.join(['='.join(map(str, x)) for x in opts.items()]))
            self.linkAnnotation(ann)
        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.details.group.id.val)
        if not self.canAnnotate():
            save = False
        self._re.resetDefaultSettings(save, ctx)
        return True

    def countArchivedFiles(self):
        """
        Returns the number of Original 'archived' Files linked to primary
        pixels.
        """
        fsInfo = self.getImportedFilesInfo()
        if not fsInfo['fileset']:
            return fsInfo['count']
        return 0

    def countFilesetFiles(self):
        """
        Counts the Original Files that are part of the FS Fileset linked to
        this image
        """

        fsInfo = self.getImportedFilesInfo()
        if fsInfo['fileset']:
            return fsInfo['count']
        return 0

    def getImportedFilesInfo(self):
        """
        Returns a dict of 'count' and 'size' of the Fileset files (OMERO 5) or
        the Original Archived files (OMERO 4)

        :return:        A dict of 'count' and sum 'size' of the files.
        """
        if self._importedFilesInfo is None:
            # Check for Filesets first...
            self._importedFilesInfo = self._conn.getFilesetFilesInfo(
                [self.getId()])
            if (self._importedFilesInfo['count'] == 0):
                # If none, check Archived files
                self._importedFilesInfo = self._conn.getArchivedFilesInfo(
                    [self.getId()])
        return self._importedFilesInfo

    def countImportedImageFiles(self):
        """
        Returns a count of the number of Imported Image files
        (Archived files for pre-FS images)
        This will only be 0 if the image was imported pre-FS
        and original files NOT archived
        """
        return self.getImportedFilesInfo()['count']

    def getArchivedFiles(self):
        """
        Returns a generator of :class:`OriginalFileWrapper` corresponding to
        the archived files linked to primary pixels
        ** Deprecated ** Use :meth:`getImportedImageFiles`.
        """
        warnings.warn(
            "Deprecated. Use getImportedImageFiles()", DeprecationWarning)
        return self.getImportedImageFiles()

    def getImportedImageFiles(self):
        """
        Returns a generator of :class:`OriginalFileWrapper` corresponding to
        the Imported image files that created this image, if available.
        """
        query_service = self._conn.getQueryService()

        # If we have an FS image, return Fileset files.
        params = omero.sys.ParametersI()
        params.addId(self.getId())
        query = 'select ofile from FilesetEntry as fse '\
                'join fse.fileset as fileset '\
                'join fse.originalFile as ofile '\
                'join fileset.images as image '\
                'where image.id in (:id)'
        original_files = query_service.findAllByQuery(
            query, params, self._conn.SERVICE_OPTS
        )

        if len(original_files) == 0:
            # Otherwise, return Original Archived Files
            params = omero.sys.ParametersI()
            params.addId(self.getPixelsId())
            query = 'select ofile from PixelsOriginalFileMap as link '\
                    'join link.parent as ofile ' \
                    'where link.child.id = :id'
            original_files = query_service.findAllByQuery(
                query, params, self._conn.SERVICE_OPTS
            )

        for original_file in original_files:
            yield OriginalFileWrapper(self._conn, original_file)

    def getImportedImageFilePaths(self):
        """
        Returns a generator of path strings corresponding to the Imported
        image files that created this image, if available.
        """
        query_service = self._conn.getQueryService()
        server_paths = list()
        client_paths = list()

        # If we have an FS image, return Fileset files.
        params = omero.sys.ParametersI()
        params.addId(self.getId())
        query = 'select ofile.path, ofile.name, fse.clientPath '\
                'from FilesetEntry as fse '\
                'join fse.fileset as fileset '\
                'join fse.originalFile as ofile '\
                'join fileset.images as image '\
                'where image.id in (:id)'
        rows = query_service.projection(
            query, params, self._conn.SERVICE_OPTS
        )
        for row in rows:
            path, name, clientPath = row
            server_paths.append('%s%s' % (unwrap(path), unwrap(name)))
            client_paths.append(unwrap(clientPath))

        if len(rows) == 0:
            # Otherwise, return Original Archived Files
            params = omero.sys.ParametersI()
            params.addId(self.getPixelsId())
            query = 'select ofile.path, ofile.name '\
                    '    from PixelsOriginalFileMap as link '\
                    'join link.parent as ofile ' \
                    'where link.child.id = :id'
            rows = query_service.projection(
                query, params, self._conn.SERVICE_OPTS
            )
            for row in rows:
                path, name = row
                server_paths.append('%s%s' % (unwrap(path), unwrap(name)))

        return {'server_paths': server_paths, 'client_paths': client_paths}

    def getFileset(self):
        """
        Returns the Fileset linked to this Image.
        Fileset images, usedFiles and originalFiles are loaded.
        """
        if self.fileset is not None:
            return self._conn.getObject("Fileset", self.fileset.id.val)

    def getInplaceImport(self):
        """
        If the image was imported using file transfer,
        return the type of file transfer.
        One of:
        'ome.formats.importer.transfers.MoveFileTransfer',
        'ome.formats.importer.transfers.CopyFileTransfer',
        'ome.formats.importer.transfers.CopyMoveFileTransfer',
        'ome.formats.importer.transfers.HardlinkFileTransfer',
        'ome.formats.importer.transfers.SymlinkFileTransfer'

        :rtype:     String or None
        :return:    Transfer type or None
        """
        ns = omero.constants.namespaces.NSFILETRANSFER
        fsInfo = self.getImportedFilesInfo()
        if 'annotations' in fsInfo:
            for a in fsInfo['annotations']:
                if ns == a['ns']:
                    return a['value']

    def getROICount(self, shapeType=None, filterByCurrentUser=False):
        """
        Count number of ROIs associated to an image

        :param shapeType: Filter by shape type ("Rectangle",...).
        :param filterByCurrentUser: Whether or not to filter the count by
                                    the currently logged in user.
        :return: Number of ROIs found for the currently logged in user if
                 filterByCurrentUser is True, otherwise the total number
                 found.
        """

        # Create ROI shape validator (return True if at least one shape is
        # found)
        def isValidType(shape):
            if not shapeType:
                return True
            elif isinstance(shapeType, list):
                for t in shapeType:
                    if isinstance(shape, getattr(omero.model, t)):
                        return True
            elif isinstance(shape, getattr(omero.model, shapeType)):
                return True
            return False

        def isValidROI(roi):
            for shape in roi.copyShapes():
                if isValidType(shape):
                    return True
            return False

        # Optimisation for the most common use case of unfiltered ROI counts
        # for the current user.
        if shapeType is None:
            params = omero.sys.ParametersI()
            params.addLong('imageId', self.id)
            query = 'select count(*) from Roi as roi ' \
                    'where roi.image.id = :imageId'
            if filterByCurrentUser:
                query += ' and roi.details.owner.id = :ownerId'
                params.addLong('ownerId', self._conn.getUserId())
            count = self._conn.getQueryService().projection(
                query, params, self._conn.SERVICE_OPTS)
            # Projection returns a two dimensional array of RType wrapped
            # return values so we want the value of row one, column one.
            return count[0][0].getValue()

        roiOptions = omero.api.RoiOptions()
        if filterByCurrentUser:
            roiOptions.userId = omero.rtypes.rlong(self._conn.getUserId())

        result = self._conn.getRoiService().findByImage(self.id, roiOptions)
        count = sum(1 for roi in result.rois if isValidROI(roi))
        return count

ImageWrapper = _ImageWrapper

# INSTRUMENT AND ACQUISITION #
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
