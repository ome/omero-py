#!/usr/bin/env python
#
# OMERO Utilities package
#
# Copyright 2009 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

import os
import sys
import Ice
import time
import uuid
import omero
import IceGrid
import logging
import Glacier2
import threading
import exceptions
import logging.handlers
import omero.util.concurrency

from omero.util.decorators import locked

LOGDIR = os.path.join("var","log")
LOGFORMAT =  """%(asctime)s %(levelname)-5.5s [%(name)40s] (%(threadName)-10s) %(message)s"""
LOGLEVEL = logging.INFO
LOGSIZE = 500000000
LOGNUM = 9
LOGMODE = "a"

orig_stdout = sys.stdout
orig_stderr = sys.stderr

def make_logname(self):
    """
    Generates a logname from the given instance using the module and name from its class
    """
    log_name = "%s.%s" % (self.__class__.__module__, self.__class__.__name__)
    return log_name

def configure_logging(logdir = None, logfile = None, loglevel = LOGLEVEL,\
    format = LOGFORMAT, filemode = LOGMODE, maxBytes = LOGSIZE, backupCount = LOGNUM, time_rollover = False):

    if logdir is None or logfile is None:
        handler = logging.StreamHandler()
    elif not time_rollover:
        handler = logging.handlers.RotatingFileHandler(os.path.join(logdir, logfile), maxBytes = maxBytes, backupCount = backupCount)
    else:
        handler = logging.handlers.TimedRotatingFileHandler(os.path.join(logdir, logfile),'midnight',1)
        # Windows will not allow renaming (or deleting) a file that's open.
        # There's nothing the logging package can do about that.
        try:
            sys.getwindowsversion()
        except:
            handler.doRollover()

    handler.setLevel(loglevel)
    formatter = logging.Formatter(format)
    handler.setFormatter(formatter)
    rootLogger = logging.getLogger()
    rootLogger.setLevel(loglevel)
    rootLogger.addHandler(handler)
    return rootLogger

def configure_server_logging(props):
    """
    Takes an Ice.Properties instance and configures logging
    """
    program_name = props.getProperty("Ice.Admin.ServerId")
    # Using Ice.ProgramName on Windows failed
    log_name = program_name+".log"
    log_timed = props.getPropertyWithDefault("omero.logging.timedlog","False")[0] in ('T', 't')
    log_num = int(props.getPropertyWithDefault("omero.logging.lognum",str(LOGNUM)))
    log_size = int(props.getPropertyWithDefault("omero.logging.logsize",str(LOGSIZE)))
    log_num = int(props.getPropertyWithDefault("omero.logging.lognum",str(LOGNUM)))
    log_level = int(props.getPropertyWithDefault("omero.logging.level",str(LOGLEVEL)))
    configure_logging(LOGDIR, log_name, loglevel=log_level, maxBytes=log_size, backupCount=log_num, time_rollover = log_timed)

    sys.stdout = StreamRedirect(logging.getLogger("stdout"))
    sys.stderr = StreamRedirect(logging.getLogger("stderr"))

class StreamRedirect(object):
    """
    Since all server components should exclusively using the logging module
    any output to stdout or stderr is caught and logged at "WARN". This is
    useful, especially in the case of Windows, where stdout/stderr is eaten.
    """

    def __init__(self, logger):
        self.logger = logger
        self.internal = logging.getLogger("StreamRedirect")
        self.softspace = False

    def flush(self):
        pass

    def write(self, msg):
        msg = msg.strip()
        if msg:
            self.logger.warn(msg)

    def __getattr__(self, name):
        self.internal.warn("No attribute: %s" % name)

def internal_service_factory(communicator, user="root", group=None, retries=6, interval=10, client_uuid=None, stop_event = None):
    """
    Try to return a ServiceFactory from the grid.

    Try a number of times then give up and raise the
    last exception returned. This method will only
    work internally to the grid, i.e. behind the Glacier2
    firewall. It is intended for internal servers to
    be able to create sessions for accessing the database. ::
        communicator := Ice.Communicator used to find the registry
        user         := Username which should have a session created
        group        := Group into which the session should be logged
        retries      := Number of session creation retries before throwing
        interval     := Seconds between retries
        client_uuid  := Uuid of the client which should be used
    """
    log = logging.getLogger("omero.utils")
    if stop_event == None:
        stop_event = omero.util.concurrency.get_event()

    tryCount = 0
    excpt = None
    query = communicator.stringToProxy("IceGrid/Query")
    query = IceGrid.QueryPrx.checkedCast(query)

    if client_uuid is None:
        client_uuid = str(uuid.uuid4())

    while tryCount < retries:
        if stop_event.isSet(): # Something is shutting down, exit.
            return None
        try:
            blitz = query.findAllObjectsByType("::Glacier2::SessionManager")[0]
            blitz = Glacier2.SessionManagerPrx.checkedCast(blitz)
            sf = blitz.create(user, None, {"omero.client.uuid":client_uuid})
            # Group currently unused.
            return omero.api.ServiceFactoryPrx.checkedCast(sf)
        except Exception, e:
            tryCount += 1
            log.info("Failed to get session on attempt %s", str(tryCount))
            excpt = e
            stop_event.wait(interval)

    log.warn("Reason: %s", str(excpt))
    raise excpt

def create_admin_session(communicator):
    """
    """
    reg = communicator.stringToProxy("IceGrid/Registry")
    reg = IceGrid.RegistryPrx.checkedCast(reg)
    adm = reg.createAdminSession('null', '')
    return adm

def add_grid_object(communicator, obj):
    """
    """
    sid = communicator.identityToString(obj.ice_getIdentity())
    adm = create_admin_session(communicator)
    prx = adm.getAdmin()
    try:
        try:
            prx.addObject(obj)
        except IceGrid.ObjectExistsException:
            prx.updateObject(obj)
    finally:
            adm.destroy()

def long_to_path(id, root=""):
    """
    Converts a long to a path such that for all directiories only
    a 1000 files and a 1000 subdirectories will be returned.

    This method duplicates the logic in
    ome.io.nio.AbstractFileSystemService.java:getPath()
    """
    suffix = ""
    remaining = id
    dirno = 0

    if id is None or id == "":
        raise exceptions.Exception("Expecting a not-null id.")

    id = long(id)

    if id < 0:
        raise exceptions.Exception("Expecting a non-negative id.")

    while (remaining > 999):
        remaining /= 1000

        if remaining > 0:
            dirno = remaining % 1000
            suffix = os.path.join("Dir-%03d" % dirno, suffix)

    return os.path.join(root, "%s%s" %(suffix,id))

class ServerContext(object):
    """
    Context passed to all servants.

    server_id, communicator, and stop_event will be
    constructed by the top-level Server instance.

    A context instance may also be configured to hold
    on to an internal session (ServiceFactoryPrx) and
    keep it alive.

    This instance obeys the Resources API and calls
    sf.keepAlive(None) on every check call, but does
    nothing on cleanup. The sf instance must be manually
    cleaned as the final operation of a servant.

    (Note: cleanup of the server context indicates
    server shutdown, so should be infrequent)
    """

    def __init__(self, server_id, communicator, stop_event):
        self._lock = threading.RLock()
        self.logger = logging.getLogger("omero.util.ServerContext")
        self.server_id = server_id
        self.communicator = communicator
        self.stop_event = stop_event

    def newSession(self):
        self.session = internal_service_factory(self.communicator, stop_event = self.stop_event)

    def hasSession(self):
        return hasattr(self, "session")

    @locked
    def getSession(self, recreate = True):
        """
        Returns the ServiceFactoryPrx configured for the context if
        available. If the context was not configured for sessions,
        an ApiUsageException will be thrown: servants should know
        whether or not they were configured for sessions.
        See Servant(..., needs_session = True)

        Otherwise, if there is no ServiceFactoryPrx, an attempt will
        be made to create one if recreate == True. If the value is None
        or non can be recreated, an InternalException will be thrown.

        TODO : currently no arguments are provided for re-creating these,
        but also not in Servant.__init__
        """
        if not self.hasSession():
            raise omero.ApiUsageException("Not configured for server connection")

        if self.session:
            try:
                self.session.keepAlive(None)
            except exceptions.Exception, e:
                self.logger.warn("Connection failure: %s" % e)
                self.session = None

        if self.session is None and recreate:
            try:
                self.newSession()
                self.logger.info("Established connection: %s" % e)
            except exceptions.Exception, e:
                self.logger.warn("Failed to establish connection: %s" % e)

        if self.session is None:
            raise omero.InternalException("No connection to server")

        return self.session

    def check(self):
        """
        Calls getSession() but always returns True. This keeps the context
        available in the resources for later uses, and tries to re-establish
        a connection in case Blitz goes down.
        """
        try:
            self.getSession()
        except:
            pass
        return True

    def cleanup(self):
        """
        Does nothing. Context clean up must happen manually
        since later activities may want to reuse it. Servants using
        a server connection should cleanup the instance *after* Resources
        is cleaned up
        """
        pass

class Server(Ice.Application):
    """
    Basic server implementation which can be used for
    implementing a standalone python server which can
    be started from icegridnode.

    The servant implementation MUST have a constructor
    which takes a single ServerContext argument AND
    have a cleanup() method

    Logging is configured relative to the current directory
    to be in var/log by default.

    Usage::

        if __name__ == "__main__":
            app=Server(ServicesI, "ServicesAdapter", Ice.Identity("Services",""))
            sys.exit(app.main(sys.argv))

    app.impl now points to an instance of ServicesI

    """

    def __init__(self, impl_class, adapter_name, identity, logdir = LOGDIR):

        self.impl_class = impl_class
        self.adapter_name = adapter_name
        self.identity = identity
        self.logdir = logdir
        self.stop_event = omero.util.concurrency.get_event()

    def run(self,args):

        from omero.rtypes import ObjectFactories as rFactories
        from omero.columns import ObjectFactories as cFactories

        props = self.communicator().getProperties()
        configure_server_logging(props)

        self.logger = logging.getLogger("omero.util.Server")
        self.logger.info("*"*80)
        self.logger.info("Starting")

        self.shutdownOnInterrupt()

        try:

            self.objectfactory = omero.clients.ObjectFactory()
            self.objectfactory.registerObjectFactory(self.communicator())
            for of in rFactories.values() + cFactories.values():
                of.register(self.communicator())

            try:
                serverid = self.communicator().getProperties().getProperty("Ice.ServerId")
                ctx = ServerContext(serverid, self.communicator(), self.stop_event)
                self.impl = self.impl_class(ctx)
                getattr(self.impl, "cleanup") # Required per docs
            except:
                self.logger.error("Failed initialization", exc_info=1)
                sys.exit(100)

            try:
                self.adapter = self.communicator().createObjectAdapter(self.adapter_name)
                prx = self.adapter.add(self.impl, self.identity)
                self.adapter.activate()
                add_grid_object(self.communicator(), prx) # This must happen _after_ activation
            except:
                self.logger.error("Failed activation", exc_info=1)
                sys.exit(200)

            self.logger.info("Entering main loop")
            self.communicator().waitForShutdown()
        finally:
            self.stop_event.set() # Let's all waits shutdown
            self.logger.info("Cleanup")
            self.cleanup()
            self.logger.info("Stopped")
            self.logger.info("*"*80)

    def cleanup(self):
        """
        Cleans up all resources that were created by this server.
        Primarily the one servant instance.
        """
        if hasattr(self,"impl"):
            try:
                self.impl.cleanup()
            finally:
                del self.impl


class SimpleServant(object):
    """
    Base servant initialization. Doesn't create or try to cleanup
    a top-level Resources thread. This is useful for large numbers
    of servants. For servers and other singleton-like servants,
    see "Servant"
    """
    def __init__(self, ctx):
        self._lock = threading.RLock()
        self.ctx = ctx
        self.stop_event = ctx.stop_event
        self.communicator = ctx.communicator
        self.logger = logging.getLogger(make_logname(self))
        self.logger.debug("Created")

class Servant(SimpleServant):
    """
    Abstract servant which can be used along with a slice2py
    generated dispatch class as the base type of high-level servants.
    These provide resource cleanup as per the omero.util.Server
    class.

    By passing "needs_session = True" to this constructor, an internal
    session will be created and stored in ServerContext as well as
    registered with self.resources
    """

    def __init__(self, ctx, needs_session = False):
        SimpleServant.__init__(self, ctx)
        self.resources = omero.util.Resources(sleeptime = 60, stop_event = self.stop_event)
        if needs_session:
            self.ctx.newSession()
            self.resources.add(self.ctx)

    def cleanup(self):
        """
        Cleanups all resoures created by this servant. Calling
        cleanup multiple times should be safe.
        """
        resources = self.resources
        self.resources = None
        if resources != None:
            self.logger.info("Cleaning up")
            resources.cleanup()
            self.logger.info("Done")
        if self.ctx.hasSession():
            try:
                sf = self.ctx.getSession(recreate=False)
                self.logger.debug("Destroying %s" % sf)
                sf.destroy()
            except:
                pass

    def __del__(self):
        self.cleanup()


class Resources:
    """
    Container class for storing resources which should be
    cleaned up on close and periodically checked. Use
    stop_event.set() to stop the internal thread.
    """

    def __init__(self, sleeptime = 60, stop_event = None):
        """
        Add resources via add(object). They should have a no-arg cleanup()
        and a check() method.

        The check method will be called periodically (default: 60 seconds)
        on each resource. The cleanup method will be called on
        Resources.cleanup()
        """

        self._lock = threading.RLock()
        self.logger = logging.getLogger("omero.util.Resources")
        self.stop_event = stop_event
        if not self.stop_event:
            self.stop_event = omero.util.concurrency.get_event()

        if sleeptime < 5:
            raise exceptions.Exception("Sleep time should be greater than 5: " % sleeptime)

        self.sleeptime = sleeptime
        self.stuff = []

        class Task(threading.Thread):
            """
            Internal thread used for checking "stuff"
            """
            def run(self):
                ctx = self.ctx # Outer class
                ctx.logger.info("Starting")
                while not ctx.stop_event.isSet():
                    try:
                        ctx.logger.debug("Executing")
                        copy = ctx.copyStuff()
                        remove = ctx.checkAll(copy)
                        ctx.removeAll(remove)
                    except:
                        ctx.logger.error("Exception during execution", exc_info = True)

                    ctx.logger.debug("Sleeping %s" % ctx.sleeptime)
                    # ticket:1531 - Attempting to catch threading issues
                    try:
                        ctx.stop_event.wait(ctx.sleeptime)
                    except ValueError:
                        pass

                ctx.logger.info("Halted")

        self.thread = Task()
        self.thread.ctx = self
        self.thread.start()

    @locked
    def copyStuff(self):
        """
        Within a lock, copy the "stuff" list and reverse it.
        The list is reversed so that entries added
        later, which may depend on earlier added entries
        get a chance to be cleaned up first.
        """
        copy = list(self.stuff)
        copy.reverse()
        return copy

    # Not locked
    def checkAll(self, copy):
        """
        While stop_event is unset, go through the copy
        of stuff and call the check method on each
        entry. Any that throws an exception or returns
        a False value will be returned in the remove list.
        """
        remove = []
        for m in copy:
            if self.stop_event.isSet():
                return # Let cleanup handle this
            self.logger.debug("Checking %s" % m[0])
            method = getattr(m[0],m[2])
            rv = None
            try:
                rv = method()
            except:
                self.logger.warn("Error from %s" % method, exc_info = True)
            if not rv:
                remove.append(m)
        return remove

    @locked
    def removeAll(self, remove):
        """
        Finally, within another lock, call the "cleanup"
        method on all the entries in remove, and remove
        them from the official stuff list. (If stop_event
        is set during execution, we return with the assumption
        that Resources.cleanup() will take care of them)
        """
        for r in remove:
            if self.stop_event.isSet():
                return # Let cleanup handle this
            self.logger.debug("Removing %s" % r[0])
            self.safeClean(r)
            self.stuff.remove(r)

    @locked
    def add(self, object, cleanupMethod = "cleanup", checkMethod = "check"):
        entry = (object,cleanupMethod,checkMethod)
        self.logger.info("Adding object %s" % object)
        self.stuff.append(entry)

    @locked
    def cleanup(self):
        self.stop_event.set()
        for m in self.stuff:
            self.safeClean(m)
        self.stuff = None
        self.logger.info("Cleanup done")

    def safeClean(self, m):
            try:
                self.logger.debug("Cleaning %s" % m[0])
                method = getattr(m[0],m[1])
                method()
            except:
                self.logger.error("Error cleaning resource: %s" % m[0], exc_info=1)

    def __del__(self):
        self.cleanup()

class Environment:
    """
    Simple class for creating an executable environment
    """

    def __init__(self, *args):
        """
        Takes an number of environment variable names which
        should be copied to the target environment if present
        in the current execution environment.
        """
        if sys.platform == "win32":
            # Prevents SocketException. See ticket:1518
            self.env = os.environ.copy()
        else:
            self.env = {}
        for arg in args:
            if os.environ.has_key(arg):
                self.env[arg] = os.environ[arg]
    def __call__(self):
        """
        Returns the environment map when called.
        """
        return self.env

    def set(self, key, value):
        """
        Manually sets a value in the target environment.
        """
        self.env[key] = value

    def append(self, key, addition):
        """
        Manually adds a value to the environment string
        """
        if self.env.has_key(key):
            self.env[key] = os.pathsep.join([self.env[key], addition])
        else:
            self.set(key, addition)
