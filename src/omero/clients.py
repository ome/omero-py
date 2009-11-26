#!/usr/bin/env python
"""

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

__save__ = __name__
__name__ = 'omero'
try:
    import exceptions, traceback, threading, logging
    import Ice, Glacier2, Glacier2_Router_ice
    import uuid
    sys = __import__("sys")

    api = __import__('omero.api')
    model = __import__('omero.model')
    util = __import__('omero.util')
    sys = __import__('omero.sys')

    import omero_API_ice
    import omero_Constants_ice
    import omero_sys_ParametersI
    import omero.rtypes
    from omero.rtypes import rlong
    from omero.rtypes import rint
    from omero.rtypes import rstring
    from omero.rtypes import rdouble
    from omero.rtypes import rfloat

finally:
    __name__ = __save__
    del __save__

ClientError = omero.ClientError

class BaseClient(object):
    """
    Central client-side blitz entry point, and should be in sync with OmeroJava's omero.client
    and OmeroCpp's omero::client.

    Typical usage includes::

        client = omero.client()                          # Uses --Ice.Config argument or ICE_CONFIG variable
        client = omero.client(host = host)               # Defines "omero.host"
        client = omero.client(host = host, port = port)  # Defines "omero.host" and "omero.port"

    For more information, see:

        - U{https://trac.openmicroscopy.org.uk/omero/wiki/ClientDesign}

    """

    def __init__(self, args = None, id = None, \
                     host = None, port = None, pmap = None):
        """
        Constructor which takes one sys.argv-style list, one initialization
        data, one host string, one port integer, and one properties map, in
        that order. *However*, to simplify use, we reassign values based on
        their type with a warning printed. A cleaner approach is to use named
        parameters.
        ::
            c1 = omero.client(None, None, "host", myPort)   # Correct
            c2 = omero.client(host = "host", port = myPort) # Correct
            c3 = omero.client("host", myPort)               # Works with warning

        Both "Ice" and "omero" prefixed properties will be parsed.

        Defines the state variables::
            __previous : InitializationData from any previous communicator, if any
                       Used to re-initialization the client post-closeSession()
           
            __ic       : communicator. Nullness => init() needed on createSession()

            __sf       : current session. Nullness => createSession() needed.

            __resources: if non-null, hs access to this client instance and will
                       periodically call sf.keepAlive(None) in order to keep any
                       session alive. This can be enabled either via the omero.keep_alive
                       configuration property, or by calling the enableKeepAlive() method.
                       Once enabled, the period cannot be adjusted during a single
                       session.

        Modifying these variables outside of the accessors can lead to
        undefined behavior.

        Equivalent to all OmeroJava and OmeroCpp constructors
        """

        # Setting all protected values to prevent AttributeError
        self.__previous = None
        self.__ic = None
        self.__oa = None
        self.__sf = None
        self.__uuid = None
        self.__resources = None
        self.__lock = threading.RLock()

        # Logging
        self.__logger = logging.getLogger("omero.client")
        logging.basicConfig() # Does nothing if already configured

        # Reassigning based on argument type

        args, id, host, port, pmap = self._repair(args, id, host, port, pmap)

        # Copying args since we don't really want them edited
        if not args:
            args = []
        else:
            args = list(args)

        # Equiv to multiple constructors. #######################
        if id == None:
            id = Ice.InitializationData()

        if id.properties == None:
            id.properties = Ice.createProperties(args)

        id.properties.parseCommandLineOptions("omero", args);
        if host:
            id.properties.setProperty("omero.host", str(host))
        if not port:
            port = id.properties.getPropertyWithDefault("omero.port",\
                str(omero.constants.GLACIER2PORT))
        id.properties.setProperty("omero.port", str(port))
        if pmap:
            for k,v in pmap.items():
                id.properties.setProperty(str(k), str(v))

        self._initData(id)

    def _repair(self, args, id, host, port, pmap):
        """
        Takes the 5 arguments passed to the __init__ method
        and attempts to re-order them based on their types.
        This allows for simplified usage without parameter
        names.
        """
        types = [list, Ice.InitializationData, str, int, dict]
        original = [args, id, host, port, pmap]
        repaired = [None, None, None, None, None]

        # Check all to see if valid
        valid = True
        for i in range(0, len(types)):
            if None != original[i] and not isinstance(original[i], types[i]):
                valid = False
                break
        if valid:
            return original

        # Now try to find corrections.
        for i in range(0, len(types)):
            found = None
            for j in range(0, len(types)):
                if isinstance(original[j], types[i]):
                    if not found:
                        found = original[j]
                    else:
                        raise ClientError("Found two arguments of same type: " + str(types[i]))
            if found:
                repaired[i] = found
        return repaired

    def _initData(self, id):
        """
        Initializes the current client via an Ice.InitializationData
        instance. This is called by all of the constructors, but may
        also be called on createSession(name, pass) if a previous
        call to closeSession() has nulled the Ice.Communicator.
        """

        if not id:
            raise ClientError("No initialization data provided.");

        # Strictly necessary for this class to work
        id.properties.setProperty("Ice.ImplicitContext", "Shared")
        id.properties.setProperty("Ice.ACM.Client", "0")
        id.properties.setProperty("Ice.RetryIntervals", "-1")

        # Setting MessageSizeMax
        messageSize = id.properties.getProperty("Ice.MessageSizeMax")
        if not messageSize or len(messageSize) == 0:
            id.properties.setProperty("Ice.MessageSizeMax", str(omero.constants.MESSAGESIZEMAX))

        # Setting ConnectTimeout
        self.parseAndSetInt(id, "Ice.Override.ConnectTimeout",\
                           omero.constants.CONNECTTIMEOUT)

        # Endpoints set to tcp if not present
        endpoints = id.properties.getProperty("omero.ClientCallback.Endpoints")
        if not endpoints or len(endpoints) == 0:
            id.properties.setProperty("omero.ClientCallback.Endpoints", "tcp")

        # Port, setting to default if not present
        port = self.parseAndSetInt(id, "omero.port",\
                                  omero.constants.GLACIER2PORT)

        # Default Router, set a default and then replace
        router = id.properties.getProperty("Ice.Default.Router")
        if not router or len(router) == 0:
            router = str(omero.constants.DEFAULTROUTER)
        host = id.properties.getPropertyWithDefault("omero.host", """<"omero.host" not set>""")
        router = router.replace("@omero.port@", str(port))
        router = router.replace("@omero.host@", str(host))
        id.properties.setProperty("Ice.Default.Router", router)

        # Dump properties
        dump = id.properties.getProperty("omero.dump")
        if len(dump) > 0:
            for prefix in ["omero","Ice"]:
                for k,v in id.properties.getPropertiesForPrefix(prefix).items():
                    print "%s=%s" % (k,v)

        self.__lock.acquire()
        try:
            if self.__ic:
                raise ClientError("Client already initialized")

            self.__ic = Ice.initialize(id)

            if not self.__ic:
                raise ClientError("Improper initialization")

            # Register Object Factory
            self.of = ObjectFactory()
            self.of.registerObjectFactory(self.__ic)
            for of in omero.rtypes.ObjectFactories.values():
                of.register(self.__ic)

            # Define our unique identifier (used during close/detach)
            self.__uuid = str(uuid.uuid4())
            ctx = self.__ic.getImplicitContext()
            if not ctx:
                raise ClientError("Ice.ImplicitContext not set to Shared")
            ctx.put(omero.constants.CLIENTUUID, self.__uuid)

            # Register the default client callback
            self.__oa = self.__ic.createObjectAdapter("omero.ClientCallback")
            cb = BaseClient.CallbackI(self.__ic, self.__oa)
            self.__oa.add(cb, self.__ic.stringToIdentity("ClientCallback/%s" % self.__uuid))
            self.__oa.activate()
        finally:
            self.__lock.release()

    def __del__(self):
        """
        Calls closeSession() and ignores any exceptions.

        Equivalent to close() in OmeroJava or omero::client::~client()
        """
        try:
            self.closeSession()
        except exceptions.Exception, e:
            self.__logger.warning("Ignoring error in client.__del__:" + str(e.__class__))

    def getCommunicator(self):
        """
        Returns the Ice.Communicator for this instance or throws
        an exception if None.
        """
        self.__lock.acquire()
        try:
            if not self.__ic:
                raise ClientError("No Ice.Communicator active; call createSession() or create a new client instance")
            return self.__ic
        finally:
            self.__lock.release()

    def getAdapter(self):
        """
        Returns the Ice.ObjectAdapter for this instance or throws
        an exception if None.
        """
        self.__lock.acquire()
        try:
            if not self.__oa:
                raise ClientError("No Ice.ObjectAdapter active; call createSession() or create a new client instance")
            return self.__oa
        finally:
            self.__lock.release()

    def getSession(self):
        """
        Returns the current active session or throws an exception if none has been
        created since the last closeSession()
        """
        self.__lock.acquire()
        try:
            return self.__sf
        finally:
            self.__lock.release()

    def getImplicitContext(self):
        """
        Returns the Ice.ImplicitContext which defines what properties
        will be sent on every method invocation.
        """
        return self.getCommunicator().getImplicitContext()

    def getProperties(self):
        """
        Returns the active properties for this instance
        """
        self.__lock.acquire()
        try:
            return self.__ic.getProperties()
        finally:
            self.__lock.release()

    def getProperty(self, key):
        """
        Returns the property for the given key or "" if none present
        """
        return self.getProperties().getProperty(key)

    def joinSession(self, session):
        """
        Uses the given session uuid as name
        and password to rejoin a running session
        """
        return self.createSession(session, session)

    def createSession(self, username=None, password=None):
        """
        Performs the actual logic of logging in, which is done via the
        getRouter(). Disallows an extant ServiceFactoryPrx, and
        tries to re-create a null Ice.Communicator. A null or empty
        username will throw an exception, but an empty password is allowed.
        """
        import omero

        self.__lock.acquire()
        try:

            # Checking state

            if self.__sf:
                raise ClientError("Session already active. Create a new omero.client or closeSession()")

            if not self.__ic:
                if not self.__previous:
                    raise ClientError("No previous data to recreate communicator.")
                self._initData(self.__previous)
                self.__previous = None

            # Check the required properties

            if not username:
                username = self.getProperty("omero.user")
            elif isinstance(username,omero.RString):
                username = username.val

            if not username or len(username) == 0:
                raise ClientError("No username specified")

            if not password:
                password = self.getProperty("omero.pass")
            elif isinstance(password,omero.RString):
                password = password.val

            if not password:
                raise ClientError("No password specified")

            # Acquire router and get the proxy
            prx = None
            retries = 0
            while retries < 3:
                reason = None
                if retries > 0:
                    self.__logger.warning(\
                    "%s - createSession retry: %s"% (reason, retries) )
                try:
                    prx = self.getRouter(self.__ic).createSession(username, password)
                    break
                except omero.WrappedCreateSessionException, wrapped:
                    if not wrapped.concurrency:
                        raise wrapped # We only retry concurrency issues.
                    reason = "%s:%s" % (wrapped.type, wrapped.reason)
                    retries = retries + 1
                except Ice.ConnectTimeoutException, cte:
                    reason = "Ice.ConnectTimeoutException:%s" % str(cte)
                    retries = retries + 1

            if not prx:
                raise ClientError("Obtained null object prox")

            # Check type
            self.__sf = omero.api.ServiceFactoryPrx.uncheckedCast(prx)
            if not self.__sf:
                raise ClientError("Obtained object proxy is not a ServiceFactory")

            # Configure keep alive
            keep_alive = self.__ic.getProperties().getPropertyWithDefault("omero.keep_alive", "-1")
            try:
                i = int(keep_alive)
                self.enableKeepAlive(i)
            except:
                pass

            # Set the client callback on the session
            # and pass it to icestorm
            id = self.__ic.stringToIdentity("ClientCallback/%s" % self.__uuid )
            raw = self.__oa.createProxy(id)
            self.__sf.setCallback(omero.api.ClientCallbackPrx.uncheckedCast(raw))
            #self.__sf.subscribe("/public/HeartBeat", raw)

            return self.__sf
        finally:
            self.__lock.release()

    def enableKeepAlive(self, seconds):
        """
        Resets the "omero.keep_alive" property on the current
        Ice.Communicator which is used on initialization to determine
        the time-period between Resource checks. If no __resources
        instance is available currently, one is also created.
        """

        self.__lock.acquire()
        try:
            # A communicator must be configured!
            ic = self.getCommunicator()
            # Setting this here guarantees that after closeSession()
            # the next createSession() will use the new value despite
            # what was in the configuration file
            ic.getProperties().setProperty("omero.keep_alive", str(seconds))

            # If it's not null, then there's already an entry for keeping
            # any existing session alive
            if self.__resources == None and seconds > 0:
                self.__resources = omero.util.Resources(seconds)
                class Entry:
                    def __init__(self, c):
                        self.c = c
                    def cleanup(self): pass
                    def check(self):
                        sf = self.c._BaseClient__sf
                        ic = self.c._BaseClient__ic
                        if sf != None:
                            try:
                                sf.keepAlive(None)
                            except exceptions.Exception, e:
                                self.c._BaseClient__logger.warning("Proxy keep alive failed.")
                                return False
                        return True
                self.__resources.add(Entry(self))
        finally:
            self.__lock.release()

    def getRouter(self, comm):
        """
        Acquires the default router, and throws an exception
        if it is not of type Glacier2.Router. Also sets the
        Ice.ImplicitContext on the router proxy.
        """
        prx = comm.getDefaultRouter()
        if not prx:
            raise ClientError("No default router found.")
        router = Glacier2.RouterPrx.uncheckedCast(prx)
        if not router:
            raise ClientError("Error obtaining Glacier2 router")

        # For whatever reason, we have to set the context
        # on the router context here as well
        router = router.ice_context(comm.getImplicitContext().getContext())
        return router

    def sha1(self, filename):
        """
        Calculates the local sha1 for a file.
        """
        import sha
        digest = sha.new()
        file = open(filename, 'rb')
        try:
            while True:
                block = file.read(1024)
                if not block:
                    break
                digest.update(block)
        finally:
            file.close()
        return digest.hexdigest()

    def upload(self, filename, name = None, path = None,
               type = None, ofile = None, block_size = 1024,
               permissions = None):
        """
        Utility method to upload a file to the server.
        """
        if not self.__sf:
            raise ClientError("No session. Use createSession first.")

        import os, types
        if not filename or not isinstance(filename, types.StringType):
            raise ClientError("Non-null filename must be provided")

        if not os.path.exists(filename):
            raise ClientError("File does not exist: " + filename)

        file = open(filename, 'rb')
        try:

            size = os.path.getsize(file.name)
            if block_size > size:
                block_size = size

            if not ofile:
                ofile = omero.model.OriginalFileI()

            ofile.size = rlong(size)
            ofile.sha1 = rstring(self.sha1(file.name))

            if not ofile.name:
                if name:
                    ofile.name = rstring(name)
                else:
                    ofile.name = rstring(file.name)

            if not ofile.path:
                ofile.path = rstring(os.path.abspath(file.name))

            if not ofile.format:
                if not type:
                    # ofile.format = FormatI("unknown")
                    # Or determine type from file ending
                    raise ClientError("no format given")
                else:
                    ofile.format = omero.model.FormatI()
                    ofile.format.value = rstring(type)

            if permissions:
                ofile.details.permissions = permissions

            up = self.__sf.getUpdateService()
            ofile = up.saveAndReturnObject(ofile)

            prx = self.__sf.createRawFileStore()
            prx.setFileId(ofile.id.val)
            offset = 0
            while True:
                block = file.read(block_size)
                if not block:
                    break
                prx.write(block, offset, len(block))
                offset += len(block)
            prx.close()
        finally:
            file.close()

        return ofile

    def download(self, ofile, filename, block_size = 1024*1024):
        file = open(filename, 'wb')
        try:
            prx = self.__sf.createRawFileStore()
            try:
                if not ofile or not ofile.id:
                    raise ClientError("No file to download")
                ofile = self.__sf.getQueryService().get("OriginalFile", ofile.id.val)

                if block_size > ofile.size.val:
                    block_size = ofile.size.val

                prx.setFileId(ofile.id.val)
                offset = 0
                while offset < ofile.size.val:
                    block = prx.read(offset, block_size)
                    if not block:
                        break
                    file.write(block)
                    offset += len(block)
                file.flush()
            finally:
                prx.close()
        finally:
            file.close()

    def closeSession(self):
        """
        Closes the Router connection created by createSession(). Due to a bug in Ice,
        only one connection is allowed per communicator, so we also destroy the communicator.
        """

        self.__lock.acquire()
        try:
            oldSf = self.__sf
            self.__sf = None

            oldOa = self.__oa
            self.__oa = None

            oldIc = self.__ic
            self.__ic = None

            # Only possible if improperly configured.
            if not oldIc:
                return

            if oldOa:
                try:
                    oldOa.deactivate()
                except exceptions.Exception, e:
                    self.__logger.warning("While deactivating adapter: " + str(e.message))

            self.__previous = Ice.InitializationData()
            self.__previous.properties = oldIc.getProperties().clone()

            oldR = self.__resources
            self.__resources = None
            if oldR != None:
                try:
                    oldR.cleanup()
                except exceptions.Exception, e:
                    self.__logger.warning(
                        "While cleaning up resources: " + str(e))

            try:
                try:
                    if oldSf:
                        oldSf = omero.api.ServiceFactoryPrx.uncheckedCast(oldSf.ice_oneway())
                        oldSf.destroy()
                except Glacier2.SessionNotExistException:
                    # ok. We don't want it to exist
                    pass
                except Ice.ConnectionLostException:
                    # ok. Exception will always be thrown
                    pass
                except Ice.ConnectionRefusedException:
                    # ok. Server probably went down
                    pass
                except Ice.ConnectTimeoutException:
                    # ok. Server probably went down
                    pass
            finally:
                oldIc.destroy()

        finally:
            self.__lock.release()


    def killSession(self):
        """
        Calls closeSession(omero.model.Session) until
        the returned reference count is greater than zero.
        """

        sf = self.sf
        if not sf:
            raise ClientError("No session avaliable")

        s = omero.model.SessionI()
        s.uuid = rstring(sf.ice_getIdentity().name)
        try:
            svc = sf.getSessionService()
        except:
            self.__logger.warning("Cannot get session service for killSession. Using closeSession")
            self.closeSession()
            return
        count = 0
        try:
            r = 1
            while r > 0:
                count += 1
                r = svc.closeSession(s)
        except omero.RemovedSessionException:
            pass
        except:
            self.__logger.warning("Unknown exception while closing all references", exc_info = True)

        # Now the server-side session is dead, call closeSession()
        self.closeSession()
        return count

    # Environment Methods
    # ===========================================================

    def _env(self, method, *args):
        """ Helper method to access session environment"""
        session = self.getSession()
        if not session:
            raise ClientError("No session active")
        a = session.getAdminService()
        u = a.getEventContext().sessionUuid
        s = session.getSessionService()
        m = getattr(s, method)
        return apply(m, (u,)+args)

    def getInput(self, key):
        """
        Retrieves an item from the "input" shared (session) memory.
        """
        return self._env("getInput", key)

    def getOutput(self, key):
        """
        Retrieves an item from the "output" shared (session) memory.
        """
        return self._env("getOutput", key)


    def setInput(self, key, value):
        """
        Sets an item in the "input" shared (session) memory under the given name.
        """
        self._env("setInput", key, value)

    def setOutput(self, key, value):
        """
        Sets an item in the "output" shared (session) memory under the given name.
        """
        self._env("setOutput", key, value)

    def getInputKeys(self):
        """
        Returns a list of keys for all items in the "input" shared (session) memory
        """
        return self._env("getInputKeys")

    def getOutputKeys(self):
        """
        Returns a list of keys for all items in the "output" shared (session) memory
        """
        return self._env("getOutputKeys")

    #
    # Misc.
    #

    def parseAndSetInt(self, data, key, newValue):
        currentValue = data.properties.getProperty(key)
        if not currentValue or len(currentValue) == 0:
            newStr = str(newValue)
            data.properties.setProperty(key, newStr)
            currentValue = newStr
        return currentValue

    def __getattr__(self, name):
        """
        Compatibility layer, which allows calls to getCommunicator() and getSession()
        to be called via self.ic and self.sf
        """
        if name == "ic":
            return self.getCommunicator()
        elif name == "sf":
            return self.getSession()
        else:
            raise AttributeError("Unknown property: " + name)

    #
    # Callback
    #
    def _getCb(self):
        if not self.__oa:
            raise ClientError("No session active; call createSession()")
        obj = self.__oa.find(self.ic.stringToIdentity("ClientCallback/%s" %  self.__uuid))
        if not isinstance(obj, BaseClient.CallbackI):
            raise ClientError("Cannot find CallbackI in ObjectAdapter")
        return obj

    def onHeartbeat(self, myCallable):
        self._getCb().onHeartbeat = myCallable

    def onSessionClosed(self, myCallable):
        self._getCb().onSessionClosed = myCallable

    def onShutdownIn(self, myCallable):
        self._getCb().onShutdownIn = myCallable

    class CallbackI(omero.api.ClientCallback):
        """
        Implemention of ClientCallback which will be added to
        any Session which this instance creates. Note: this client
        should avoid all interaction with the {@link client#lock} since it
        can lead to deadlocks during shutdown. See: ticket:1210
        """

        #
        # Default callbacks
        #
        def _noop(self):
            pass
        def _closeSession(self):
            try:
                self.oa.deactivate();
            except exceptions.Exception, e:
                sys.err.write("On session closed: " + str(e))

        def __init__(self, ic, oa):
            self.ic = ic
            self.oa = oa
            self.onHeartbeat = self._noop
            self.onShutdownIn = self._noop
            self.onSessionClosed = self._noop
        def execute(self, myCallable, action):
            try:
                myCallable()
                self.__logger.debug("ClientCallback %s run", action)
            except:
                try:
                    self.__logger.error("Error performing %s" % action)
                except:
                    print "Error performing %s" % action

        def requestHeartbeat(self, current = None):
            self.execute(self.onHeartbeat, "heartbeat")
        def shutdownIn(self, milliseconds, current = None):
            self.execute(self.onShutdownIn, "shutdown")
        def sessionClosed(self, current = None):
            self.execute(self.onSessionClosed, "sessionClosed")

#
# Other
#

import util.FactoryMap
class ObjectFactory(Ice.ObjectFactory):
    """
    Responsible for instantiating objects during deserialization.
    """

    def __init__(self, pmap = util.FactoryMap.map()):
        self.__m = pmap

    def registerObjectFactory(self, ic):
        for key in self.__m:
            if not ic.findObjectFactory(key):
                ic.addObjectFactory(self,key)

    def create(self, type):
        generator = self.__m[type]
        if generator == None:
            raise ClientError("Unknown type:"+type)
        return generator.next()

    def destroy(self):
        # Nothing to do
        pass

