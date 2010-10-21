#
# blitz_gateway - python bindings and wrappers to access an OMERO blitz server
# 
# Copyright (c) 2007, 2010 Glencoe Software, Inc. All rights reserved.
# 
# This software is distributed under the terms described by the LICENCE file
# you can find at the root of the distribution bundle, which states you are
# free to use it only for non commercial purposes.
# If the file is missing please request a copy by contacting
# jason@glencoesoftware.com.

# Set up the python include paths
import os,sys
THISPATH = os.path.dirname(os.path.abspath(__file__))

from types import IntType, LongType, UnicodeType, ListType, TupleType, StringType, StringTypes
from datetime import datetime
from cStringIO import StringIO
import ConfigParser

import omero
import omero.clients
import Ice
import Glacier2

import traceback
import time
import array

import logging
logger = logging.getLogger('blitz_gateway')

try:
    from PIL import Image, ImageDraw, ImageFont # see ticket:2597
except ImportError:
    try:
        import Image, ImageDraw, ImageFont
    except:
        logger.error('No PIL installed, line plots and split channel will fail!')

from cStringIO import StringIO
from math import sqrt

import omero_Constants_ice  
import omero_ROMIO_ice
from omero.rtypes import *

def omero_type(val):
    """
    Converts rtypes from static factory methods:
      - StringType to rstring
      - UnicodeType to rstring
      - IntType to rint
      - LongType to rlong
    elswere return the argument itself

    @param val: value 
    @return:    matched RType or value
    """
    
    if isinstance(val, StringType):
        return rstring(val)
    elif isinstance(val, UnicodeType):
        return rstring(val.encode('utf-8'))
    elif isinstance(val, IntType):
        return rint(val)
    elif isinstance(val, LongType):
        return rlong(val)
    else:
        return val

class TimeIt (object):
    """
    Decorator to measure the execution time of a function.

    @param level: the level to use for logging
    """
    def __init__ (self, level=logging.DEBUG):
        self._level = level

    def __call__ (self, func):
        def wrapped (*args, **kwargs):
            logger.log(self._level, "timing %s" % (func.func_name))
            now = time.time()
            rv = func(*args, **kwargs)
            logger.log(self._level, "timed %s: %f" % (func.func_name, time.time()-now))
            return rv
        return wrapped

def timeit (func):
    """
    Measures the execution time of a function using time.time() 
    and the a @ function decorator.

    Logs at logging.DEBUG level.
    """
    def wrapped (*args, **kwargs):
        logger.log(self._level, "timing %s" % (func.func_name))
        now = time.time()
        rv = func(*args, **kwargs)
        logger.log(self._level, "timed %s: %f" % (func.func_name, time.time()-now))
        return rv
    return TimeIt()(func)




class BlitzObjectWrapper (object):
    """
    Object wrapper class.
    """
    
    OMERO_CLASS = None
    LINK_CLASS = None
    CHILD_WRAPPER_CLASS = None
    PARENT_WRAPPER_CLASS = None
    
    def __init__ (self, conn=None, obj=None, cache={}, **kwargs):
        self.__bstrap__()
        self._obj = obj
        self._cache = cache
        self._conn = conn
        if conn is None:
            return
        if hasattr(obj, 'id') and obj.id is not None:
            self._oid = obj.id.val
            if not self._obj.loaded:
                try:
                    self._obj = self._conn.getQueryService().get(self._obj.__class__.__name__, self._oid)
                except:
                    print traceback.format_exc()
        self.__prepare__ (**kwargs)

    def __eq__ (self, a):
        return type(a) == type(self) and self._obj.id == a._obj.id and self.getName() == a.getName()

    def __bstrap__ (self):
        pass

    def __prepare__ (self, **kwargs):
        pass

    def __repr__ (self):
        if hasattr(self, '_oid'):
            return '<%s id=%s>' % (self.__class__.__name__, str(self._oid))
        return super(BlitzObjectWrapper, self).__repr__()

    def _getChildWrapper (self):
        if self.CHILD_WRAPPER_CLASS is None:
            raise NotImplementedError
        if type(self.CHILD_WRAPPER_CLASS) is type(''):
            # resolve class
            if hasattr(omero.gateway, self.CHILD_WRAPPER_CLASS):
                self.__class__.CHILD_WRAPPER_CLASS = self.CHILD_WRAPPER_CLASS = getattr(omero.gateway, self.CHILD_WRAPPER_CLASS)
            else: #pragma: no cover
                raise NotImplementedError
        return self.CHILD_WRAPPER_CLASS

    def _getParentWrapper (self):
        if self.PARENT_WRAPPER_CLASS is None:
            raise NotImplementedError
        if type(self.PARENT_WRAPPER_CLASS) is type(''):
            # resolve class
            g = globals()
            if not g.has_key(self.PARENT_WRAPPER_CLASS): #pragma: no cover
                raise NotImplementedError
            self.__class__.PARENT_WRAPPER_CLASS = self.PARENT_WRAPPER_CLASS = g[self.PARENT_WRAPPER_CLASS]
        return self.PARENT_WRAPPER_CLASS

    def __loadedHotSwap__ (self):
        self._obj = self._conn.getContainerService().loadContainerHierarchy(self.OMERO_CLASS, (self._oid,), None)[0]


    def _getParentLink (self):
        p = self.listParents()
        link = self._conn.getQueryService().findAllByQuery("select l from %s as l where l.parent.id=%i and l.child.id=%i" % (p.LINK_CLASS, p.id, self.id), None)
        if len(link):
            return link[0]
        return None

    def _moveLink (self, newParent):
        """ moves this object from the current parent container to a new one """
        p = self.listParents()
        if type(p) == type(newParent):
            link = self._conn.getQueryService().findAllByQuery("select l from %s as l where l.parent.id=%i and l.child.id=%i" % (p.LINK_CLASS, p.id, self.id), None)
            if len(link):
                link[0].parent = newParent._obj
                self._conn.getUpdateService().saveObject(link[0])
                return True
        return False

    def findChildByName (self, name, description=None):
        for c in self.listChildren():
            if c.getName() == name:
                if description is None or omero_type(description) == omero_type(c.getDescription()):
                    return c
        return None

    def getDetails (self):
        if self._obj.loaded:
            return omero.gateway.DetailsWrapper (self._conn, self._obj.getDetails())
        return None
    
    def getDate(self):
        try:
            if self._obj.acquisitionDate.val is not None and self._obj.acquisitionDate.val > 0:
                t = self._obj.acquisitionDate.val
            else:
                t = self._obj.details.creationEvent.time.val
        except:
            t = self._conn.getQueryService().get("Event", self._obj.details.creationEvent.id.val).time.val
        return datetime.fromtimestamp(t/1000)
    
    def save (self):
        self._obj = self._conn.getUpdateService().saveAndReturnObject(self._obj)

    def saveAs (self, details):
        """ Save this object, keeping the object owner the same as the one on provided details """
        if self._conn.isAdmin():
            d = self.getDetails()
            if d.getOwner() and \
                    d.getOwner().omeName == details.getOwner().omeName and \
                    d.getGroup().name == details.getGroup().name:
                return self.save()
            else:
                newConn = self._conn.suConn(details.getOwner().omeName, details.getGroup().name)
                #p = omero.sys.Principal()
                #p.name = details.getOwner().omeName
                #p.group = details.getGroup().name
                #p.eventType = "User"
                #newConnId = self._conn.getSessionService().createSessionWithTimeout(p, 60000)
                #newConn = self._conn.clone()
                #newConn.connect(sUuid=newConnId.getUuid().val)
            clone = self.__class__(newConn, self._obj)
            clone.save()
            self._obj = clone._obj
            return
        else:
            return self.save()

    def canWrite (self):
        return self._conn.canWrite(self._obj)

    def canOwnerWrite (self):
        return self._obj.details.permissions.isUserWrite()
    
    def isOwned(self):
        return (self._obj.details.owner.id.val == self._conn.getEventContext().userId)
    
    def isLeaded(self):
        if self._obj.details.group.id.val in self._conn.getEventContext().leaderOfGroups:
            return True
        return False
    
    def isEditable(self):
        if self.isOwned():
            return True
        elif not self.isPrivate() and not self.isReadOnly():
            return True
        return False
    
    def isPublic(self):
        return self._obj.details.permissions.isWorldRead()
    
    def isShared(self):
        if not self.isPublic():
            return self._obj.details.permissions.isGroupRead()
        return False
    
    def isPrivate(self):
        if not self.isPublic() and not self.isShared():
            return self._obj.details.permissions.isUserRead()
        return False
    
    def isReadOnly(self):
        if self.isPublic() and not self._obj.details.permissions.isWorldWrite():
            return True
        elif self.isShared() and not self._obj.details.permissions.isGroupWrite():
            return True
        elif self.isPrivate() and not self._obj.details.permissions.isUserWrite():
            return True
        return False
    
    #@timeit
    #def getUID (self):
    #    p = self.listParents()
    #    return p and '%s:%s' % (p.getUID(), str(self.id)) or str(self.id)

    #def getChild (self, oid):
    #    q = self._conn.getQueryService()
    #    ds = q.find(self.CHILD_WRAPPER_CLASS.OMERO_CLASS, long(oid))
    #    if ds is not None:
    #        ds = self.CHILD_WRAPPER_CLASS(self._conn, ds)
    #    return ds
    
    def countChildren (self):
        """
        Counts available number of child objects.
        
        @return: Long. The number of child objects available
        """
        
        childw = self._getChildWrapper()
        klass = "%sLinks" % childw().OMERO_CLASS.lower()
        #self._cached_countChildren = len(self._conn.getQueryService().findAllByQuery("from %s as c where c.parent.id=%i" % (self.LINK_CLASS, self._oid), None))
        self._cached_countChildren = self._conn.getContainerService().getCollectionCount(self.OMERO_CLASS, klass, [self._oid], None)[self._oid]
        return self._cached_countChildren

    def countChildren_cached (self):
        """
        countChildren, but caching the first result, useful if you need to call this multiple times in
        a single sequence, but have no way of storing the value between them.
        It is actually a hack to support django template's lack of break in for loops
        
        @return: Long
        """
        
        if not hasattr(self, '_cached_countChildren'):
            return self.countChildren()
        return self._cached_countChildren

    def listChildren (self, ns=None, val=None, params=None):
        """
        Lists available child objects.

        @return: Generator yielding child objects.
        """

        childw = self._getChildWrapper()
        klass = childw().OMERO_CLASS
#        if getattr(self, 'is%sLinksLoaded' % klass)():
#            childns = getattr(self, 'copy%sLinks' % klass)()
#            childnodes = [ x.child for x in childns]
#            logger.debug('listChildren for %s %d: already loaded' % (self.OMERO_CLASS, self.getId()))
#        else:
        if not params:
            params = omero.sys.Parameters()
        if not params.map:
            params.map = {}
        params.map["dsid"] = omero_type(self._oid)
        query = "select c from %s as c" % self.LINK_CLASS
        if ns is not None:
            params.map["ns"] = omero_type(ns)
            #query += """ join c.child.annotationLinks ial
            #             join ial.child as a """
        query += """ join fetch c.child as ch
                     left outer join fetch ch.annotationLinks as ial
                     left outer join fetch ial.child as a """
        query += " where c.parent.id=:dsid"
        if ns is not None:
            query += " and a.ns=:ns"
            if val is not None:
                if isinstance(val, StringTypes):
                    params.map["val"] = omero_type(val)
                    query +=" and a.textValue=:val"
        query += " order by c.child.name"
        childnodes = [ x.child for x in self._conn.getQueryService().findAllByQuery(query, params)]
        for child in childnodes:
            yield childw(self._conn, child, self._cache)

    #def listChildren_cached (self):
    #    """ This version caches all child nodes for all parents, so next parent does not need to search again.
    #    Good for full depth traversal, but a waste of time otherwise """
    #    if self.CHILD_WRAPPER_CLASS is None: #pragma: no cover
    #        raise NotImplementedError
    #    if not self._cache.has_key(self.LINK_CLASS):
    #        pdl = {}
    #        for link in self._conn.getQueryService().findAll(self.LINK_CLASS, None):
    #            pid = link.parent.id.val
    #            if pdl.has_key(pid):
    #                pdl[pid].append(link.child)
    #            else:
    #                pdl[pid] = [link.child]
    #        self._cache[self.LINK_CLASS] = pdl
    #    for child in self._cache[self.LINK_CLASS].get(self._oid, ()):
    #        yield self.CHILD_WRAPPER_CLASS(self._conn, child, self._cache)

    def listParents (self, single=True, withlinks=False):
        """
        Lists available parent objects.
        
        @return: Generator yielding parent objects
        """
        
        if self.PARENT_WRAPPER_CLASS is None:
            if single:
                return withlinks and (None, None) or None
            return ()
        parentw = self._getParentWrapper()
        param = omero.sys.Parameters() # TODO: What can I use this for?
        if withlinks:
            parentnodes = [ (parentw(self._conn, x.parent, self._cache), BlitzObjectWrapper(self._conn, x)) for x in self._conn.getQueryService().findAllByQuery("from %s as c where c.child.id=%i" % (parentw().LINK_CLASS, self._oid), param)]
        else:
            parentnodes = [ parentw(self._conn, x.parent, self._cache) for x in self._conn.getQueryService().findAllByQuery("from %s as c where c.child.id=%i" % (parentw().LINK_CLASS, self._oid), param)]
        if single:
            return len(parentnodes) and parentnodes[0] or None
        return parentnodes


    def getAncestry (self):
        rv = []
        p = self.listParents()
        while p:
            rv.append(p)
            p = p.listParents()
        return rv


    def _loadAnnotationLinks (self):
        if not hasattr(self._obj, 'isAnnotationLinksLoaded'): #pragma: no cover
            raise NotImplementedError
        if not self._obj.isAnnotationLinksLoaded():
            links = self._conn.getQueryService().findAllByQuery("select l from %sAnnotationLink as l join fetch l.child as a where l.parent.id=%i" % (self.OMERO_CLASS, self._oid), None)
            self._obj._annotationLinksLoaded = True
            self._obj._annotationLinksSeq = links


    def _getAnnotationLinks (self, ns=None):
        self._loadAnnotationLinks()
        rv = self.copyAnnotationLinks()
        if ns is not None:
            rv = filter(lambda x: x.getChild().getNs() and x.getChild().getNs().val == ns, rv)
        return rv


    def removeAnnotations (self, ns):
        for al in self._getAnnotationLinks(ns=ns):
            a = al.child
            update = self._conn.getUpdateService()
            update.deleteObject(al)
            update.deleteObject(a)
        self._obj.unloadAnnotationLinks()
    
    def getAnnotation (self, ns=None):
        """
        ets the first annotation in the ns namespace, linked to this object
        
        @return: #AnnotationWrapper or None
        """
        rv = self._getAnnotationLinks(ns)
        if len(rv):
            return AnnotationWrapper._wrap(self._conn, rv[0].child)
        return None

    def listAnnotations (self, ns=None):
        """
        List annotations in the ns namespace, linked to this object
        
        @return: Generator yielding AnnotationWrapper
        """
        
        for ann in self._getAnnotationLinks(ns):
            yield AnnotationWrapper._wrap(self._conn, ann.child, link=ann)


    def _linkAnnotation (self, ann):
        if not ann.getId():
            # Not yet in db, save it
            ann.details.setPermissions(omero.model.PermissionsI())
            ann.details.permissions.setWorldRead(True)
            ann.details.permissions.setGroupWrite(True)
            ann = ann.__class__(self._conn, self._conn.getUpdateService().saveAndReturnObject(ann._obj))
        #else:
        #    ann.save()
        lnktype = "%sAnnotationLinkI" % self.OMERO_CLASS
        lnk = getattr(omero.model, lnktype)()
        lnk.details.setPermissions(omero.model.PermissionsI())
        lnk.details.permissions.setWorldRead(True)
        lnk.details.permissions.setGroupWrite(True)
        lnk.details.permissions.setUserWrite(True)
        lnk.setParent(self._obj.__class__(self._obj.id, False))
        lnk.setChild(ann._obj.__class__(ann._obj.id, False))
        self._conn.getUpdateService().saveObject(lnk)
        return ann


    def linkAnnotation (self, ann, sameOwner=True):
        if sameOwner:
            d = self.getDetails()
            ad = ann.getDetails()
            if self._conn.isAdmin() and self._conn._userid != d.getOwner().id:
                # Keep the annotation owner the same as the linked of object's
                if ad.getOwner() and d.getOwner().omeName == ad.getOwner().omeName and d.getGroup().name == ad.getGroup().name:
                    newConn = ann._conn
                else:
                    #p = omero.sys.Principal()
                    #p.name = d.getOwner().omeName
                    group = None
                    if d.getGroup():
                        group = d.getGroup().name
                    newConn = self._conn.suConn(d.getOwner().omeName, group)
                    #p.eventType = "User"
                    #newConnId = self._conn.getSessionService().createSessionWithTimeout(p, 60000)
                    #newConn = self._conn.clone()
                    #newConn.connect(sUuid=newConnId.getUuid().val)
                clone = self.__class__(newConn, self._obj)
                ann = clone._linkAnnotation(ann)
            elif d.getGroup():
                # Try to match group
                self._conn.setGroupForSession(d.getGroup().getId())
                ann = self._linkAnnotation(ann)
                self._conn.revertGroupForSession()
            else:
                ann = self._linkAnnotation(ann)
        else:
            ann = self._linkAnnotation(ann)
        self.unloadAnnotationLinks()
        return ann


    def simpleMarshal (self, xtra=None, parents=False):
        rv = {'type': self.OMERO_CLASS,
              'id': self.getId(),
              'name': self.getName(),
              'description': self.getDescription(),
              }
        if hasattr(self, '_attrs'):
            # 'key' -> key = _obj[key]
            # '#key' -> key = _obj[key].value.val
            # 'key;title' -> title = _obj[key]
            # 'key|wrapper' -> key = omero.gateway.wrapper(_obj[key]).simpleMarshal
            for k in self._attrs:
                if ';' in k:
                    s = k.split(';')
                    k = s[0]
                    rk = ';'.join(s[1:])
                else:
                    rk = k
                rk = rk.replace('#', '')
                if '|' in k:
                    s = k.split('|')
                    k2 = s[0]
                    w = '|'.join(s[1:])
                    if rk == k:
                        rk = k2
                    k = k2
                    
                    v = getattr(self, k)
                    if v is not None:
                        v = getattr(omero.gateway, w)(self._conn, v).simpleMarshal()
                else:
                    if k.startswith('#'):
                        v = getattr(self, k[1:])
                        if v is not None:
                            v = v._value
                    else:
                        v = getattr(self, k)
                    if hasattr(v, 'val'):
                        v = v.val
                rv[rk] = v
        if xtra: # TODO check if this can be moved to a more specific place
            if xtra.has_key('childCount'):
                rv['child_count'] = self.countChildren()
        if parents:
            rv['parents'] = map(lambda x: x.simpleMarshal(), self.getAncestry())
        return rv

    #def __str__ (self):
    #    if hasattr(self._obj, 'value'):
    #        return str(self.value)
    #    return str(self._obj)

    def __getattr__ (self, attr):
        if attr != 'get' and attr.startswith('get') and hasattr(self, '_attrs'):
            tattr = attr[3].lower() + attr[4:]
            attrs = filter(lambda x: tattr in x, self._attrs)
            for a in attrs:
                if a.startswith('#') and a[1:] == tattr:  
                    # Broken code here
                    v = getattr(self, tattr)
                    if v is not None:
                        v = v._value
                    def wrap ():
                        return v
                    return wrap
                if len(a) > len(tattr) and a[len(tattr)] == '|':
                    def wrap ():
                        return getattr(omero.gateway, a[len(tattr)+1:])(self._conn, getattr(self, tattr))
                    return wrap
        if not hasattr(self._obj, attr) and hasattr(self._obj, '_'+attr):
            attr = '_' + attr
        if hasattr(self._obj, attr):
            rv = getattr(self._obj, attr)
            if hasattr(rv, 'val'):
                return isinstance(rv.val, StringType) and rv.val.decode('utf8') or rv.val
            return rv
        raise AttributeError("'%s' object has no attribute '%s'" % (self._obj.__class__.__name__, attr))


    # some methods are accessors in _obj and return and omero:: type. The obvious ones we wrap to return a python type
    
    def getId (self):
        """
        Gets this object ID
        
        @return: Long or None
        """
        oid = self._obj.getId()
        if oid is not None:
            return oid.val
        return None

    def getName (self):
        """
        Gets this object name
        
        @return: String or None
        """
        if hasattr(self._obj, 'name'):
            if hasattr(self._obj.name, 'val'):
                return self._obj.getName().val
            else:
                return self._obj.getName()
        else:
            return None

    def getDescription (self):
        """
        Gets this object description
        
        @return: String
        """
        
        rv = hasattr(self._obj, 'description') and self._obj.getDescription() or None
        return rv and rv.val or ''

    def getOwner (self):
        """
        Gets user who is the owner of this object.
        
        @return: _ExperimenterWrapper
        """
        
        return self.getDetails().getOwner()

    def getOwnerFullName (self):
        """
        Gets full name of the owner of this object.
        
        @return: String or None
        """
        
        try:
            lastName = self.getDetails().getOwner().lastName
            firstName = self.getDetails().getOwner().firstName
            middleName = self.getDetails().getOwner().middleName
            
            if middleName is not None and middleName != '':
                name = "%s %s. %s" % (firstName, middleName, lastName)
            else:
                name = "%s %s" % (firstName, lastName)
            return name
        except:
            logger.error(traceback.format_exc())
            return None

    def getOwnerOmeName (self):
        """
        Gets omeName of the owner of this object.
        
        @return: String
        """
        return self.getDetails().getOwner().omeName

    def creationEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when object was created.
        
        @return: Long
        """
        
        try:
            if self._obj.details.creationEvent.time is not None:
                t = self._obj.details.creationEvent.time.val
            else:
                t = self._conn.getQueryService().get("Event", self._obj.details.creationEvent.id.val).time.val
        except:
            t = self._conn.getQueryService().get("Event", self._obj.details.creationEvent.id.val).time.val
        return datetime.fromtimestamp(t/1000)

    def updateEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when object was updated.
        
        @return: Long
        """
        
        try:
            if self._obj.details.updateEvent.time is not None:
                t = self._obj.details.updateEvent.time.val
            else:
                t = self._conn.getQueryService().get("Event", self._obj.details.updateEvent.id.val).time.val
        except:
            t = self._conn.getQueryService().get("Event", self._obj.details.updateEvent.id.val).time.val
        return datetime.fromtimestamp(t/1000)


    # setters are also provided
    
    def setName (self, value):
        self._obj.setName(omero_type(value))

    def setDescription (self, value):
        self._obj.setDescription(omero_type(value))

## BASIC ##

class NoProxies (object):
    def __getitem__ (self, k):
        raise Ice.ConnectionLostException

class _BlitzGateway (object):
    """
    ICE_CONFIG - Defines the path to the Ice configuration
    """
    
    ICE_CONFIG = None#os.path.join(p,'etc/ice.config')
#    def __init__ (self, username, passwd, server, port, client_obj=None, group=None, clone=False):
    
    def __init__ (self, username=None, passwd=None, client_obj=None, group=None, clone=False, try_super=False, host=None, port=None, extra_config=[], secure=False, useragent=None):
        """
        TODO: Constructor
        
        @param username:    User name. String
        @param passwd:      Password. String
        @param client_obj:  omero.client 
        @param group:       admin group
        @param clone:       Boolean
        @param try_super:   Boolean
        @param host:        Omero server host. String
        @param port:        Omero server port. Integer
        @param extra_config:
        @param secure:      Initial underlying omero.client connection type (True=SSL/False=insecure)
        """
        
        super(_BlitzGateway, self).__init__()
        self.client = client_obj
        if not type(extra_config) in (type(()), type([])):
            extra_config=[extra_config]
        self.extra_config = extra_config
        self.ice_config = [self.ICE_CONFIG]
        self.ice_config.extend(extra_config)
        self.ice_config = map(lambda x: str(x), filter(None, self.ice_config))

        self.host = host
        self.port = port
        self.secure = secure
        self.useragent = useragent
        
        self._resetOmeroClient()
        if not username:
            username = self.c.ic.getProperties().getProperty('omero.gateway.anon_user')
            passwd = self.c.ic.getProperties().getProperty('omero.gateway.anon_pass')
        #logger.debug('super: %s %s %s' % (try_super, str(group), self.c.ic.getProperties().getProperty('omero.gateway.admin_group')))
        if try_super:
            self.group = 'system' #self.c.ic.getProperties().getProperty('omero.gateway.admin_group')
        else:
            self.group = group and group or None
        self._sessionUuid = None
        self._session_cb = None
        self._session = None
        self._lastGroupId = None
        self._anonymous = True

        # The properties we are setting through the interface
        self.setIdentity(username, passwd, not clone)

        self._connected = False
        self._user = None
        self._userid = None
        self._proxies = NoProxies()

    def getProperty(self, k):
        return self.c.getProperty(k)

    def clone (self):
        return self.__class__(self._ic_props[omero.constants.USERNAME],
                              self._ic_props[omero.constants.PASSWORD],
                              host = self.host,
                              port = self.port,
                              extra_config=self.extra_config,
                              clone=True,
                              secure=self.secure)
                              #self.server, self.port, clone=True)

    def setIdentity (self, username, passwd, _internal=False):
        """
        TODO: description
        
        @param username:    User name. String
        @param passwd:      Password. String
        @param _internal:   Boolean
        """
        
        self._ic_props = {omero.constants.USERNAME: username,
                          omero.constants.PASSWORD: passwd}
        self._anonymous = _internal
    
    def suConn (self, username, group=None, ttl=60000):
        """ If current user isAdmin, return new connection owned by 'username' """
        if self.isAdmin():
            if group is None:
                e = self.lookupExperimenter(username)
                if e is None:
                    return
                group = e._obj._groupExperimenterMapSeq[0].parent.name.val
            p = omero.sys.Principal()
            p.name = username
            p.group = group
            p.eventType = "User"
            newConnId = self.getSessionService().createSessionWithTimeout(p, ttl)
            newConn = self.clone()
            newConn.connect(sUuid=newConnId.getUuid().val)
            return newConn

    def keepAlive (self):
        """
        Keeps service alive. 
        Returns True if connected. If connection was lost, reconnecting.
        
        @return:    Boolean
        """
        
        try:
            if self.c.sf is None: #pragma: no cover
                logger.debug('... c.sf is None, reconnecting')
                return self.connect()
            return self.c.sf.keepAlive(self._proxies['admin']._obj)
        except Ice.ObjectNotExistException: #pragma: no cover
            # The connection is there, but it has been reset, because the proxy no longer exists...
            logger.debug(traceback.format_exc())
            logger.debug("... reset, not reconnecting")
            return False
        except Ice.ConnectionLostException: #pragma: no cover
            # The connection was lost. This shouldn't happen, as we keep pinging it, but does so...
            logger.debug(traceback.format_exc())
            logger.debug("... lost, reconnecting")
            #return self.connect()
            return False
        except Ice.ConnectionRefusedException: #pragma: no cover
            # The connection was refused. We lost contact with glacier2router...
            logger.debug(traceback.format_exc())
            logger.debug("... refused, not reconnecting")
            return False
        except omero.SessionTimeoutException: #pragma: no cover
            # The connection is there, but it has been reset, because the proxy no longer exists...
            logger.debug(traceback.format_exc())
            logger.debug("... reset, not reconnecting")
            return False
        except omero.RemovedSessionException: #pragma: no cover
            # Session died on us
            logger.debug(traceback.format_exc())
            logger.debug("... session has left the building, not reconnecting")
            return False
        except Ice.UnknownException, x: #pragma: no cover
            # Probably a wrapped RemovedSession
            logger.debug(traceback.format_exc())
            logger.debug('Ice.UnknownException: %s' % str(x))
            logger.debug("... ice says something bad happened, not reconnecting")
            return False
        except:
            # Something else happened
            logger.debug(traceback.format_exc())
            logger.debug("... error not reconnecting")
            return False
        
    def seppuku (self, softclose=False): #pragma: no cover
        """
        Terminates connection. If softclose is False, the session is really
        terminate disregarding its connection refcount. 
        
        @param softclose:   Boolean
        """
        
        self._connected = False
        if self.c:
            try:
                self.c.sf.closeOnDestroy()
            except:
                pass
            try:
                if softclose:
                    try:
                        r = self.c.sf.getSessionService().getReferenceCount(self._sessionUuid)
                        self.c.closeSession()
                        if r < 2:
                            self._session_cb and self._session_cb.close(self)
                    except Ice.OperationNotExistException:
                        self.c.closeSession()
                else:
                    self._closeSession()
            except:
                pass 
            self.c = None
        self._proxies = NoProxies()
        logger.info("closed connecion (uuid=%s)" % str(self._sessionUuid))

    def __del__ (self):
        logger.debug("##GARBAGE COLLECTOR KICK IN")
    
    def _createProxies (self):
        """
        Creates proxies to the server services.
        """
        
        if not isinstance(self._proxies, NoProxies):
            logger.debug("## Reusing proxies")
            for k, p in self._proxies.items():
                p._resyncConn(self)
        else:
            logger.debug("## Creating proxies")
            self._proxies = {}
            self._proxies['admin'] = ProxyObjectWrapper(self, 'getAdminService')
            self._proxies['config'] = ProxyObjectWrapper(self, 'getConfigService')
            self._proxies['container'] = ProxyObjectWrapper(self, 'getContainerService')
            self._proxies['delete'] = ProxyObjectWrapper(self, 'getDeleteService')
            self._proxies['export'] = ProxyObjectWrapper(self, 'createExporter')
            self._proxies['ldap'] = ProxyObjectWrapper(self, 'getLdapService')
            self._proxies['metadata'] = ProxyObjectWrapper(self, 'getMetadataService')
            self._proxies['query'] = ProxyObjectWrapper(self, 'getQueryService')
            self._proxies['pixel'] = ProxyObjectWrapper(self, 'getPixelsService')
            self._proxies['projection'] = ProxyObjectWrapper(self, 'getProjectionService')
            self._proxies['rawpixels'] = ProxyObjectWrapper(self, 'createRawPixelsStore')
            self._proxies['rendering'] = ProxyObjectWrapper(self, 'createRenderingEngine')
            self._proxies['rendsettings'] = ProxyObjectWrapper(self, 'getRenderingSettingsService')
            self._proxies['rawfile'] = ProxyObjectWrapper(self, 'createRawFileStore')
            self._proxies['repository'] = ProxyObjectWrapper(self, 'getRepositoryInfoService')
            self._proxies['roi'] = ProxyObjectWrapper(self, 'getRoiService')
            self._proxies['script'] = ProxyObjectWrapper(self, 'getScriptService')
            self._proxies['search'] = ProxyObjectWrapper(self, 'createSearchService')
            self._proxies['session'] = ProxyObjectWrapper(self, 'getSessionService')
            self._proxies['share'] = ProxyObjectWrapper(self, 'getShareService')
            self._proxies['thumbs'] = ProxyObjectWrapper(self, 'createThumbnailStore')
            self._proxies['timeline'] = ProxyObjectWrapper(self, 'getTimelineService')
            self._proxies['types'] = ProxyObjectWrapper(self, 'getTypesService')
            self._proxies['update'] = ProxyObjectWrapper(self, 'getUpdateService')
            
        self._ctx = self._proxies['admin'].getEventContext()
        if self._ctx is not None:
            self._userid = self._ctx.userId
            # "guest" user has no access that method.
            self._user = self._ctx.userName!="guest" and self.getExperimenter(self._userid) or None
        else:
            self._userid = None
            self._user = None
        
        if self._session_cb: #pragma: no cover
            if self._was_join:
                self._session_cb.join(self)
            else:
                self._session_cb.create(self)

    def setSecure (self, secure=True):
        """ Switches between SSL and insecure (faster) connections to Blitz.
        The gateway must already be connected. """
        if hasattr(self.c, 'createClient') and (secure ^ self.c.isSecure()):
            self.c = self.c.createClient(secure=secure)
            self._createProxies()
            self.secure = secure
    
    def isSecure (self):
        """ Returns 'True' if the underlying omero.clients.BaseClient is connected using SSL """
        return hasattr(self.c, 'isSecure') and self.c.isSecure() or False

    def _createSession (self, skipSUuid=False):
        """
        Creates a new session for the principal given in the constructor.
        """
        s = self.c.createSession(self._ic_props[omero.constants.USERNAME],
                                 self._ic_props[omero.constants.PASSWORD])
        self._sessionUuid = self.c.sf.ice_getIdentity().name
        ss = self.c.sf.getSessionService()
        self._session = ss.getSession(self._sessionUuid)
        self._lastGroupId = None
        s.detachOnDestroy()
        self._was_join = False
        if self.group is not None:
            # try something that fails if the user don't have permissions on the group
            self.c.sf.getAdminService().getEventContext()
        self.setSecure(self.secure)
    
    def _closeSession (self):
        """
        Close session.
        """
        
        self._session_cb and self._session_cb.close(self)
        if self._sessionUuid:
            s = omero.model.SessionI()
            s._uuid = omero_type(self._sessionUuid)
            try:
                #r = 1
                #while r:
                #    r = self.c.sf.getSessionService().closeSession(s)
                # it is not neccessary to go through every workers.
                # if cannot get session service for killSession will use closeSession
                self.c.killSession()
            except Ice.ObjectNotExistException:
                pass
            except omero.RemovedSessionException:
                pass
            except ValueError:
                raise
            except: #pragma: no cover
                logger.warn(traceback.format_exc())
        else:
            try:
                self.c.killSession()
            except Glacier2.SessionNotExistException: #pragma: no cover
                pass
            except:
                logger.warn(traceback.format_exc())
        
    def _resetOmeroClient (self):
        """
        Resets omero.client object.
        """
        
        if self.host is not None:
            self.c = omero.client(host=str(self.host), port=int(self.port))#, pmap=['--Ice.Config='+','.join(self.ice_config)])
        else:
            self.c = omero.client(pmap=['--Ice.Config='+','.join(self.ice_config)])

        if hasattr(self.c, "setAgent"):
            if self.useragent is not None:
                self.c.setAgent(self.useragent)
            else:
                self.c.setAgent("OMERO.py.gateway")
                
    def connect (self, sUuid=None):
        """
        Creates or retrieves connection for the given sessionUuid.
        Returns True if connected.
        
        @param sUuid:   omero_model_SessionI
        @return:        Boolean
        """
        
        logger.debug("Connect attempt, sUuid=%s, group=%s, self.sUuid=%s" % (str(sUuid), str(self.group), self._sessionUuid))
        if not self.c: #pragma: no cover
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
                        logger.debug("was connected, creating new omero.client")
                        self._resetOmeroClient()
                    s = self.c.joinSession(self._sessionUuid)
                    s.detachOnDestroy()
                    logger.debug('joinSession(%s)' % self._sessionUuid)
                    self._was_join = True
                except Ice.SyscallException: #pragma: no cover
                    raise
                except Exception, x: #pragma: no cover
                    logger.debug("Error: " + str(x))
                    self._sessionUuid = None
                    if sUuid:
                        return False
            if self._sessionUuid is None:
                if sUuid: #pragma: no cover
                    logger.debug("Uncaptured sUuid failure!") 
                if self._connected:
                    self._connected = False
                    try:
                        #args = self.c._ic_args
                        #logger.debug(str(args))
                        self._closeSession()
                        self._resetOmeroClient()
                        #self.c = omero.client(*args)
                    except Glacier2.SessionNotExistException: #pragma: no cover
                        pass
                setprop = self.c.ic.getProperties().setProperty
                map(lambda x: setprop(x[0],str(x[1])), self._ic_props.items())
                if self._anonymous:
                    self.c.ic.getImplicitContext().put(omero.constants.EVENT, 'Internal')
                if self.group is not None:
                    self.c.ic.getImplicitContext().put(omero.constants.GROUP, self.group)
                try:
                    self._createSession()
                except omero.SecurityViolation:
                    if self.group is not None:
                        # User don't have access to group
                        logger.debug("## User not in '%s' group" % self.group)
                        self.group = None
                        self._closeSession()
                        self._sessionUuid = None
                        self._connected=True
                        return self.connect()
                    else: #pragma: no cover
                        logger.debug("BlitzGateway.connect().createSession(): " + traceback.format_exc())
                        logger.info('first create session threw SecurityViolation, hold off 10 secs and retry (but only once)')
                        #time.sleep(10)
                        try:
                            self._createSession()
                        except omero.SecurityViolation:
                            if self.group is not None:
                                # User don't have access to group
                                logger.debug("## User not in '%s' group" % self.group)
                                self.group = None
                                self._connected=True
                                return self.connect()
                            else:
                                raise
                except Ice.SyscallException: #pragma: no cover
                    raise
                except:
                    logger.info("BlitzGateway.connect().createSession(): " + traceback.format_exc())
                    logger.debug(str(self._ic_props))
                    #time.sleep(10)
                    self._createSession()

            self._last_error = None
            self._createProxies()
            self._connected = True
            logger.info('created connection (uuid=%s)' % str(self._sessionUuid))
        except Ice.SyscallException: #pragma: no cover
            logger.debug('This one is a SyscallException')
            raise
        except Ice.LocalException, x: #pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        except Exception, x: #pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        logger.debug(".. connected!")
        return True

    def getLastError (self): #pragma: no cover
        """
        Returns error if thrown by _BlitzGateway.connect connect.
        
        @return: String
        """
        
        return self._last_error

    def isConnected (self):
        """
        Returns last status of connection.
        
        @return:    Boolean
        """
        
        return self._connected

    ######################
    ## Connection Stuff ##

    def getEventContext (self):
        """
        Returns omero_System_ice.EventContext.
        It containes:: 
            shareId, sessionId, sessionUuid, userId, userName, 
            groupId, groupName, isAdmin, isReadOnly, 
            eventId, eventType, eventType,
            memberOfGroups, leaderOfGroups
        
        @return: omero.sys.EventContext
        """
        
        self._ctx = self._proxies['admin'].getEventContext()
        return self._ctx

    def getUser (self):
        """
        Returns current omero_model_ExperimenterI.
         
        @return:    omero.model.ExperimenterI
        """
        
        return self._user
    
    def getGroupFromContext(self):
        """
        Returns current omero_model_ExperimenterGroupI.
         
        @return:    omero.model.ExperimenterGroupI
        """
        
        admin_service = self.getAdminService()
        group = admin_service.getGroup(self.getEventContext().groupId)
        return ExperimenterGroupWrapper(self, group)
    
    def isAdmin (self):
        """
        Checks if a user has administration privileges.
        
        @return:    Boolean
        """
        
        return self.getEventContext().isAdmin
    
    def canBeAdmin (self):
        """
        Checks if a user is in system group, i.e. can have administration privileges.
        
        @return:    Boolean
        """
        return 0 in self.getEventContext().memberOfGroups

    def isOwner (self, gid=None):
        """
        Checks if a user has owner privileges.
        
        @return:    Boolean
        """
        if not isinstance(gid, LongType) or not isinstance(gid, IntType):
            gid = long(gid)
        if gid is not None:
            for gem in self._user.copyGroupExperimenterMap():
                if gem.parent.id.val == gid and gem.owner.val == True:
                    return True
        else:
            for gem in self._user.copyGroupExperimenterMap():
                if gem.owner.val == True:
                    return True
        return False
    
    def canWrite (self, obj):
        """
        Checks if a user has write privileges to the given object.
        
        @param obj: Given object
        @return:    Boolean
        """
        
        return self.isAdmin() or (self._userid == obj.details.owner.id.val and obj.details.permissions.isUserWrite())

    def getSession (self):
        if self._session is None:
            ss = self.c.sf.getSessionService()
            self._session = ss.getSession(self._sessionUuid)
        return self._session

#    def setDefaultPermissionsForSession (self, permissions):
#        self.getSession()
#        self._session.setDefaultPermissions(rstring(permissions))
#        self._session.setTimeToIdle(None)
#        self.getSessionService().updateSession(self._session)

    def setGroupNameForSession (self, group):
        a = self.getAdminService()
        g = a.lookupGroup(group)
        return self.setGroupForSession(g.getId().val)

    def setGroupForSession (self, groupid):
        if self.getEventContext().groupId == groupid:
            return True
        if groupid not in self._ctx.memberOfGroups:
            return False
        self._lastGroupId = self._ctx.groupId
        if hasattr(self.c, 'setSecurityContext'):
            # Beta4.2
            self.c.sf.setSecurityContext(omero.model.ExperimenterGroupI(groupid, False))
        else:
            self.getSession()
            self._session.getDetails().setGroup(omero.model.ExperimenterGroupI(groupid, False))
            self._session.setTimeToIdle(None)
            self.getSessionService().updateSession(self._session)
        return True


#    def setGroupForSession (self, group):
#        self.getSession()
#        if self._session.getDetails().getGroup().getId().val == group.getId():
#            # Already correct
#            return
#        a = self.getAdminService()
#        if not group.name in [x.name.val for x in a.containedGroups(self._userid)]:
#            # User not in this group
#            return
#        self._lastGroup = self._session.getDetails().getGroup()
#        self._session.getDetails().setGroup(group._obj)
#        self._session.setTimeToIdle(None)
#        self.getSessionService().updateSession(self._session)
#
    def revertGroupForSession (self):
        if self._lastGroupId is not None:
            self.setGroupForSession(self._lastGroupId)
            self._lastGroupId = None

    ##############
    ## Services ##

    def getAdminService (self):
        """
        Gets reference to the admin service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['admin']

    def getQueryService (self):
        """
        Gets reference to the query service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['query']

    def getContainerService (self):
        """
        Gets reference to the container service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['container']

    def getPixelsService (self):
        """
        Gets reference to the pixels service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['pixel']
    
    def getMetadataService (self):
        """
        Gets reference to the metadata service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['metadata']
    
    def getRoiService (self):
        """
        Gets ROI service.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['roi']
        
    def getScriptService (self):
        """
        Gets script service.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['script']
        
    def createRawFileStore (self):
        """
        Creates a new raw file store.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rawfile']

    def getRepositoryInfoService (self):
        """
        Gets reference to the repository info service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['repository']

    def getShareService(self):
        """
        Gets reference to the share service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['share']

    def getTimelineService (self):
        """
        Gets reference to the timeline service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['timeline']
    
    def getTypesService(self):
        """
        Gets reference to the types service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['types']

    def getConfigService (self):
        """
        Gets reference to the config service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['config']

    def createRenderingEngine (self):
        """
        Creates a new rendering engine.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        rv = self._proxies['rendering']
        if rv._tainted:
            rv = self._proxies['rendering'] = rv.clone()
        rv.taint()
        return rv

    def getRenderingSettingsService (self):
        """
        Gets reference to the rendering settings service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rendsettings']
   
    def createRawPixelsStore (self):
        """
        Creates a new raw pixels store.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rawpixels']

    def createThumbnailStore (self):
        """
        Gets a reference to the thumbnail store on this connection object or creates a new one
        if none exists.
        
        @rtype: omero.gateway.ProxyObjectWrapper
        @return: The proxy wrapper of the thumbnail store
        """
        
        return self._proxies['thumbs']
    
    def createSearchService (self):
        """
        Creates a new search service.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return: omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['search']

    def getUpdateService (self):
        """
        Gets reference to the update service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['update']

    def getDeleteService (self):
        """
        Gets reference to the delete service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['delete']

    def getSessionService (self):
        """
        Gets reference to the session service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['session']

    def createExporter (self):
        """
        New instance of non cached Exporter, wrapped in ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['export']

    #############################
    # Top level object fetchers #
    
    def listProjects (self, only_owned=False):
        """
        List every Projects controlled by the security system.
        
        @param only_owned:  Only owned by the logged user. Boolean.
        @return:            Generator yielding _ProjectWrapper
        """
        
        q = self.getQueryService()
        cache = {}
        if only_owned:
            params = omero.sys.Parameters()
            params.map = {'owner_id': rlong(self._userid)}
            for e in q.findAllByQuery("from Project as p where p.details.owner.id=:owner_id order by p.name", params):
                yield ProjectWrapper(self, e, cache)
        else:
            for e in q.findAll('Project', None):
                yield ProjectWrapper(self, e, cache)

#    def listCategoryGroups (self):
#        q = self.getQueryService()
#        cache = {}
#        for e in q.findAll("CategoryGroup", None):
#            yield CategoryGroupWrapper(self, e, cache)


    #################################################
    ## IAdmin
    
    # GROUPS
    
    def getGroup(self, gid):
        """ Fetch an Group and all contained users."""
        
        admin_service = self.getAdminService()
        group = admin_service.getGroup(long(gid))
        return ExperimenterGroupWrapper(self, group)
    
    def lookupGroup(self, name):
        """ Look up an Group and all contained users by name."""
        
        admin_service = self.getAdminService()
        group = admin_service.lookupGroup(str(name))
        return ExperimenterGroupWrapper(self, group)
    
    def getDefaultGroup(self, eid):
        """ Retrieve the default group for the given user id."""
        
        admin_serv = self.getAdminService()
        dgr = admin_serv.getDefaultGroup(long(eid))
        return ExperimenterGroupWrapper(self, dgr)
    
    def getOtherGroups(self, eid):
        """ Fetch all groups of which the given user is a member. 
            The returned groups will have all fields filled in and all collections unloaded."""
        
        admin_serv = self.getAdminService()
        for gr in admin_serv.containedGroups(long(eid)):
            yield ExperimenterGroupWrapper(self, gr)
        
    def getGroupsLeaderOf(self):
        """ Look up Groups where current user is a leader of."""
        
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["ids"] = rlist([rlong(a) for a in self.getEventContext().leaderOfGroups])
        sql = "select e from ExperimenterGroup as e where e.id in (:ids)"
        for e in q.findAllByQuery(sql, p):
            yield ExperimenterGroupWrapper(self, e)

    def getGroupsMemberOf(self):
        """ Look up Groups where current user is a member of (except "user")."""
        
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["ids"] = rlist([rlong(a) for a in self.getEventContext().memberOfGroups])
        sql = "select e from ExperimenterGroup as e where e.id in (:ids)"
        for e in q.findAllByQuery(sql, p):
            if e.name.val == "user":
                pass
            else:
                yield ExperimenterGroupWrapper(self, e)

    # EXPERIMENTERS
        
    def lookupExperimenters(self):
        """ Look up all experimenters all related groups.
            The experimenters are also loaded."""
        
        admin_serv = self.getAdminService()
        for exp in admin_serv.lookupExperimenters():
            yield ExperimenterWrapper(self, exp)
    
    def getExperimenter(self, eid):
        """
        Return an Experimenter for the given ID.
        
        @param eid: User ID.
        @return:    _ExperimenterWrapper or None
        """
        
        admin_serv = self.getAdminService()
        try:
            exp = admin_serv.getExperimenter(long(eid))
            return ExperimenterWrapper(self, exp)
        except omero.ApiUsageException:
            return None

    def lookupExperimenter(self, name):
        """
        Return an Experimenter for the given username.
        
        @param name:    Username. String
        @return:        _ExperimenterWrapper or None
        """
        
        admin_serv = self.getAdminService()
        try:
            exp = admin_serv.lookupExperimenter(str(name))
            return ExperimenterWrapper(self, exp)
        except omero.ApiUsageException:
            return None
            
    def containedExperimenters(self, gid):
        """ Fetch all users contained in this group. 
            The returned users will have all fields filled in and all collections unloaded."""
        
        admin_serv = self.getAdminService()
        for exp in admin_serv.containedExperimenters(long(gid)):
            yield ExperimenterWrapper(self, exp)
    
    def getColleagues(self):
        """ Look up users who are a member of the current user active group."""
        
        a = self.getAdminService()
        default = self.getAdminService().getGroup(self.getEventContext().groupId)
        for d in default.copyGroupExperimenterMap():
            if d.child.id.val != self.getEventContext().userId:
                yield ExperimenterWrapper(self, d.child)

    def getStaffs(self):
        """ Look up users who are a member of the group owned by the current user."""
        
        q = self.getQueryService()
        gr_list = list()
        gr_list.extend(self.getEventContext().leaderOfGroups)
        p = omero.sys.Parameters()
        p.map = {}
        p.map["gids"] = rlist([rlong(a) for a in set(gr_list)])
        sql = "select e from Experimenter as e where " \
                "exists ( select gem from GroupExperimenterMap as gem where gem.child = e.id and gem.parent.id in (:gids)) order by e.omeName"
        for e in q.findAllByQuery(sql, p):
            if e.id.val != self.getEventContext().userId:
                yield ExperimenterWrapper(self, e)

    def getColleaguesAndStaffs(self):
        """ Look up users who are a member of the current user active group 
            and users who are a member of the group owned by the current user."""
        
        q = self.getQueryService()
        gr_list = list()
        gr_list.extend(self.getEventContext().memberOfGroups)
        gr_list.extend(self.getEventContext().leaderOfGroups)
        p = omero.sys.Parameters()
        p.map = {}
        p.map["gids"] = rlist([rlong(a) for a in set(gr_list)])
        sql = "select e from Experimenter as e where " \
                "exists ( select gem from GroupExperimenterMap as gem where gem.child = e.id and gem.parent.id in (:gids)) order by e.omeName"
        for e in q.findAllByQuery(sql, p):
            if e.id.val != self.getEventContext().userId:
                yield ExperimenterWrapper(self, e)
    
    def lookupGroups(self):
        """ Looks up all groups and all related experimenters. 
            The experimenters' groups are also loaded."""
            
        admin_serv = self.getAdminService()
        for gr in admin_serv.lookupGroups():
            yield ExperimenterGroupWrapper(self, gr)
    
    def lookupOwnedGroups(self):
        """ Looks up owned groups for the logged user. """
            
        exp = self.getUser()
        for gem in exp.copyGroupExperimenterMap():
            if gem.owner.val:
                yield ExperimenterGroupWrapper(self, gem.parent)
    
    # Repository info
    def getUsedSpace(self):
        """ Returns the total space in bytes for this file system
            including nested subdirectories. """
        
        rep_serv = self.getRepositoryInfoService()
        return rep_serv.getUsedSpaceInKilobytes() * 1024
    
    def getFreeSpace(self):
        """ Returns the free or available space on this file system
            including nested subdirectories. """
        
        rep_serv = self.getRepositoryInfoService()
        return rep_serv.getFreeSpaceInKilobytes() * 1024
    
    def getUsage(self):
        """ Returns list of users and how much space each of them use."""
       
        query_serv = self.getQueryService()
        usage = dict()
        if self.getUser().isAdmin():
            admin_serv = self.getAdminService()
            groups = admin_serv.lookupGroups()
            for group in groups:
                for gem in group.copyGroupExperimenterMap():
                    exp = gem.child
                    res = query_serv.projection("""
                    select o.id, sum(p.sizeX * p.sizeY * p.sizeZ * p.sizeC * p.sizeT), p.pixelsType.value 
                    from Pixels p join p.details.owner o 
                    group by o.id, p.pixelsType.value
                    """, None, {"omero.group":str(group.id.val)})
                    rv = unwrap(res)
                    for r in rv:
                        if usage.has_key(r[0]):
                            usage[r[0]] += r[1]*self.bytesPerPixel(r[2])
                        else:
                            usage[r[0]] = r[1]*self.bytesPerPixel(r[2])
        else:
            groups = self.getEventContext().memberOfGroups
            groups.extend(self.getEventContext().leaderOfGroups)
            groups = set(groups)
            for gid in groups:
                res = query_serv.projection("""
                select o.id, sum(p.sizeX * p.sizeY * p.sizeZ * p.sizeC * p.sizeT), p.pixelsType.value 
                from Pixels p join p.details.owner o 
                group by o.id, p.pixelsType.value
                """, None, {"omero.group":str(gid)})
                rv = unwrap(res)
                for r in rv:
                    if usage.has_key(gid):
                        usage[gid] += r[1]*self.bytesPerPixel(r[2])
                    else:
                        usage[gid] = r[1]*self.bytesPerPixel(r[2])
        return usage
    
    def bytesPerPixel(self, pixel_type):
        if pixel_type == "int8" or pixel_type == "uint8":
            return 1
        elif pixel_type == "int16" or pixel_type == "uint16":
            return 2
        elif pixel_type == "int32" or pixel_type == "uint32" or pixel_type == "float":
            return 4
        elif pixel_type == "double":
            return 8;
        else:
            logger.error("Error: Unknown pixel type: %s" % (pixel_type))
            logger.error(traceback.format_exc())
            raise AttributeError("Unknown pixel type: %s" % (pixel_type))
    
    ##############################################
    ##   IShare
    
    def getOwnShares(self):
        """ Gets all owned shares for the current user. """
        
        sh = self.getShareService()
        for e in sh.getOwnShares(False):
            yield ShareWrapper(self, e)
    
    def getMemberShares(self):
        """ Gets all shares where current user is a member. """
        
        sh = self.getShareService()
        for e in sh.getMemberShares(False):
            yield ShareWrapper(self, e)
    
    def getMemberCount(self, share_ids):
        """ Returns a map from share id to the count of total members (including the
            owner). This is represented by ome.model.meta.ShareMember links."""
        
        sh = self.getShareService()
        return sh.getMemberCount(share_ids)
    
    def getCommentCount(self, share_ids):
        """ Returns a map from share id to comment count. """
        
        sh = self.getShareService()
        return sh.getCommentCount(share_ids)
    
    def getContents(self, share_id):
        """ Looks up all items belong to the share."""
        
        sh = self.getShareService()
        for e in sh.getContents(long(share_id)):
            yield ShareContentWrapper(self, e)
    
    def getComments(self, share_id):
        """ Looks up all comments which belong to the share."""
        
        sh = self.getShareService()
        for e in sh.getComments(long(share_id)):
            yield ShareCommentWrapper(self, e)
    
    def getAllMembers(self, share_id):
        """ Get all {@link Experimenter users} who are a member of the share."""
        
        sh = self.getShareService()
        for e in sh.getAllMembers(long(share_id)):
            yield ExperimenterWrapper(self, e)

    def getAllGuests(self, share_id):
        """ Get the email addresses for all share guests."""
        
        sh = self.getShareService()
        return sh.getAllGuests(long(share_id))

    def getAllUsers(self, share_id):
        """ Get a single set containing the login names of the users as well email addresses for guests."""
        
        sh = self.getShareService()
        return sh.getAllUsers(long(share_id))
    
    ############################
    # ITimeline                #

    def timelineListImages (self, tfrom=None, tto=None, limit=10, only_owned=True):
        """
        List images based on the their creation times.
        If both tfrom and tto are None, grab the most recent batch.
        
        @param tfrom: milliseconds since the epoch for start date
        @param tto: milliseconds since the epoch for end date
        @param tlimit: maximum number of results
        @param only_owned:  Only owned by the logged user. Boolean.
        @return:            Generator yielding _ImageWrapper
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
            for e in tm.getByPeriod(['Image'], rtime(long(tfrom)), rtime(long(tto)), p, False)['Image']:
                yield ImageWrapper(self, e)


    ###########################
    # Specific Object Getters #

    def getProject (self, oid):
        """
        Return Project for the given ID.
        
        @param oid: Project ID.
        @return:    _ProjectWrapper or None
        """
        
        q = self.getQueryService()
        pr = q.find("Project", long(oid))
        if pr is not None:
            pr = ProjectWrapper(self, pr)
        return pr
    
    def findProject (self, name):
        """
        Return Project with the given name.
        
        @param name: Project name.
        @return:    _ProjectWrapper or None
        """
        q = self.getQueryService()
        params = omero.sys.Parameters()
        if not params.map:
            params.map = {}
        params.map['name'] = rstring(name)
        pr = q.findAllByQuery("from Project as p where p.name=:name", params)
        if len(pr):
            return ProjectWrapper(self, pr[0])
        return None

    def getDataset (self, oid):
        """
        Return Dataset for the given ID.
        
        @param oid: Dataset ID.
        @return:    _DatasetWrapper or None
        """
        
        q = self.getQueryService()
        ds = q.find("Dataset", long(oid))
        if ds is not None:
            ds = DatasetWrapper(self, ds)
        return ds

    def getImage (self, oid):
        """
        Return Image for the given ID.
        
        @param oid: Image ID.
        @return:    _ImageWrapper or None
        """
        
        q = self.getQueryService()
        img = q.find("Image", long(oid))
        if img is not None:
            img = ImageWrapper(self, img)
        return img
    
    def getShare (self, oid):
        """ Gets share for the given share id. """
        
        sh_serv = self.getShareService()
        sh = sh_serv.getShare(long(oid))
        if sh is not None:
            return ShareWrapper(self, sh)
        else:
            return None
    
    def getScreen (self, oid):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["oid"] = rlong(long(oid))
        sql = "select sc from Screen sc join fetch sc.details.owner join fetch sc.details.group where sc.id=:oid "
        sc = query_serv.findByQuery(sql,p)
        if sc is not None:
            return ScreenWrapper(self, sc)
        else:
            return None
    
    def getPlate (self, oid):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["oid"] = rlong(long(oid))
        sql = "select pl from Plate pl join fetch pl.details.owner join fetch pl.details.group " \
              "left outer join fetch pl.screenLinks spl " \
              "left outer join fetch spl.parent sc where pl.id=:oid "
        pl = query_serv.findByQuery(sql,p)
        if pl is not None:
            return PlateWrapper(self, pl)
        else:
            return None
    
    def getSpecifiedImages(self, oids):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["ids"] = rlist([rlong(a) for a in oids])
        sql = "select im from Image im join fetch im.details.owner join fetch im.details.group where im.id in (:ids) order by im.name"
        for e in query_serv.findAllByQuery(sql, p):
            yield ImageWrapper(self, e)

    def getSpecifiedDatasets(self, oids):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["ids"] = rlist([rlong(a) for a in oids])
        sql = "select ds from Dataset ds join fetch ds.details.owner join fetch ds.details.group where ds.id in (:ids) order by ds.name"
        for e in query_serv.findAllByQuery(sql, p):
            yield DatasetWrapper(self, e) 
    
    def getSpecifiedProjects(self, oids):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["ids"] = rlist([rlong(a) for a in oids])
        sql = "select pr from Project pr join fetch pr.details.owner join fetch pr.details.group where pr.id in (:ids) order by pr.name"
        for e in query_serv.findAllByQuery(sql, p):
            yield ProjectWrapper(self, e)
    
    def getSpecifiedPlates(self, oids):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["ids"] = rlist([rlong(a) for a in oids])
        sql = "select pl from Plate pl join fetch pl.details.owner join fetch pl.details.group where pl.id in (:ids) order by pl.name"
        for e in query_serv.findAllByQuery(sql, p):
            yield DatasetWrapper(self, e)
    
    #################################
    # Annotations                   #
    
    def getFileAnnotation (self, oid):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["oid"] = rlong(long(oid))
        sql = "select f from FileAnnotation f join fetch f.file where f.id = :oid"
        of = query_serv.findByQuery(sql, p)
        return FileAnnotationWrapper(self, of)
    
    def getCommentAnnotation (self, oid):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["oid"] = rlong(long(oid))
        sql = "select ca from CommentAnnotation ca where ca.id = :oid"
        ta = query_serv.findByQuery(sql, p)
        return AnnotationWrapper(self, ta)
    
    def getTagAnnotation (self, oid):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["oid"] = rlong(long(oid))
        sql = "select tg from TagAnnotation tg where tg.id = :oid"
        tg = query_serv.findByQuery(sql, p)
        return AnnotationWrapper(self, tg)
    
    def lookupTagAnnotation (self, name):
        query_serv = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {} 
        p.map["text"] = rstring(str(name))
        p.map["eid"] = rlong(self.getEventContext().userId)
        f = omero.sys.Filter()
        f.limit = rint(1)
        p.theFilter = f
        sql = "select tg from TagAnnotation tg " \
              "where tg.textValue=:text and tg.details.owner.id=:eid and tg.ns is null order by tg.textValue"
        tg = query_serv.findByQuery(sql, p)
        return AnnotationWrapper(self, tg)
    
    ##############################
    # Annotation based iterators #
    
    def listImages (self, ns, params=None):
        """
        TODO: description
        
        @return:    Generator yielding _ImageWrapper
        """
        
        if not params:
            params = omero.sys.Parameters()
        if not params.map:
            params.map = {}
        params.map["ns"] = omero_type(ns)
        query = """
                 select i
                   from Image i
                   join i.annotationLinks ial
                   join ial.child as a
                   where a.ns = :ns
                   order by a.id desc """
        for i in self.getQueryService().findAllByQuery(query, params):
            yield ImageWrapper(self, i)

    
    ################
    # Enumerations #
    
    def getEnumerationEntries(self, klass):
        types = self.getTypesService()
        for e in types.allEnumerations(str(klass)):
            yield EnumerationWrapper(self, e)
    
    def getEnumeration(self, klass, string):
        types = self.getTypesService()
        obj = types.getEnumeration(str(klass), str(string))
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None
    
    def getEnumerationById(self, klass, eid):
        query_serv = self.getQueryService()
        obj =  query_serv.find(klass, long(eid))
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None
            
    def getOriginalEnumerations(self):
        types = self.getTypesService()
        rv = dict()
        for e in types.getOriginalEnumerations():
            if rv.get(e.__class__.__name__) is None:
                rv[e.__class__.__name__] = list()
            rv[e.__class__.__name__].append(EnumerationWrapper(self, e))
        return rv
        
    def getEnumerations(self):
        types = self.getTypesService()
        return types.getEnumerationTypes() 
    
    def getEnumerationsWithEntries(self):
        types = self.getTypesService()
        rv = dict()
        for key, value in types.getEnumerationsWithEntries().items():
            r = list()
            for e in value:
                r.append(EnumerationWrapper(self, e))
            rv[key+"I"] = r
        return rv
    
    def deleteEnumeration(self, obj):
        types = self.getTypesService()
        types.deleteEnumeration(obj)
        
    def createEnumeration(self, obj):
        types = self.getTypesService()
        types.createEnumeration(obj)
    
    def resetEnumerations(self, klass):
        types = self.getTypesService()
        types.resetEnumerations(klass)
    
    def updateEnumerations(self, new_entries):
        types = self.getTypesService()
        types.updateEnumerations(new_entries)
    
    
    ###################
    # Searching stuff #


    #def searchImages (self, text):
    #    """
    #    Fulltext search for images
    #    """
    #    return self.simpleSearch(text,(ImageWrapper,))
    
    def searchImages (self, text=None, created=None):
        search = self.createSearchService()
        search.onlyType('Image')
        search.addOrderByAsc("name")
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text:
           search.setAllowLeadingWildcard(True)
           search.byFullText(str(text))
        if search.hasNext():
            for e in search.results():
                yield ImageWrapper(self, e)

    def searchDatasets (self, text=None, created=None):
        search = self.createSearchService()
        search.onlyType('Dataset')
        search.addOrderByAsc("name")
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text:
           search.setAllowLeadingWildcard(True)
           search.byFullText(str(text))
        
        if search.hasNext():
            for e in search.results():
                yield DatasetWrapper(self, e)
        

    def searchProjects (self, text=None, created=None):
        search = self.createSearchService()
        search.onlyType('Project')
        search.addOrderByAsc("name")
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text:
           search.setAllowLeadingWildcard(True)
           search.byFullText(str(text))
        if search.hasNext():
            for e in search.results():
                yield ProjectWrapper(self, e)
    
    def searchScreens (self, text=None, created=None):
        search = self.createSearchService()
        search.onlyType('Screen')
        search.addOrderByAsc("name")
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text:
           search.setAllowLeadingWildcard(True)
           search.byFullText(str(text))
        if search.hasNext():
            for e in search.results():
                yield ScreenWrapper(self, e)
    
    def searchPlates (self, text=None, created=None):
        search = self.createSearchService()
        search.onlyType('Plate')
        search.addOrderByAsc("name")
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text:
           search.setAllowLeadingWildcard(True)
           search.byFullText(str(text))
        if search.hasNext():
            for e in search.results():
                yield PlateWrapper(self, e)

    def simpleSearch (self, text, types=None):
        """
        Fulltext search on Projects, Datasets and Images.
        TODO: search other object types?
        TODO: batch support.
        """
        if not text:
            return []
        if isinstance(text, UnicodeType):
            text = text.encode('utf8')
        if types is None:
            types = (ProjectWrapper, DatasetWrapper, ImageWrapper)
        search = self.createSearchService()
        if text[0] in ('?','*'):
            search.setAllowLeadingWildcard(True)
        rv = []
        for t in types:
            def actualSearch ():
                search.onlyType(t().OMERO_CLASS)
                search.byFullText(text)
            timeit(actualSearch)()
            if search.hasNext():
                def searchProcessing ():
                    rv.extend(map(lambda x: t(self, x), search.results()))
                timeit(searchProcessing)()
        search.close()
        return rv

def safeCallWrap (self, attr, f): #pragma: no cover
    """
    Captures called function. Throws an exception.
    
    @return:
    """
    
    def inner (*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except omero.ResourceError:
            logger.debug('captured resource error')
            raise
        except omero.SecurityViolation:
            raise
        except omero.ApiUsageException:
            raise
        except Ice.MemoryLimitException:
            raise
        except omero.InternalException:
            raise
        except Ice.Exception, x:
            # Failed
            logger.debug( "Ice.Exception (1) on safe call %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            # Recreate the proxy object
            try:
                self._obj = self._create_func()
                func = getattr(self._obj, attr)
                return func(*args, **kwargs)
            except Ice.MemoryLimitException:
                raise
            except Ice.Exception, x:
                # Still Failed
                logger.debug("Ice.Exception (2) on safe call %s(%s,%s)" % (attr, str(args), str(kwargs)))
                logger.debug(traceback.format_exc())
                try:
                    # Recreate connection
                    self._connect()
                    logger.debug('last try for %s' % attr)
                    # Last try, don't catch exception
                    func = getattr(self._obj, attr)
                    return func(*args, **kwargs)
                except:
                    raise

    def wrapped (*args, **kwargs): #pragma: no cover
        try:
            return inner(*args, **kwargs)
        except Ice.MemoryLimitException:
            logger.debug("MemoryLimitException! abort, abort...")
            raise
        except omero.SecurityViolation:
            logger.debug("SecurityViolation, bailing out")
            raise
        except omero.ApiUsageException:
            logger.debug("ApiUsageException, bailing out")
            raise
        except Ice.UnknownException:
            logger.debug("UnknownException, bailing out")
            raise
        except Ice.Exception, x:
            logger.debug('wrapped ' + f.func_name)
            logger.debug(x.__dict__)
            if x.serverExceptionClass == 'ome.conditions.InternalException':
                if x.message.find('java.lang.NullPointerException') > 0:
                    logger.debug("NullPointerException, bailing out")
                    raise
                elif x.message.find('Session is dirty') >= 0:
                    logger.debug("Session is dirty, bailing out")
                    raise
                else:
                    logger.debug(x.message)
            logger.debug("exception caught, first time we back off for 10 secs")
            logger.debug(traceback.format_exc())
            #time.sleep(10)
            return inner(*args, **kwargs)
    return wrapped


BlitzGateway = _BlitzGateway


def splitHTMLColor (color):
    """ splits an hex stream of characters into an array of bytes in format (R,G,B,A).
    - abc      -> (0xAA, 0xBB, 0xCC, 0xFF)
    - abcd     -> (0xAA, 0xBB, 0xCC, 0xDD)
    - abbccd   -> (0xAB, 0xBC, 0xCD, 0xFF)
    - abbccdde -> (0xAB, 0xBC, 0xCD, 0xDE)
    """
    try:
        out = []
        if len(color) in (3,4):
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
    def __init__ (self, conn, func_str):
        self._obj = None
        self._func_str = func_str
        self._resyncConn(conn)
        self._tainted = False
    
    def clone (self):
        return ProxyObjectWrapper(self._conn, self._func_str)

    def _connect (self): #pragma: no cover
        """
        Returns True if connected.
        
        @return:    Boolean
        """
        
        logger.debug("proxy_connect: a");
        if not self._conn.connect():
            logger.debug('connect failed')
            logger.debug('/n'.join(traceback.format_stack()))
            return False
        logger.debug("proxy_connect: b");
        self._resyncConn(self._conn)
        logger.debug("proxy_connect: c");
        self._obj = self._create_func()
        logger.debug("proxy_connect: d");
        return True

    def taint (self):
        self._tainted = True

    def untaint (self):
        self._tainted = False

    def close (self):
        """
        Closes the underlaying service, so next call to the proxy will create a new
        instance of it.
        """
        
        if self._obj:
            self._obj.close()
        self._obj = None
    
    def _resyncConn (self, conn):
        """
        
        @param conn:    Connection
        """
        
        self._conn = conn
        self._sf = conn.c.sf
        self._create_func = getattr(self._sf, self._func_str)
        if self._obj is not None:
            try:
                logger.debug("## - refreshing %s" % (self._func_str))
                obj = conn.c.ic.stringToProxy(str(self._obj))
                self._obj = self._obj.checkedCast(obj)
            except Ice.ObjectNotExistException:
                self._obj = None

    def _getObj (self):
        """
        
        @return:    obj
        """
        if not self._obj:
            self._obj = self._create_func()
        else:
            self._ping()
        return self._obj

    def _ping (self): #pragma: no cover
        """
        For some reason, it seems that keepAlive doesn't, so every so often I need to recreate the objects.
        
        @return:    Boolean
        """
        
        try:
            if not self._sf.keepAlive(self._obj):
                logger.debug("... died, recreating ...")
                self._obj = self._create_func()
        except Ice.ObjectNotExistException:
            # The connection is there, but it has been reset, because the proxy no longer exists...
            logger.debug("... reset, reconnecting")
            self._connect()
            return False
        except Ice.ConnectionLostException:
            # The connection was lost. This shouldn't happen, as we keep pinging it, but does so...
            logger.debug(traceback.format_stack())
            logger.debug("... lost, reconnecting")
            self._conn._connected = False
            self._connect()
            return False
        except Ice.ConnectionRefusedException:
            # The connection was refused. We lost contact with glacier2router...
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

    def __getattr__ (self, attr):
        """
        
        @param attr:    Connection
        @return: rv
        """
        # safe call wrapper
        obj = self._obj or self._getObj()
        rv = getattr(obj, attr)
        if callable(rv):
            rv = safeCallWrap(self, attr, rv)
        #self._conn.updateTimeout()
        return rv


class AnnotationWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationI class wrapper extends BlitzObjectWrapper.
    """
    registry = {}
    OMERO_TYPE = None

    def __init__ (self, *args, **kwargs):
        super(AnnotationWrapper, self).__init__(*args, **kwargs)
        self.link = kwargs.has_key('link') and kwargs['link'] or None
        if self._obj is None and self.OMERO_TYPE is not None:
            self._obj = self.OMERO_TYPE()

    def __eq__ (self, a):
        return type(a) == type(self) and self._obj.id == a._obj.id and self.getValue() == a.getValue() and self.getNs() == a.getNs()

    @classmethod
    def _register (klass, regklass):
        klass.registry[regklass.OMERO_TYPE] = regklass

    @classmethod
    def _wrap (klass, conn, obj, link=None):
        if obj.__class__ in klass.registry:
            kwargs = dict()
            if link is not None:
                kwargs['link'] = BlitzObjectWrapper(conn, link)
            return klass.registry[obj.__class__](conn, obj, **kwargs)
        else: #pragma: no cover
            return None

    @classmethod
    def createAndLink (klass, target, ns, val=None):
        this = klass()
        this.setNs(ns)
        if val is not None:
            this.setValue(val)
        target.linkAnnotation(this)

    def getNs (self):
        return self._obj.ns is not None and self._obj.ns.val or None

    def setNs (self, val):
        self._obj.ns = omero_type(val)
    
    def getValue (self): #pragma: no cover
        raise NotImplementedError

    def setValue (self, val): #pragma: no cover
        raise NotImplementedError

from omero_model_FileAnnotationI import FileAnnotationI

class FileAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_FileAnnotatio class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = FileAnnotationI

    def __loadedHotSwap__ (self):
        if not self._obj.file.loaded:
            self._obj._file = self._conn.getQueryService().find('OriginalFile', self._obj.file.id.val)

    def getValue (self):
        pass

    def setValue (self, val):
        pass

    def isOriginalMetadata(self):
        self.__loadedHotSwap__()
        try:
            if self._obj.ns is not None and self._obj.ns.val == omero.constants.namespaces.NSCOMPANIONFILE and self._obj.file.name.val.startswith("original_metadata"):
                return True
        except:
            logger.info(traceback.format_exc())
        return False
     
    def getFileSize(self):
        return self._obj.file.size.val
    
    def getFileName(self):
        self.__loadedHotSwap__()
        return self._obj.file.name.val
    
    def getFileInChunks(self):
        self.__loadedHotSwap__()
        store = self._conn.createRawFileStore()
        store.setFileId(self._obj.file.id.val)
        size = self.getFileSize()
        buf = 2621440
        if size <= buf:
            yield store.read(0,long(size))
        else:
            for pos in range(0,long(size),buf):
                data = None
                if size-pos < buf:
                    data = store.read(pos, size-pos)
                else:
                    data = store.read(pos, buf)
                yield data
        store.close()
    
#    def shortTag(self):
#        if isinstance(self._obj, TagAnnotationI):
#            try:
#                name = self._obj.textValue.val
#                l = len(name)
#                if l < 25:
#                    return name
#                return name[:10] + "..." + name[l - 10:] 
#            except:
#                logger.info(traceback.format_exc())
#                return self._obj.textValue.val

AnnotationWrapper._register(FileAnnotationWrapper)

from omero_model_TimestampAnnotationI import TimestampAnnotationI

class TimestampAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TimestampAnnotatio class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = TimestampAnnotationI

    def getValue (self):
        return datetime.fromtimestamp(self._obj.timeValue.val / 1000.0)

    def setValue (self, val):
        if isinstance(val, datetime):
            self._obj.timeValue = rtime(long(time.mktime(val.timetuple())*1000))
        elif isinstance(val, omero.RTime):
            self._obj.timeValue = val
        else:
            self._obj.timeValue = rtime(long(val * 1000))

AnnotationWrapper._register(TimestampAnnotationWrapper)

from omero_model_BooleanAnnotationI import BooleanAnnotationI

class BooleanAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = BooleanAnnotationI

    def getValue (self):
        return self._obj.boolValue.val

    def setValue (self, val):
        self._obj.boolValue = rbool(not not val)

AnnotationWrapper._register(BooleanAnnotationWrapper)

from omero_model_TagAnnotationI import TagAnnotationI

class TagAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = TagAnnotationI

    def getValue (self):
        return self._obj.textValue.val

    def setValue (self, val):
        self._obj.textValue = rbool(not not val)
    
AnnotationWrapper._register(TagAnnotationWrapper)

from omero_model_CommentAnnotationI import CommentAnnotationI

class CommentAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_CommentAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = CommentAnnotationI

    def getValue (self):
        return self._obj.textValue.val

    def setValue (self, val):
        self._obj.textValue = omero_type(val)

AnnotationWrapper._register(CommentAnnotationWrapper)

from omero_model_LongAnnotationI import LongAnnotationI

class LongAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_LongAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = LongAnnotationI

    def getValue (self):
        return self._obj.longValue.val

    def setValue (self, val):
        self._obj.longValue = rlong(val)

AnnotationWrapper._register(LongAnnotationWrapper)

from omero_model_DoubleAnnotationI import DoubleAnnotationI

class DoubleAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_DoubleAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = DoubleAnnotationI

    def getValue (self):
        return self._obj.doubleValue.val

    def setValue (self, val):
        self._obj.doubleValue = rdouble(val)

AnnotationWrapper._register(DoubleAnnotationWrapper)

from omero_model_TermAnnotationI import TermAnnotationI

class TermAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TermAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = TermAnnotationI

    def getValue (self):
        return self._obj.termValue.val

    def setValue (self, val):
        self._obj.termValue = rstring(val)

AnnotationWrapper._register(TermAnnotationWrapper)

from omero_model_XmlAnnotationI import XmlAnnotationI

class XmlAnnotationWrapper (CommentAnnotationWrapper):
    """
    omero_model_XmlAnnotationI class wrapper extends CommentAnnotationWrapper.
    """
    OMERO_TYPE = XmlAnnotationI
    
AnnotationWrapper._register(XmlAnnotationWrapper)

class _EnumerationWrapper (BlitzObjectWrapper):
    
    def getType(self):
        return self._obj.__class__

EnumerationWrapper = _EnumerationWrapper

class _ExperimenterWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterI class wrapper extends BlitzObjectWrapper.
    """

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Experimenter'
        self.LINK_CLASS = "copyGroupExperimenterMap"
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'ExperimenterGroupWrapper'

    def simpleMarshal (self, xtra=None, parents=False):
        rv = super(_ExperimenterWrapper, self).simpleMarshal(xtra=xtra, parents=parents)
        rv.update({'firstName': self.firstName,
                   'middleName': self.middleName,
                   'lastName': self.lastName,
                   'email': self.email,
                   'isAdmin': len(filter(lambda x: x.name.val == 'system', self._conn.getAdminService().containedGroups(self.getId()))) == 1,
                   })
        return rv

    def getRawPreferences (self):
        """ Returns the experiments preferences annotation contents, as a ConfigParser instance """
        self._obj.unloadAnnotationLinks()
        cp = ConfigParser.SafeConfigParser()
        prefs = self.getAnnotation('TODO.changeme.preferences')
        if prefs is not None:
            prefs = prefs.getValue()
            if prefs is not None:
                cp.readfp(StringIO(prefs))
        return cp

    def setRawPreferences (self, prefs):
        """ Sets the experiments preferences annotation contents, passed in as a ConfigParser instance """
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
    
    def getPreference (self, key, default='', section=None):
        if section is None:
            section = 'DEFAULT'
        try:
            return self.getRawPreferences().get(section, key)
        except ConfigParser.Error:
            return default
        return default

    def getPreferences (self, section=None):
        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if prefs.has_section(section) or section == 'DEFAULT':
            return dict(prefs.items(section))
        return {}

    def setPreference (self, key, value, section=None):
        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if not section in prefs.sections():
            prefs.add_section(section)
        prefs.set(section, key, value)
        self.setRawPreferences(prefs)

    def getDetails (self):
        if not self._obj.details.owner:
            details = omero.model.DetailsI()
            details.owner = self._obj
            self._obj._details = details
        return DetailsWrapper(self._conn, self._obj.details)

    def getName (self):
        return self.omeName

    def getDescription (self):
        return self.getFullName()

    def getFullName (self):
        """
        Gets full name of this experimenter.
        
        @return: String or None
        """
        
        try:
            if self.middleName is not None and self.middleName != '':
                name = "%s %s. %s" % (self.firstName, self.middleName[:1].upper(), self.lastName)
            else:
                name = "%s %s" % (self.firstName, self.lastName)
        except:
            logger.error(traceback.format_exc())
            name = self.omeName
        return name
    
    def getNameWithInitial(self):
        try:
            if self.firstName is not None and self.lastName is not None:
                name = "%s. %s" % (self.firstName[:1], self.lastName)
            else:
                name = self.omeName
        except:
            logger.error(traceback.format_exc())
            name = self.omeName
        return name
    
    def isAdmin(self):
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "system":
                return True
        return False
    
    def isActive(self):
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "user":
                return True
        return False
    
    def isGuest(self):
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "guest":
                return True
        return False
    
ExperimenterWrapper = _ExperimenterWrapper

class _ExperimenterGroupWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterGroupI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'ExperimenterGroup'
        self.LINK_CLASS = "copyGroupExperimenterMap"
        self.CHILD_WRAPPER_CLASS = 'ExperimenterWrapper'
        self.PARENT_WRAPPER_CLASS = None

    def isLeader(self):
        if self._conn.getEventContext().groupId in self._conn.getEventContext().leaderOfGroups:
            return True
        return False

ExperimenterGroupWrapper = _ExperimenterGroupWrapper

class DetailsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetailsI class wrapper extends BlitzObjectWrapper.
    """
    
    def __init__ (self, *args, **kwargs):
        super(DetailsWrapper, self).__init__ (*args, **kwargs)
        owner = self._obj.getOwner()
        group = self._obj.getGroup()
        self._owner = owner and ExperimenterWrapper(self._conn, self._obj.getOwner()) or None
        self._group = group and ExperimenterGroupWrapper(self._conn, self._obj.getGroup()) or None

    def getOwner (self):
        return self._owner

    def getGroup (self):
        return self._group

class _DatasetWrapper (BlitzObjectWrapper):
    """
    omero_model_DatasetI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Dataset'
        self.LINK_CLASS = "DatasetImageLink"
        self.CHILD_WRAPPER_CLASS = 'ImageWrapper'
        self.PARENT_WRAPPER_CLASS = 'ProjectWrapper'

    def __loadedHotSwap__ (self):
        super(_DatasetWrapper, self).__loadedHotSwap__()
        if not self._obj.isImageLinksLoaded():
            links = self._conn.getQueryService().findAllByQuery("select l from DatasetImageLink as l join fetch l.child as a where l.parent.id=%i" % (self._oid), None)
            self._obj._imageLinksLoaded = True
            self._obj._imageLinksSeq = links

DatasetWrapper = _DatasetWrapper

class _ProjectWrapper (BlitzObjectWrapper):
    """
    omero_model_ProjectI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Project'
        self.LINK_CLASS = "ProjectDatasetLink"
        self.CHILD_WRAPPER_CLASS = 'DatasetWrapper'
        self.PARENT_WRAPPER_CLASS = None

ProjectWrapper = _ProjectWrapper

class _ScreenWrapper (BlitzObjectWrapper):
    
    annotation_counter = None
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Screen'
        self.LINK_CLASS = "ScreenPlateLink"
        self.CHILD_WRAPPER_CLASS = 'PlateWrapper'
        self.PARENT_WRAPPER_CLASS = None

ScreenWrapper = _ScreenWrapper

class _PlateWrapper (BlitzObjectWrapper):
    
    annotation_counter = None
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Plate'
        self.LINK_CLASS = None
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'ScreenWrapper'

PlateWrapper = _PlateWrapper

class _WellWrapper (BlitzObjectWrapper):
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Well'
        self.LINK_CLASS = "WellSample"
        self.CHILD_WRAPPER_CLASS = "ImageWrapper"
        self.PARENT_WRAPPER_CLASS = 'PlateWrapper'
    
    def __prepare__ (self, **kwargs):
        try:
            self.index = int(kwargs['index'])
        except:
            self.index = 0
    
    def isWellSample (self):
        """ return boolean if object exist """
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            if len(childnodes) > 0:
                return True
        return False
    
    def countWellSample (self):
        """ return boolean if object exist """
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('countChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            size = len(childnodes)
            if size > 0:
                return size
        return 0
    
    def selectedWellSample (self):
        """ return a wrapped child object """
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listSelectedChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            if len(childnodes) > 0:
                return WellSampleWrapper(self._conn, childnodes[self.index])
        return None
    
    def loadWellSamples (self):
        """ return a generator yielding child objects """
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            for ch in childnodes:
                yield WellSampleWrapper(self._conn, ch)
    
    def plate(self):
        return PlateWrapper(self._conn, self._obj.plate)

WellWrapper = _WellWrapper

class _WellSampleWrapper (BlitzObjectWrapper):
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'WellSample'
        self.CHILD_WRAPPER_CLASS = "ImageWrapper"
        self.PARENT_WRAPPER_CLASS = 'WellWrapper'
        
    def image(self):
        return ImageWrapper(self._conn, self._obj.image)

WellSampleWrapper = _WellSampleWrapper

class _ShareWrapper (BlitzObjectWrapper):
    
    def getStartDate(self):
        return datetime.fromtimestamp(self.getStarted().val/1000)
        
    def getExpirationDate(self):
        try:
            return datetime.fromtimestamp((self.getStarted().val+self.getTimeToLive().val)/1000)
        except ValueError:
            pass
        return None
    
    def isExpired(self):
        try:
            if (self.getStarted().val+self.getTimeToLive().val)/1000 <= time.time():
                return True
            else:
                return False
        except:
            return True
    
    def isOwned(self):
        if self.owner.id.val == self._conn.getEventContext().userId:
            return True
        else:
            return False
    
    def getOwner(self):
        return omero.gateway.ExperimenterWrapper(self, self.owner)

ShareWrapper = _ShareWrapper

class ShareContentWrapper (BlitzObjectWrapper):
    pass

class ShareCommentWrapper (AnnotationWrapper):
    pass

## IMAGE ##

class ColorHolder (object):
    """
    Stores color internally as (R,G,B,A) and allows setting and getting in multiple formats
    """
    
    _color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}

    def __init__ (self, colorname=None):
        self._color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}
        if colorname and colorname.lower() in self._color.keys():
            self._color[colorname.lower()] = 255

    @classmethod
    def fromRGBA(klass,r,g,b,a):
        rv = klass()
        rv.setRed(r)
        rv.setGreen(g)
        rv.setBlue(b)
        rv.setAlpha(a)
        return rv

    def getRed (self):
        return self._color['red']

    def setRed (self, val):
        """
        Set red, as int 0..255 
        
        @param val: value of Red.
        """
        
        self._color['red'] = max(min(255, int(val)), 0)

    def getGreen (self):
        return self._color['green']

    def setGreen (self, val):
        """
        Set green, as int 0..255 
        
        @param val: value of Green.
        """
        
        self._color['green'] = max(min(255, int(val)), 0)

    def getBlue (self):
        return self._color['blue']

    def setBlue (self, val):
        """
        Set Blue, as int 0..255 
        
        @param val: value of Blue.
        """
        
        self._color['blue'] = max(min(255, int(val)), 0)

    def getAlpha (self):
        return self._color['alpha']

    def setAlpha (self, val):
        """
        Set alpha, as int 0..255.
        @param val: value of alpha.
        """
        
        self._color['alpha'] = max(min(255, int(val)), 0)

    def getHtml (self):
        """
        @return: String. The html usable color. Dumps the alpha information.
        """
        
        return "%(red)0.2X%(green)0.2X%(blue)0.2X" % (self._color)

    def getCss (self):
        """
        @return: String. rgba(r,g,b,a) for this color.
        """
        
        c = self._color.copy()
        c['alpha'] /= 255.0
        return "rgba(%(red)i,%(green)i,%(blue)i,%(alpha)0.3f)" % (c)

    def getRGB (self):
        """
        @return: list. A list of (r,g,b) values
        """
        
        return (self._color['red'], self._color['green'], self._color['blue'])

class _LogicalChannelWrapper (BlitzObjectWrapper):
    """
    omero_model_LogicalChannelI class wrapper extends BlitzObjectWrapper.
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
              'lightPath|LightPathWrapper',              
              'samplesPerPixel',
              '#photometricInterpretation',
              'mode',
              'pockelCellSetting',
              'shapes',
              'version')

LogicalChannelWrapper = _LogicalChannelWrapper    

class _LightPathWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('dichroic|DichroicWrapper')
    #       'copyEmissionFilter|FilterWrapper',
    #       'copyExcitationFilter|FilterWrapper',
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'LightPath'

    def copyEmissionFilters(self):
        pass

    def copyExcitationFilters(self):
        pass
        
LightPathWrapper = _LightPathWrapper

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

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Channel'

    def __prepare__ (self, idx=-1, re=None, img=None):
        self._re = re
        self._idx = idx
        self._img = img

    def save (self):
        self._obj.setPixels(omero.model.PixelsI(self._obj.getPixels().getId(), False))
        return super(_ChannelWrapper, self).save()

    def isActive (self):
        return self._re.isActive(self._idx)

    def getLogicalChannel (self):
        if self._obj.logicalChannel is not None:
            return LogicalChannelWrapper(self._conn, self._obj.logicalChannel)
    
    def getEmissionWave (self):
        lc = self.getLogicalChannel()
        rv = lc.name
        if rv is None:
            rv = lc.emissionWave
        if rv is None:
            rv = self._idx
        return rv

    def getColor (self):
        return ColorHolder.fromRGBA(*self._re.getRGBA(self._idx))

    def getWindowStart (self):
        return int(self._re.getChannelWindowStart(self._idx))

    def setWindowStart (self, val):
        self.setWindow(val, self.getWindowEnd())

    def getWindowEnd (self):
        return int(self._re.getChannelWindowEnd(self._idx))

    def setWindowEnd (self, val):
        self.setWindow(self.getWindowStart(), val)

    def setWindow (self, minval, maxval):
        self._re.setChannelWindow(self._idx, float(minval), float(maxval))

    def getWindowMin (self):
        return self._obj.getStatsInfo().getGlobalMin().val

    def getWindowMax (self):
        return self._obj.getStatsInfo().getGlobalMax().val

ChannelWrapper = _ChannelWrapper

def assert_re (func):
    def wrapped (self, *args, **kwargs):
        if not self._prepareRenderingEngine():
            return None
        return func(self, *args, **kwargs)
    return wrapped

def assert_pixels (func):
    def wrapped (self, *args, **kwargs):
        if not self._loadPixels():
            return None
        return func(self, *args, **kwargs)
    return wrapped


class _ImageWrapper (BlitzObjectWrapper):
    """
    omero_model_ImageI class wrapper extends BlitzObjectWrapper.
    """
    
    _re = None
    _pd = None
    _rm = {}
    _pixels = None

    _pr = None # projection

    PROJECTIONS = {
        'normal': -1,
        'intmax': omero.constants.projection.ProjectionType.MAXIMUMINTENSITY,
        'intmean': omero.constants.projection.ProjectionType.MEANINTENSITY,
        'intsum': omero.constants.projection.ProjectionType.SUMINTENSITY,
        }
    
    PLANEDEF = omero.romio.XY

    @classmethod
    def fromPixelsId (self, conn, pid):
        q = conn.getQueryService()
        p = q.find('Pixels', pid)
        if p is None:
            return None
        return ImageWrapper(conn, p.image)

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Image'
        self.LINK_CLASS = None
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'DatasetWrapper'

    def __del__ (self):
        self._re and self._re.untaint()

    def __loadedHotSwap__ (self):
        self._obj = self._conn.getContainerService().getImages(self.OMERO_CLASS, (self._oid,), None)[0]

    def getInstrument (self):
        i = self._obj.instrument
        if i is None:
            return None
        if not i.loaded:
            self._obj.instrument = self._conn.getQueryService().find('Instrument', i.id.val)
            i = self._obj.instrument
            meta_serv = self._conn.getMetadataService()
            instruments = meta_serv.loadInstrument(i.id.val)

            if instruments._detectorLoaded:
                i._detectorSeq.extend(instruments._detectorSeq)
            if instruments._objectiveLoaded:
                i._objectiveSeq.extend(instruments._objectiveSeq)
            if instruments._lightSourceLoaded:
                i._lightSourceSeq.extend(instruments._lightSourceSeq)
            if instruments._filterLoaded:
                i._filterSeq.extend(instruments._filterSeq)
            if instruments._dichroicLoaded:
                i._dichroicSeq.extend(instruments._dichroicSeq)
            if instruments._filterSetLoaded:
                i._filterSetSeq.extend(instruments._filterSetSeq)
            if instruments._otfLoaded:
                i._otfSeq.extend(instruments._otfSeq)

        return InstrumentWrapper(self._conn, i)

    def _loadPixels (self):
        if not self._obj.pixelsLoaded:
            self.__loadedHotSwap__()
        return self._obj.sizeOfPixels() > 0

    def _prepareRE (self):
        re = self._conn.createRenderingEngine()
        pixels_id = self._obj.getPrimaryPixels().id.val
        re.lookupPixels(pixels_id)
        if re.lookupRenderingDef(pixels_id) == False: #pragma: no cover
            try:
                re.resetDefaults()
            except omero.ResourceError:
                # broken image
                return False
            re.lookupRenderingDef(pixels_id)
        re.load()
        return re

    def _prepareRenderingEngine (self):
        self._loadPixels()
        if self._re is None:
            if self._obj.sizeOfPixels() < 1:
                return False
            if self._pd is None:
                self._pd = omero.romio.PlaneDef(self.PLANEDEF)
            self._re = self._prepareRE()
        return self._re is not None

    def resetRDefs (self):
        logger.debug('resetRDefs')
        if self.canWrite():
            self._conn.getDeleteService().deleteSettings(self.getId())
            return True
        return False

    def simpleMarshal (self, xtra=None, parents=False):
        rv = super(_ImageWrapper, self).simpleMarshal(xtra=xtra, parents=parents)
        rv.update({'author': self.getAuthor(),
                   'date': time.mktime(self.getDate().timetuple()),})
        if xtra:
            if xtra.has_key('thumbUrlPrefix'):
                if callable(xtra['thumbUrlPrefix']):
                    rv['thumb_url'] = xtra['thumbUrlPrefix'](str(self.id))
                else:
                    rv['thumb_url'] = xtra['thumbUrlPrefix'] + str(self.id) + '/'
        return rv

    def getStageLabel (self):
        if self._obj.stageLabel is None:
            return None
        else:
            return ImageStageLabelWrapper(self._conn, self._obj.stageLabel)
    
    def shortname(self, length=20, hist=5):
        name = self.name
        if not name:
            return ""
        l = len(name)
        if l < length+hist:
            return name
        return "..." + name[l - length:]

    def getAuthor(self):
        q = self._conn.getQueryService()
        e = q.findByQuery("select e from Experimenter e where e.id = %i" % self._obj.details.owner.id.val,None)
        self._author = e.firstName.val + " " + e.lastName.val
        return self._author

    def getDataset(self):
        try:
            q = """
            select ds from Image i join i.datasetLinks dl join dl.parent ds
            where i.id = %i
            """ % self._obj.id.val
            query = self._conn.getQueryService()
            ds = query.findByQuery(q,None)
            return ds and DatasetWrapper(self._conn, ds) or None
        except: #pragma: no cover
            logger.debug('on getDataset')
            logger.debug(traceback.format_exc())
            return None
        
    def getProject(self):
        try:
            q = """
            select p from Image i join i.datasetLinks dl join dl.parent ds join ds.projectLinks pl join pl.parent p
            where i.id = %i
            """ % self._obj.id.val
            query = self._conn.getQueryService()
            prj = query.findByQuery(q,None)
            return prj and ProjectWrapper(self._conn, prj) or None
        except: #pragma: no cover
            logger.debug('on getProject')
            logger.debug(traceback.format_exc())
            return None

    def getDate(self):
        try:
            query = self._conn.getQueryService()
            event = query.findByQuery("select e from Event e where id = %i" % self._obj.details.creationEvent.id.val, None)
            return datetime.fromtimestamp(event.time.val / 1000)
        except: # pragma: no cover
            logger.debug('on getDate')
            logger.debug(traceback.format_exc())
            #self._date = "Today"
            return datetime.fromtimestamp(event.time.val / 1000) #"Today"

    def getObjectiveSettings (self):
        rv = self.objectiveSettings
        if self.objectiveSettings is not None:
            rv = ObjectiveSettingsWrapper(self._conn, self.objectiveSettings)
            if not self.objectiveSettings.loaded:
                self.objectiveSettings = rv._obj
        return rv

    def getImagingEnvironment (self):
        rv = self.imagingEnvironment
        if self.imagingEnvironment is not None:
            rv = ImagingEnvironmentWrapper(self._conn, self.imagingEnvironment)
            if not self.imagingEnvironment.loaded:
                self.imagingEnvironment = rv._obj
        return rv

    @assert_pixels
    def getPrimaryPixels (self):
        return self._obj.getPrimaryPixels()

    @assert_pixels
    def getPixelsId (self):
        return self._obj.getPrimaryPixels().getId().val

    def _prepareTB (self):
        pixels_id = self.getPixelsId()
        if pixels_id is None:
            return None
        tb = self._conn.createThumbnailStore()
        try:
            rv = tb.setPixelsId(pixels_id)
        except omero.InternalException:
            logger.error(traceback.print_exc())
            rv = False
        if not rv: #pragma: no cover
            tb.resetDefaults()
            tb.close()
            tb.setPixelsId(pixels_id)
        return tb
    
    def loadOriginalMetadata(self):
        global_metadata = list()
        series_metadata = list()
        if self is not None:
            for a in self.listAnnotations():
                if isinstance(a._obj, FileAnnotationI) and a.isOriginalMetadata():
                    t_file = list()
                    for piece in a.getFileInChunks():
                        t_file.append(piece)
                    temp_file = "".join(t_file).split('\n')
                    flag = None
                    for l in temp_file:
                        if l.startswith("[GlobalMetadata]"):
                            flag = 1
                        elif l.startswith("[SeriesMetadata]"):
                            flag = 2
                        else:
                            if len(l) < 1:
                                l = None
                            else:
                                l = tuple(l.split("="))                            
                            if l is not None:
                                if flag == 1:
                                    global_metadata.append(l)
                                elif flag == 2:
                                    series_metadata.append(l)
                    return (a, (global_metadata), (series_metadata))
        return None
    
    def getThumbnail (self, size=(64,64), z=None, t=None):
        try:
            tb = self._prepareTB()
            if tb is None:
                return None
            if isinstance(size, IntType):
                size = (size,)
            if z is not None and t is not None:
                pos = z,t
            else:
                pos = None
            if len(size) == 1:
                if pos is None:
                    thumb = tb.getThumbnailByLongestSideDirect
                else:
                    thumb = tb.getThumbnailForSectionByLongestSideDirect
            else:
                if pos is None:
                    thumb = tb.getThumbnailDirect
                else:
                    thumb = tb.getThumbnailForSectionDirect
            args = map(lambda x: rint(x), size)
            if pos is not None:
                args = list(pos) + args
            rv = thumb(*args)
            return rv
        except Exception: #pragma: no cover
            logger.error(traceback.print_exc())
            return None

    @assert_pixels
    def getPixelRange (self):
        """ Returns (min, max) values for the pixels type of this image.
        TODO: Does not handle floats correctly, though."""
        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        rp.setPixelsId(pixels_id, True)
        pmax = 2 ** (8 * rp.getByteWidth())
        if rp.isSigned():
            return (-(pmax / 2), pmax / 2 - 1)
        else:
            return (0, pmax-1)

    @assert_re
    def getChannels (self):
        return [ChannelWrapper(self._conn, c, idx=n, re=self._re, img=self) for n,c in enumerate(self._re.getPixels().iterateChannels())]

    def setActiveChannels(self, channels, windows=None, colors=None):
        for c in range(len(self.getChannels())):
            self._re.setActive(c, (c+1) in channels)
            if (c+1) in channels:
                if windows is not None and windows[c][0] is not None and windows[c][1] is not None:
                    self._re.setChannelWindow(c, *windows[c])
                if colors is not None and colors[c]:
                    rgba = splitHTMLColor(colors[c])
                    if rgba:
                        self._re.setRGBA(c, *rgba)
        return True

    def getProjections (self):
        return self.PROJECTIONS.keys()

    def setProjection (self, proj):
        self._pr = proj

    LINE_PLOT_DTYPES = {
        (4, True, True): 'f', # signed float
        (2, False, False): 'H', # unsigned short
        (2, False, True): 'h',  # signed short
        (1, False, False): 'B', # unsigned char
        (1, False, True): 'b',  # signed char
        }

    def getPixelLine (self, z, t, pos, axis, channels=None, range=None):
        """
        Grab a horizontal or vertical line from the image pixel data, for the specified channels
        (or all if not specified) and using the specified range (or 1:1 relative to the image size).
        Axis may be 'h' or 'v', for horizontal or vertical respectively.
        
        @param z:
        @param t:
        @param pos:
        @param axis:
        @param channels:
        @param range:
        @return: rv
        """
        
        if not self._loadPixels():
            logger.debug( "No pixels!")
            return None
        axis = axis.lower()[:1]
        if channels is None:
            channels = map(lambda x: x._idx, filter(lambda x: x.isActive(), self.getChannels()))
        if range is None:
            range = axis == 'h' and self.getHeight() or self.getWidth()
        if not isinstance(channels, (TupleType, ListType)):
            channels = (channels,)
        chw = map(lambda x: (x.getWindowMin(), x.getWindowMax()), self.getChannels())
        rv = []
        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        rp.setPixelsId(pixels_id, True)
        for c in channels:
            bw = rp.getByteWidth()
            key = self.LINE_PLOT_DTYPES.get((bw, rp.isFloat(), rp.isSigned()), None)
            if key is None:
                logger.error("Unknown data type: " + str((bw, rp.isFloat(), rp.isSigned())))
            plot = array.array(key, axis == 'h' and rp.getRow(pos, z, c, t) or rp.getCol(pos, z, c, t))
            plot.byteswap() # TODO: Assuming ours is a little endian system
            # now move data into the windowMin..windowMax range
            offset = -chw[c][0]
            if offset != 0:
                plot = map(lambda x: x+offset, plot)
            normalize = 1.0/chw[c][1]*(range-1)
            if normalize != 1.0:
                plot = map(lambda x: x*normalize, plot)
            if isinstance(plot, array.array):
                plot = plot.tolist()
            rv.append(plot)
        return rv
        

    def getRow (self, z, t, y, channels=None, range=None):
        return self.getPixelLine(z,t,y,'h',channels,range)

    def getCol (self, z, t, x, channels=None, range=None):
        return self.getPixelLine(z,t,x,'v',channels,range)

    @assert_re
    def getRenderingModels (self):
        if not len(self._rm):
            for m in [BlitzObjectWrapper(self._conn, m) for m in self._re.getAvailableModels()]:
                self._rm[m.value.lower()] = m
        return self._rm.values()

    @assert_re
    def getRenderingModel (self):
        return BlitzObjectWrapper(self._conn, self._re.getModel())

    def setGreyscaleRenderingModel (self):
        """
        Sets the Greyscale rendering model on this image's current renderer
        """
        
        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('greyscale', rm[0])._obj)

    def setColorRenderingModel (self):
        """
        Sets the HSB rendering model on this image's current renderer
        """
        
        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('rgb', rm[0])._obj)

    def isGreyscaleRenderingModel (self):
        return self.getRenderingModel().value.lower() == 'greyscale'
        
    @assert_re
    def renderJpeg (self, z, t, compression=0.9):
        self._pd.z = long(z)
        self._pd.t = long(t)
        try:
            if compression is not None:
                try:
                    self._re.setCompressionLevel(float(compression))
                except omero.SecurityViolation: #pragma: no cover
                    self._obj.clearPixels()
                    self._obj.pixelsLoaded = False
                    self._re = None
                    return self.renderJpeg(z,t,None)
            projection = self.PROJECTIONS.get(self._pr, -1)
            if not isinstance(projection, omero.constants.projection.ProjectionType):
                rv = self._re.renderCompressed(self._pd)
            else:
                rv = self._re.renderProjectedCompressed(projection, self._pd.t, 1, 0, self.z_count()-1)
            return rv
        except omero.InternalException: #pragma: no cover
            logger.debug('On renderJpeg');
            logger.debug(traceback.format_exc())
            return None
        except Ice.MemoryLimitException: #pragma: no cover
            # Make sure renderCompressed isn't called again on this re, as it hangs
            self._obj.clearPixels()
            self._obj.pixelsLoaded = False
            self._re = None
            raise

    def exportOmeTiff (self):
        e = self._conn.createExporter()
        e.addImage(self.getId())
        size = e.generateTiff()
        p = 0
        rv = ''
        while p < size:
            s = min(65536, size-p)
            rv += e.read(p,s)
            p += s
        e.close()
        return rv

    def renderImage (self, z, t, compression=0.9):
        rv = self.renderJpeg(z,t,compression)
        if rv is not None:
            i = StringIO(rv)
            rv = Image.open(i)
        return rv

    def renderSplitChannel (self, z, t, compression=0.9, border=2):
        """
        Prepares a jpeg representation of a 2d grid holding a render of each channel, 
        along with one for all channels at the set Z and T points.
        
        @param z:
        @param t:
        @param compression:
        @param border:
        @return: value
        """
        
        img = self.renderSplitChannelImage(z,t,compression, border)
        rv = StringIO()
        img.save(rv, 'jpeg', quality=int(compression*100))
        return rv.getvalue()

    def splitChannelDims (self, border=2):
        c = self.c_count()
        # Greyscale, no channel overlayed image
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv = {'g':{'width': self.getWidth()*x + border*(x+1),
              'height': self.getHeight()*y+border*(y+1),
              'border': border,
              'gridx': x,
              'gridy': y,}
              }
        # Color, one extra image with all channels overlayed
        c += 1
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv['c'] = {'width': self.getWidth()*x + border*(x+1),
              'height': self.getHeight()*y+border*(y+1),
              'border': border,
              'gridx': x,
              'gridy': y,}
        return rv

    def renderSplitChannelImage (self, z, t, compression=0.9, border=2):
        """
        Prepares a PIL Image with a 2d grid holding a render of each channel, 
        along with one for all channels at the set Z and T points.
        
        @param z:
        @param t:
        @param compression:
        @param border:
        @return: canvas
        """
                
        dims = self.splitChannelDims(border=border)[self.isGreyscaleRenderingModel() and 'g' or 'c']
        canvas = Image.new('RGBA', (dims['width'], dims['height']), '#fff')
        cmap = [ch.isActive() and i+1 or 0 for i,ch in enumerate(self.getChannels())]
        c = self.c_count()
        pxc = 0
        px = dims['border']
        py = dims['border']
        
        # Font sizes depends on image width
        w = self.getWidth()
        if w >= 640:
            fsize = (int((w-640)/128)*8) + 24
            if fsize > 64:
                fsize = 64
        elif w >= 512:
            fsize = 24
        elif w >= 384: #pragma: no cover
            fsize = 18
        elif w >= 298: #pragma: no cover
            fsize = 14
        elif w >= 256: #pragma: no cover
            fsize = 12
        elif w >= 213: #pragma: no cover
            fsize = 10
        elif w >= 96: #pragma: no cover
            fsize = 8
        else: #pragma: no cover
            fsize = 0
        if fsize > 0:
            font = ImageFont.load('%s/pilfonts/B%0.2d.pil' % (THISPATH, fsize) )


        for i in range(c):
            if cmap[i]:
                self.setActiveChannels((i+1,))
                img = self.renderImage(z,t, compression)
                if fsize > 0:
                    draw = ImageDraw.ImageDraw(img)
                    draw.text((2,2), "%s" % (str(self.getChannels()[i].getEmissionWave())), font=font, fill="#fff")
                canvas.paste(img, (px, py))
            pxc += 1
            if pxc < dims['gridx']:
                px += self.getWidth() + border
            else:
                pxc = 0
                px = border
                py += self.getHeight() + border
        if not self.isGreyscaleRenderingModel():
            self.setActiveChannels(cmap)
            img = self.renderImage(z,t, compression)
            if fsize > 0:
                draw = ImageDraw.ImageDraw(img)
                draw.text((2,2), "merged", font=font, fill="#fff")
            canvas.paste(img, (px, py))
        return canvas

    LP_PALLETE = [0,0,0,0,0,0,255,255,255]
    LP_TRANSPARENT = 0 # Some color
    LP_BGCOLOR = 1 # Black
    LP_FGCOLOR = 2 # white
    def prepareLinePlotCanvas (self, z, t):
        """
        Common part of horizontal and vertical line plot rendering.
        @returns: (Image, width, height).
        """
        channels = filter(lambda x: x.isActive(), self.getChannels())
        width = self.getWidth()
        height = self.getHeight()

        pal = list(self.LP_PALLETE)
        # Prepare the palette taking channel colors in consideration
        for channel in channels:
            pal.extend(channel.getColor().getRGB())

        # Prepare the PIL classes we'll be using
        im = Image.new('P', (width, height))
        im.putpalette(pal)
        return im, width, height


    @assert_re
    def renderRowLinePlotGif (self, z, t, y, linewidth=1):
        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas(z,t)
        base = height - 1

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle([0, 0, width-1, base], fill=self.LP_TRANSPARENT, outline=self.LP_TRANSPARENT)
        draw.line(((0,y),(width, y)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab row data
        rows = self.getRow(z,t,y)

        for r in range(len(rows)):
            chrow = rows[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = base-chrow[0]
            for i in range(len(chrow)):
                draw.line(((i, last_point), (i, base-chrow[i])), fill=color, width=linewidth)
                last_point = base-chrow[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re
    def renderColLinePlotGif (self, z, t, x, linewidth=1):
        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas(z,t)

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle([0, 0, width-1, height-1], fill=self.LP_TRANSPARENT, outline=self.LP_TRANSPARENT)
        draw.line(((x,0),(x, height)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab col data
        cols = self.getCol(z,t,x)

        for r in range(len(cols)):
            chcol = cols[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = chcol[0]
            for i in range(len(chcol)):
                draw.line(((last_point, i), (chcol[i], i)), fill=color, width=linewidth)
                last_point = chcol[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re
    def getZ (self):
        return self._pd.z

    @assert_re
    def getT (self):
        return self._pd.t

    @assert_pixels
    def getPixelSizeX (self):
        rv = self._obj.getPrimaryPixels().getPhysicalSizeX()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getPixelSizeY (self):
        rv = self._obj.getPrimaryPixels().getPhysicalSizeY()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getPixelSizeZ (self):
        rv = self._obj.getPrimaryPixels().getPhysicalSizeZ()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getWidth (self):
        return self._obj.getPrimaryPixels().getSizeX().val

    @assert_pixels
    def getHeight (self):
        return self._obj.getPrimaryPixels().getSizeY().val

    @assert_pixels
    def z_count (self):
        return self._obj.getPrimaryPixels().getSizeZ().val

    @assert_pixels
    def t_count (self):
        return self._obj.getPrimaryPixels().getSizeT().val

    @assert_pixels
    def c_count (self):
        return self._obj.getPrimaryPixels().getSizeC().val

    def clearDefaults (self):
        """
        Removes specific color settings from channels
        
        @return: Boolean
        """
        
        if not self.canWrite():
            return False
        for c in self.getChannels():
            c.unloadRed()
            c.unloadGreen()
            c.unloadBlue()
            c.unloadAlpha()
            c.save()
        self._conn.getDeleteService().deleteSettings(self.getId())
        return True

    @assert_re
    def saveDefaults (self):
        """
        Limited support for saving the current prepared image rendering defs.
        Right now only channel colors are saved back.
        
        @return: Boolean
        """
        
        if not self.canWrite():
            return False
        self._re.saveCurrentSettings()
        return True

ImageWrapper = _ImageWrapper

## INSTRUMENT AND ACQUISITION ##

class _ImageStageLabelWrapper (BlitzObjectWrapper):
    pass

ImageStageLabelWrapper = _ImageStageLabelWrapper

class _ImagingEnvironmentWrapper(BlitzObjectWrapper):
    pass

ImagingEnvironmentWrapper = _ImagingEnvironmentWrapper

class _ImagingEnviromentWrapper (BlitzObjectWrapper):
    """
    omero_model_ImagingEnvironmentI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('temperature',
              'airPressure',
              'humidity',
              'co2percent',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'ImagingEnvironment'
    
ImagingEnviromentWrapper = _ImagingEnviromentWrapper

class _TransmittanceRangeWrapper (BlitzObjectWrapper):
    """
    omero_model_TransmittanceRangeI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('cutIn',
              'cutOut',
              'cutInTolerance',
              'cutOutTolerance',
              'transmittance',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'TransmittanceRange'

TransmittanceRangeWrapper = _TransmittanceRangeWrapper

class _DetectorSettingsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetectorSettingsI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('voltage',
              'gain',
              'offsetValue',
              'readOutRate',
              'binning',
              'detector|DetectorWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'DetectorSettings'

DetectorSettingsWrapper = _DetectorSettingsWrapper

class _DetectorWrapper (BlitzObjectWrapper):
    """
    omero_model_DetectorI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              'voltage',
              'gain',
              'offsetValue',
              'zoom',
              'amplificationGain',
              '#type;detectorType',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Detector'

    def getDetectorType(self):
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv
        
DetectorWrapper = _DetectorWrapper

class _ObjectiveWrapper (BlitzObjectWrapper):
    """
    omero_model_ObjectiveI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              'nominalMagnification',
              'calibratedMagnification',
              'lensNA',
              '#immersion',
              '#correction',
              'workingDistance',
              '#iris',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Objective'

    def getImmersion(self):
        rv = self.immersion
        if self.immersion is not None:
            rv = EnumerationWrapper(self._conn, self.immersion)
            if not self.immersion.loaded:
                self.immersion = rv._obj
            return rv
    
    def getCorrection(self):
        rv = self.correction
        if self.correction is not None:
            rv = EnumerationWrapper(self._conn, self.correction)
            if not self.correction.loaded:
                self.correction = rv._obj
            return rv

    def getIris(self):
        rv = self.iris
        if self.iris is not None:
            rv = EnumerationWrapper(self._conn, self.iris)
            if not self.iris.loaded:
                self.iris = rv._obj
            return rv

ObjectiveWrapper = _ObjectiveWrapper

class _ObjectiveSettingsWrapper (BlitzObjectWrapper):
    """
    omero_model_ObjectiveSettingsI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('correctionCollar',
              '#medium',
              'refractiveIndex',
              'objective|ObjectiveWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'ObjectiveSettings'

    def getObjective (self):
        rv = self.objective
        if self.objective is not None:
            rv = ObjectiveWrapper(self._conn, self.objective)
            if not self.objective.loaded:
                self.objective = rv._obj
        return rv
    
    def getMedium(self):
        rv = self.medium
        if self.medium is not None:
            rv = EnumerationWrapper(self._conn, self.medium)
            if not self.medium.loaded:
                self.medium = rv._obj
            return rv

ObjectiveSettingsWrapper = _ObjectiveSettingsWrapper


class _FilterWrapper (BlitzObjectWrapper):
    """
    omero_model_FilterI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'filterWheel',
              '#type;filterType',
              'transmittanceRange|TransmittanceRangeWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Filter'
    
    def getFilterType(self):
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv
    
FilterWrapper = _FilterWrapper

class _DichroicWrapper (BlitzObjectWrapper):
    """
    omero_model_DichroicI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Dichroic'

DichroicWrapper = _DichroicWrapper

class _FilterSetWrapper (BlitzObjectWrapper):
    """
    omero_model_FilterSetI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              #'exFilter|FilterWrapper',
              #'emFilter|FilterWrapper',
              'dichroic|DichroicWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'FilterSet'
    
    def copyEmissionFilters(self):
        pass

    def copyExcitationFilters(self):
        pass
    
FilterSetWrapper = _FilterSetWrapper

class _OTFWrapper (BlitzObjectWrapper):
    """
    omero_model_OTFI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('sizeX',
              'sizeY',
              'opticalAxisAveraged'
              'pixelsType',
              'path',
              'filterSet|FilterSetWrapper',
              'objective|ObjectiveWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'OTF'

OTFWrapper = _OTFWrapper

class _LightSettingsWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('attenuation',
              'wavelength',
              'lightSource|LightSourceWrapper',
              'microbeamManipulation',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'LightSettings'

LightSettingsWrapper = _LightSettingsWrapper

class _LightSourceWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'power',
              'serialNumber',
              '#type;lightSourceType',
              'version')
    
    def getLightSourceType(self):
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

_LightSourceClasses = {}
def LightSourceWrapper (conn, obj, **kwargs):
    for k, v in _LightSourceClasses.items():
        if isinstance(obj, k):
            return getattr(omero.gateway, v)(conn, obj, **kwargs)
    return None

class _FilamentWrapper (_LightSourceWrapper):
    """
    omero_model_ArcI class wrapper extends LightSourceWrapper.
    """

    def __bstrap__ (self):
        super(self.__class__, self).__bstrap__()
        self.OMERO_CLASS = 'Filament'

FilamentWrapper = _FilamentWrapper
_LightSourceClasses[omero.model.FilamentI] = 'FilamentWrapper'

class _ArcWrapper (FilamentWrapper):
    """
    omero_model_ArcI class wrapper extends FilamentWrapper.
    """
    def __bstrap__ (self):
        super(self.__class__, self).__bstrap__()
        self.OMERO_CLASS = 'Arc'

ArcWrapper = _ArcWrapper
_LightSourceClasses[omero.model.ArcI] = 'ArcWrapper'

class _LaserWrapper (_LightSourceWrapper):
    """
    omero_model_LaserI class wrapper extends LightSourceWrapper.
    """
    def __bstrap__ (self):
        super(self.__class__, self).__bstrap__()
        self.OMERO_CLASS = 'Laser'
        self._attrs += (
            '#laserMedium',
            'frequencyMultiplication',
            'tuneable',
            'pulse',
            'wavelength',
            'pockelCell',
            'pump',
            'repetitionRate')

    def getLaserMedium(self):
        rv = self.laserMedium
        if self.laserMedium is not None:
            rv = EnumerationWrapper(self._conn, self.laserMedium)
            if not self.laserMedium.loaded:
                self.laserMedium = rv._obj
            return rv
    
LaserWrapper = _LaserWrapper
_LightSourceClasses[omero.model.LaserI] = 'LaserWrapper'

class _LightEmittingDiodeWrapper (_LightSourceWrapper):
    """
    omero_model_LightEmittingDiodeI class wrapper extends LightSourceWrapper.
    """
    def __bstrap__ (self):
        super(self.__class__, self).__bstrap__()
        self.OMERO_CLASS = 'LightEmittingDiode'

LightEmittingDiodeWrapper = _LightEmittingDiodeWrapper
_LightSourceClasses[omero.model.LightEmittingDiodeI] = 'LightEmittingDiodeWrapper'

class _MicroscopeWrapper (BlitzObjectWrapper):
    """
    omero_model_MicroscopeI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              '#type;microscopeType',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Microscope'
    
    def getMicroscopeType(self):
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

MicroscopeWrapper = _MicroscopeWrapper

class _InstrumentWrapper (BlitzObjectWrapper):
    """
    omero_model_InstrumentI class wrapper extends BlitzObjectWrapper.
    """

    # TODO: wrap version

    _attrs = ('microscope|MicroscopeWrapper',)

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Instrument'
    
    def getMicroscope (self):
        if self._obj.microscope is not None:
            return MicroscopeWrapper(self._conn, self._obj.microscope)
        return None

    def getDetectors (self):
        return [DetectorWrapper(self._conn, x) for x in self._detectorSeq]

    def getObjectives (self):
        return [ObjectiveWrapper(self._conn, x) for x in self._objectiveSeq]

    def getFilters (self):
        return [FilterWrapper(self._conn, x) for x in self._filterSeq]

    def getDichroics (self):
        return [DichroicWrapper(self._conn, x) for x in self._dichroicSeq]

    def getFilterSets (self):
        return [FilterSetWrapper(self._conn, x) for x in self._filterSetSeq]

    def getOTFs (self):
        return [OTFWrapper(self._conn, x) for x in self._otfSeq]

    def getLightSources (self):
        return [LightSourceWrapper(self._conn, x) for x in self._lightSourceSeq]


    def simpleMarshal (self):
        if self._obj:
            rv = super(_InstrumentWrapper, self).simpleMarshal(parents=False)
            rv['detectors'] = [x.simpleMarshal() for x in self.getDetectors()]
            rv['objectives'] = [x.simpleMarshal() for x in self.getObjectives()]
            rv['filters'] = [x.simpleMarshal() for x in self.getFilters()]
            rv['dichroics'] = [x.simpleMarshal() for x in self.getDichroics()]
            rv['filterSets'] = [x.simpleMarshal() for x in self.getFilterSets()]
            rv['otfs'] = [x.simpleMarshal() for x in self.getOTFs()]
            rv['lightsources'] = [x.simpleMarshal() for x in self.getLightSources()]
        else:
            rv = {}
        return rv

InstrumentWrapper = _InstrumentWrapper
