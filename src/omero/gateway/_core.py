import os

from collections import defaultdict
from types import IntType, LongType, UnicodeType, ListType
from types import BooleanType, StringType, StringTypes
from datetime import datetime

import omero
import omero.clients

import traceback

import logging

from omero.rtypes import rstring, rint, rlong, rbool
from omero.rtypes import rlist

from ._wrappers import KNOWN_WRAPPERS

logger = logging.getLogger(__name__)
THISPATH = os.path.dirname(os.path.abspath(__file__))


def omero_type(val):
    """
    Converts rtypes from static factory methods:
     - StringType to rstring
     - UnicodeType to rstring
     - BooleanType to rbool
     - IntType to rint
     - LongType to rlong

    else return the argument itself

    :param val: value
    :rtype:     omero.rtype
    :return:    matched RType or value
    """

    if isinstance(val, StringType):
        return rstring(val)
    elif isinstance(val, UnicodeType):
        return rstring(val.encode('utf-8'))
    elif isinstance(val, BooleanType):
        return rbool(val)
    elif isinstance(val, IntType):
        return rint(val)
    elif isinstance(val, LongType):
        return rlong(val)
    else:
        return val


def fileread(fin, fsize, bufsize):
    """
    Reads everything from fin, in chunks of bufsize.


    :type fin: file
    :param fin: filelike readable object
    :type fsize: int
    :param fsize: total number of bytes to read
    :type bufsize: int
    :param fsize: size of each chunk of data read from fin
    :rtype: string
    :return: string buffer holding the contents read from the file
    """
    # Read it all in one go
    p = 0
    rv = ''
    try:
        while p < fsize:
            s = min(bufsize, fsize-p)
            rv += fin.read(p, s)
            p += s
    finally:
        fin.close()
    return rv


def fileread_gen(fin, fsize, bufsize):
    """
    Generator helper function that yields chunks of the file of size fsize.

    :type fin: file
    :param fin: filelike readable object
    :type fsize: int
    :param fsize: total number of bytes to read
    :type bufsize: int
    :param fsize: size of each chunk of data read from fin that gets yielded
    :rtype: generator
    :return: generator of string buffers of size up to bufsize read from fin
    """
    p = 0
    try:
        while p < fsize:
            s = min(bufsize, fsize-p)
            yield fin.read(p, s)
            p += s
    finally:
        fin.close()


def getAnnotationLinkTableName(objecttype):
    """
    Get the name of the *AnnotationLink table
    for the given objecttype
    """
    objecttype = objecttype.lower()

    if objecttype == "project":
        return "ProjectAnnotationLink"
    if objecttype == "dataset":
        return"DatasetAnnotationLink"
    if objecttype == "image":
        return"ImageAnnotationLink"
    if objecttype == "screen":
        return "ScreenAnnotationLink"
    if objecttype == "plate":
        return "PlateAnnotationLink"
    if objecttype == "plateacquisition":
        return "PlateAcquisitionAnnotationLink"
    if objecttype == "well":
        return "WellAnnotationLink"
    return None


def getPixelsQuery(imageName):
    """Helper for building Query for Images or Wells & Images"""
    return (' left outer join fetch %s.pixels as pixels'
            ' left outer join fetch pixels.pixelsType' % imageName)


def getChannelsQuery():
    """Helper for building Query for Images or Wells & Images"""
    return (' join fetch pixels.channels as channels'
            ' join fetch channels.logicalChannel as logicalChannel'
            ' left outer join fetch '
            ' logicalChannel.photometricInterpretation'
            ' left outer join fetch logicalChannel.illumination'
            ' left outer join fetch logicalChannel.mode'
            ' left outer join fetch logicalChannel.contrastMethod')


class OmeroRestrictionWrapper (object):

    def canDownload(self):
        """
        Determines if the current user can Download raw data linked to this
        object. The canDownload() property is set on objects:
        Image, Plate and FileAnnotation as it is read from the server, based
        on the current user, event context and group permissions.

        :rtype:     Boolean
        :return:    True if user can download.
        """
        return not self.getDetails().getPermissions().isRestricted(
            omero.constants.permissions.BINARYACCESS)


class BlitzObjectWrapper (object):
    """
    Object wrapper class which provides various methods for hierarchy
    traversing, saving, handling permissions etc. This is the 'abstract' super
    class which is subclassed by E.g. _ProjectWrapper, _DatasetWrapper etc.
    All objects have a reference to the :class:`BlitzGateway` connection, and
    therefore all services are available for handling calls on the object
    wrapper. E.g listChildren() uses queryservice etc.
    """

    # E.g. 'Project', 'Dataset', 'Experimenter' etc.
    OMERO_CLASS = None
    LINK_CLASS = None
    LINK_CHILD = 'child'
    CHILD_WRAPPER_CLASS = None
    PARENT_WRAPPER_CLASS = None

    @staticmethod
    def LINK_PARENT(x):
        return x.parent

    def __init__(self, conn=None, obj=None, cache=None, **kwargs):
        """
        Initialises the wrapper object, setting the various class variables etc

        :param conn:    The :class:`BlitzGateway` connection.
        :type conn:     :class:`BlitzGateway`
        :param obj:     The object to wrap. E.g. omero.model.Image
        :type obj:      omero.model object
        :param cache:   Cache which is passed to new child wrappers
        """
        self.__bstrap__()
        self._obj = obj
        self._cache = cache
        if self._cache is None:
            self._cache = {}
        self._conn = conn
        self._creationDate = None
        if conn is None:
            return
        if hasattr(obj, 'id') and obj.id is not None:
            self._oid = obj.id.val
            if not self._obj.loaded:
                self._obj = self._conn.getQueryService().get(
                    self._obj.__class__.__name__, self._oid,
                    self._conn.SERVICE_OPTS)
        self.__prepare__(**kwargs)

    def __eq__(self, a):
        """
        Returns true if the object is of the same type and has same id and name

        :param a:   The object to compare to this one
        :return:    True if objects are same - see above
        :rtype:     Boolean
        """
        return (type(a) == type(self) and
                self._obj.id == a._obj.id and
                self.getName() == a.getName())

    def __bstrap__(self):
        """
        Initialisation method which is implemented by subclasses to set their
        class variables etc.
        """
        pass

    def __prepare__(self, **kwargs):
        """
        Initialisation method which is implemented by subclasses to handle
        various init tasks
        """
        pass

    def __repr__(self):
        """
        Returns a String representation of the Object, including ID if set.

        :return:    String E.g. '<DatasetWrapper id=123>'
        :rtype:     String
        """
        if hasattr(self, '_oid'):
            return '<%s id=%s>' % (self.__class__.__name__, str(self._oid))
        return super(BlitzObjectWrapper, self).__repr__()

    def _unwrapunits(self, obj, units=None):
        """
        Returns the value of the Value + Unit object.
        If units is true, return the omero model unit object,
        e.g. omero.model.LengthI
        e.g. _unwrapunits(obj).getValue() == 10
        e.g. _unwrapunits(obj).getUnit() == NANOMETER # unit enum
        e.g. _unwrapunits(obj).getSymbol() == "nm"
        If units specifies a valid unit for the type of value, then we convert
        E.g. _unwrapunits(obj, units="MICROMETER").getValue() == 10000

        :param obj:         The Value + Unit object
        :param default:     Default value if obj is None
        :param units:       If true, return (value, unit) tuple
        :return:            Value or omero.model units
        """
        if obj is None:
            return None
        if units is not None:
            # If units is an attribute of the same Class as our obj...
            if isinstance(units, basestring):
                unitClass = obj.getUnit().__class__
                unitEnum = getattr(unitClass, str(units))
                # ... we can convert units
                obj = obj.__class__(obj, unitEnum)
            return obj
        return obj.getValue()

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods
        such as getObjects("Project").
        Returns a tuple of (query, clauses, params).
        Overridden by sub-classes to specify loading of different
        portions of the graph.
        Different sub-classes may allow some control over what's loaded
        and filtering of the query using various opts arguments.
        Opts:
        See different sub-classes for additional opts.

        :param opts:        Dictionary of optional parameters.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from %s obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent" % cls.OMERO_CLASS)

        params = omero.sys.ParametersI()
        clauses = []
        return (query, clauses, params)

    def _getChildWrapper(self):
        """
        Returns the wrapper class of children of this object.
        Checks that this is one of the Wrapper objects in the
        :mod:`omero.gateway` module
        Raises NotImplementedError if this is not true
        or class is not defined (None)
        This is used internally by the :meth:`listChildren` and
        :meth:`countChildren` methods.

        :return:    The child wrapper class.
                    E.g. omero.gateway.DatasetWrapper.__class__
        :rtype:     class
        """
        if self.CHILD_WRAPPER_CLASS is None:  # pragma: no cover
            raise NotImplementedError(
                '%s has no child wrapper defined' % self.__class__)
        if isinstance(self.CHILD_WRAPPER_CLASS, StringTypes):
            # resolve class
            if hasattr(omero.gateway, self.CHILD_WRAPPER_CLASS):
                self.__class__.CHILD_WRAPPER_CLASS \
                    = self.CHILD_WRAPPER_CLASS \
                    = getattr(omero.gateway, self.CHILD_WRAPPER_CLASS)
            else:  # pragma: no cover
                raise NotImplementedError
        return self.CHILD_WRAPPER_CLASS

    def _getParentWrappers(self):
        """
        Returns the wrapper classes of the parent of this object.
        This is used internally by the :meth:`listParents` method.

        :return:    List of parent wrapper classes.
                    E.g. omero.gateway.DatasetWrapper.__class__
        :rtype:     class
        """
        if self.PARENT_WRAPPER_CLASS is None:  # pragma: no cover
            raise NotImplementedError
        pwc = self.PARENT_WRAPPER_CLASS
        if not isinstance(pwc, ListType):
            pwc = [pwc, ]
        for i in range(len(pwc)):
            if isinstance(pwc[i], StringTypes):
                # resolve class
                found = None
                for kls in KNOWN_WRAPPERS.values():
                    kls_name = kls.__name__
                    if kls_name.startswith("_"):
                        kls_name = kls_name[1:]
                        if kls_name == pwc[i]:
                            found = kls
                            break
                if not found:  # pragma: no cover
                    raise NotImplementedError
                pwc[i] = found

        # Cache this so we don't need to resolve classes again
        if (pwc != self.PARENT_WRAPPER_CLASS or
                pwc != self.__class__.PARENT_WRAPPER_CLASS):
            self.__class__.PARENT_WRAPPER_CLASS \
                = self.PARENT_WRAPPER_CLASS = pwc
        return self.PARENT_WRAPPER_CLASS

    def __loadedHotSwap__(self):
        """
        Loads the object that is wrapped by this class. This includes linked
        objects. This method can be overwritten by subclasses that want to
        specify how/which linked objects are loaded
        """
        self._obj = self._conn.getContainerService().loadContainerHierarchy(
            self.OMERO_CLASS, (self._oid,), None, self._conn.SERVICE_OPTS)[0]

    def _moveLink(self, newParent):
        """
        Moves this object from a parent container (first one if there are more
        than one) to a new parent. TODO: might be more useful if it didn't
        assume only 1 parent - option allowed you to specify the oldParent.

        :param newParent:   The new parent Object Wrapper.
        :return:            True if moved from parent to parent.
                            False if no parent exists
                            or newParent has mismatching type
        :rtype:             Boolean
        """
        p = self.getParent()
        # p._obj.__class__ == p._obj.__class__
        # ImageWrapper(omero.model.DatasetI())
        if p.OMERO_CLASS == newParent.OMERO_CLASS:
            link = self._conn.getQueryService().findAllByQuery(
                "select l from %s as l where l.parent.id=%i and l.child.id=%i"
                % (p.LINK_CLASS, p.id, self.id), None, self._conn.SERVICE_OPTS)
            if len(link):
                link[0].parent = newParent._obj
                self._conn.getUpdateService().saveObject(
                    link[0], self._conn.SERVICE_OPTS)
                return True
            logger.debug(
                "## query didn't return objects: 'select l from %s as l "
                "where l.parent.id=%i and l.child.id=%i'"
                % (p.LINK_CLASS, p.id, self.id))
        else:
            logger.debug("## %s != %s ('%s' - '%s')" %
                         (type(p), type(newParent), str(p), str(newParent)))
        return False

    def findChildByName(self, name, description=None):
        """
        Find the first child object with a matching name, and description if
        specified.

        :param name:    The name which must match the child name
        :param description: If specified, child description must match too
        :return:        The wrapped child object
        :rtype:         :class:`BlitzObjectWrapper`
        """
        for c in self.listChildren():
            if c.getName() == name:
                if (description is None or
                        omero_type(description) ==
                        omero_type(c.getDescription())):
                    return c
        return None

    def getDetails(self):
        """
        Gets the details of the wrapped object

        :return:    :class:`DetailsWrapper` or None if object not loaded
        :rtype:     :class:`DetailsWrapper`
        """
        if self._obj.loaded:
            return omero.gateway.DetailsWrapper(self._conn,
                                                self._obj.getDetails())
        return None

    def getDate(self):
        """
        Returns the object's acquisitionDate, or creation date
        (details.creationEvent.time)

        :return:    A :meth:`datetime.datetime` object
        :rtype:     datetime
        """

        try:
            if (self._obj.acquisitionDate.val is not None and
                    self._obj.acquisitionDate.val > 0):
                t = self._obj.acquisitionDate.val
                return datetime.fromtimestamp(t/1000)
        except:
            # object doesn't have acquisitionDate
            pass

        return self.creationEventDate()

    def save(self):
        """
        Uses the updateService to save the wrapped object.

        :rtype:     None
        """
        ctx = self._conn.SERVICE_OPTS.copy()
        if self.getDetails() and self.getDetails().getGroup():
            # This is a save for an object that already exists, make sure group
            # matches
            ctx.setOmeroGroup(self.getDetails().getGroup().getId())
        self._obj = self._conn.getUpdateService().saveAndReturnObject(
            self._obj, ctx)

    def saveAs(self, details):
        """
        Save this object, keeping the object owner the same as the one on
        provided details If the current user is an admin but is NOT the owner
        specified in 'details', then create a new connection for that owner,
        clone the current object under that connection and save. Otherwise,
        simply save.

        :param details:     The Details specifying owner to save to
        :type details:      :class:`DetailsWrapper`
        :return:            None
        """
        if self._conn.isAdmin():
            d = self.getDetails()
            if (d.getOwner() and
                    d.getOwner().omeName == details.getOwner().omeName and
                    d.getGroup().name == details.getGroup().name):
                return self.save()
            else:
                newConn = self._conn.suConn(
                    details.getOwner().omeName, details.getGroup().name)
                # p = omero.sys.Principal()
                # p.name = details.getOwner().omeName
                # p.group = details.getGroup().name
                # p.eventType = "User"
                # newConnId = self._conn.getSessionService(
                #     ).createSessionWithTimeout(p, 60000)
                # newConn = self._conn.clone()
                # newConn.connect(sUuid=newConnId.getUuid().val)
            clone = self.__class__(newConn, self._obj)
            clone.save()
            self._obj = clone._obj
            return
        else:
            return self.save()

    def canWrite(self):
        """
        Delegates to the connection :meth:`BlitzGateway.canWrite` method

        :rtype:     Boolean
        """
        return self._conn.canWrite(self)

    def canOwnerWrite(self):
        """
        Delegates to the connection :meth:`BlitzGateway.canWrite` method

        :rtype:     Boolean
        :return:    True if the objects's permissions allow owner to write
        """
        return self._conn.canOwnerWrite(self)

    def isOwned(self):
        """
        Returns True if the object owner is the same user specified in the
        connection's Event Context

        :rtype:     Boolean
        :return:    True if current user owns this object
        """
        return (self._obj.details.owner.id.val == self._conn.getUserId())

    def isLeaded(self):
        """
        Returns True if the group that this object belongs to is lead by the
        currently logged-in user

        :rtype:     Boolean
        :return:    see above
        """
        g = self._obj.details.group or self._obj.details
        if g.id.val in self._conn.getEventContext().leaderOfGroups:
            return True
        return False

    def isPublic(self):
        """
        Determines if the object permissions are world readable, ie
        permissions.isWorldRead()

        :rtype:     Boolean
        :return:    see above
        """
        g = self.getDetails().getGroup()
        g = g and g.details or self._obj.details
        return g.permissions.isWorldRead()

    def isShared(self):
        """
        Determines if the object is sharable between groups (but not public)

        :rtype:     Boolean
        :return:    True if the object is not :meth:`public <isPublic>` AND
                    the object permissions allow group read.
        """
        if not self.isPublic():
            g = self.getDetails().getGroup()
            g = g and g.details or self._obj.details
            return g.permissions.isGroupRead()
        return False

    def isPrivate(self):
        """
        Determines if the object is private

        :rtype:     Boolean
        :returns:   True if the object is not :meth:`public <isPublic>` and
                    not :meth:`shared <isShared>` and permissions allow user
                    to read.
        """
        if not self.isPublic() and not self.isShared():
            g = self.getDetails().getGroup()
            g = g and g.details or self._obj.details
            return g.permissions.isUserRead()
        return False

    def canEdit(self):
        """
        Determines if the current user can Edit (E.g. name, description) link
        (E.g. Project, Dataset, Image etc) or Delete this object. The
        canEdit() property is set on the permissions of every object as it is
        read from the server, based on the current user, event context and
        group permissions.

        :rtype:     Boolean
        :return:    True if user can Edit this object Delete, link etc.
        """
        return self.getDetails().getPermissions().canEdit()

    def canDelete(self):
        """
        Determines if the current user can Delete the object
        """
        return self.getDetails().getPermissions().canDelete()

    def canLink(self):
        """
        Determines whether user can create 'hard' links (Not annotation
        links). E.g. Between Project/Dataset/Image etc. Previously (4.4.6 and
        earlier) we only allowed this for object owners, but now we delegate
        to what the server will allow.
        """
        return self.getDetails().getPermissions().canLink()

    def canAnnotate(self):
        """
        Determines if the current user can annotate this object: ie create
        annotation links. The canAnnotate() property is set on the permissions
        of every object as it is read from the server, based on the current
        user, event context and group permissions.

        :rtype:     Boolean
        :return:    True if user can Annotate this object
        """
        return self.getDetails().getPermissions().canAnnotate()

    def canChgrp(self):
        """
        Specifies whether the current user can move this object to another
        group. Web client will only allow this for the data Owner. Admin CAN
        move other user's data, but we don't support this in Web yet.
        """
        return self.getDetails().getPermissions().canChgrp()

    def canChown(self):
        """
        Specifies whether the current user can give this object to another
        user. Web client does not yet support this.
        """
        return self.getDetails().getPermissions().canChown()

    def countChildren(self):
        """
        Counts available number of child objects.

        :return:    The number of child objects available
        :rtype:     Long
        """

        childw = self._getChildWrapper()
        klass = "%sLinks" % childw().OMERO_CLASS.lower()
        # self._cached_countChildren = len(
        #     self._conn.getQueryService().findAllByQuery(
        #         "from %s as c where c.parent.id=%i"
        #         % (self.LINK_CLASS, self._oid), None))
        self._cached_countChildren = self._conn.getContainerService(
            ).getCollectionCount(
                self.OMERO_CLASS, klass, [self._oid], None,
                self._conn.SERVICE_OPTS)[self._oid]
        return self._cached_countChildren

    def countChildren_cached(self):
        """
        countChildren, but caching the first result, useful if you need to
        call this multiple times in a single sequence, but have no way of
        storing the value between them. It is actually a hack to support
        django template's lack of break in for loops

        :return:    The number of child objects available
        :rtype:     Long
        """

        if not hasattr(self, '_cached_countChildren'):
            return self.countChildren()
        return self._cached_countChildren

    def _listChildren(self, ns=None, val=None, params=None):
        """
        Lists available child objects.

        :rtype: generator of Ice client proxy objects for the child nodes
        :return: child objects.
        """
        if not params:
            params = omero.sys.Parameters()
        if not params.map:
            params.map = {}
        params.map["dsid"] = omero_type(self._oid)
        query = "select c from %s as c" % self.LINK_CLASS
        if ns is not None:
            params.map["ns"] = omero_type(ns)
        query += """ join fetch c.child as ch
                     left outer join fetch ch.annotationLinks as ial
                     left outer join fetch ial.child as a """
        query += " where c.parent.id=:dsid"
        if ns is not None:
            query += " and a.ns=:ns"
            if val is not None:
                if isinstance(val, StringTypes):
                    params.map["val"] = omero_type(val)
                    query += " and a.textValue=:val"
        query += " order by c.child.name"
        for child in (x.child for x in self._conn.getQueryService(
                ).findAllByQuery(query, params, self._conn.SERVICE_OPTS)):
            yield child

    def listChildren(self, ns=None, val=None, params=None):
        """
        Lists available child objects.

        :rtype: generator of :class:`BlitzObjectWrapper` objs
        :return: child objects.
        """
        childw = self._getChildWrapper()
        for child in self._listChildren(ns=ns, val=val, params=params):
            yield childw(self._conn, child, self._cache)

    def getParent(self, withlinks=False):
        """
        List a single parent, if available.

        While the model supports many to many relationships between most
        objects, there are implementations that assume a single project per
        dataset, a single dataset per image, etc. This is just a shortcut
        method to return a single parent object.

        :type withlinks: Boolean
        :param withlinks: if true result will be a tuple of (linkobj, obj)
        :rtype: :class:`BlitzObjectWrapper`
            or tuple(:class:`BlitzObjectWrapper`, :class:`BlitzObjectWrapper`)
        :return: the parent object with or without the link depending on args
        """

        rv = self.listParents(withlinks=withlinks)
        return len(rv) and rv[0] or None

    def listParents(self, withlinks=False):
        """
        Lists available parent objects.

        :type withlinks: Boolean
        :param withlinks: if true each yielded result
            will be a tuple of (linkobj, obj)
        :rtype: list of :class:`BlitzObjectWrapper`
            or tuple(:class:`BlitzObjectWrapper`, :class:`BlitzObjectWrapper`)
        :return: the parent objects,
            with or without the links depending on args
        """
        if self.PARENT_WRAPPER_CLASS is None:
            return ()
        parentw = self._getParentWrappers()
        param = omero.sys.Parameters()  # TODO: What can I use this for?
        parentnodes = []
        for pwc in parentw:
            pwck = pwc()
            if withlinks:
                parentnodes.extend(
                    [(pwc(self._conn, pwck.LINK_PARENT(x), self._cache),
                        BlitzObjectWrapper(self._conn, x))
                        for x in self._conn.getQueryService(
                            ).findAllByQuery(
                                "from %s as c where c.%s.id=%i"
                                % (pwck.LINK_CLASS, pwck.LINK_CHILD,
                                   self._oid),
                                param, self._conn.SERVICE_OPTS)])
            else:
                t = self._conn.getQueryService().findAllByQuery(
                    "from %s as c where c.%s.id=%i"
                    % (pwck.LINK_CLASS, pwck.LINK_CHILD,
                       self._oid),
                    param, self._conn.SERVICE_OPTS)
                parentnodes.extend(
                    [pwc(self._conn, pwck.LINK_PARENT(x), self._cache)
                        for x in t])
        return parentnodes

    def getAncestry(self):
        """
        Get a list of Ancestors. First in list is parent of this object.
        TODO: Assumes getParent() returns a single parent.

        :rtype: List of :class:`BlitzObjectWrapper`
        :return:    List of Ancestor objects
        """
        rv = []
        p = self.getParent()
        while p:
            rv.append(p)
            p = p.getParent()
        return rv

    def getParentLinks(self, pids=None):
        """
        Get a list of parent objects links.

        :param pids:    List of parent IDs
        :type pids:     :class:`Long`
        :rtype:         List of :class:`BlitzObjectWrapper`
        :return:        List of parent object links
        """

        if self.PARENT_WRAPPER_CLASS is None:
            raise AttributeError("This object has no parent objects")
        parentwrappers = self._getParentWrappers()
        link_class = None
        for v in parentwrappers:
            link_class = v().LINK_CLASS
            if link_class is not None:
                break
        if link_class is None:
            raise AttributeError(
                "This object has no parent objects with a link class!")
        query_serv = self._conn.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["child"] = rlong(self.id)
        sql = "select pchl from %s as pchl " \
            "left outer join fetch pchl.parent as parent " \
            "left outer join fetch pchl.child as child " \
            "where child.id=:child" % link_class
        if isinstance(pids, list) and len(pids) > 0:
            p.map["parent"] = rlist([rlong(pa) for pa in pids])
            sql += " and parent.id in (:parent)"
        for pchl in query_serv.findAllByQuery(sql, p, self._conn.SERVICE_OPTS):
            yield BlitzObjectWrapper(self, pchl)

    def getChildLinks(self, chids=None):
        """
        Get a list of child objects links.

        :param chids:   List of children IDs
        :type chids:    :class:`Long`
        :rtype:         List of :class:`BlitzObjectWrapper`
        :return:        List of child object links
        """

        if self.CHILD_WRAPPER_CLASS is None:
            raise AttributeError("This object has no child objects")
        query_serv = self._conn.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["parent"] = rlong(self.id)
        sql = ("select pchl from %s as pchl left outer join "
               "fetch pchl.child as child left outer join "
               "fetch pchl.parent as parent where parent.id=:parent"
               % self.LINK_CLASS)
        if isinstance(chids, list) and len(chids) > 0:
            p.map["children"] = rlist([rlong(ch) for ch in chids])
            sql += " and child.id in (:children)"
        for pchl in query_serv.findAllByQuery(sql, p, self._conn.SERVICE_OPTS):
            yield BlitzObjectWrapper(self, pchl)

    def _loadAnnotationLinks(self):
        """
        Loads the annotation links and annotations for the object
        (if not already loaded) and saves them to the object.
        Also loads file for file annotations.
        """
        # pragma: no cover
        if not hasattr(self._obj, 'isAnnotationLinksLoaded'):
            raise NotImplementedError
        # Need to set group context. If '-1' then canDelete() etc on
        # annotations will be False
        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.details.group.id.val)
        if not self._obj.isAnnotationLinksLoaded():
            query = ("select l from %sAnnotationLink as l join "
                     "fetch l.details.owner join "
                     "fetch l.details.creationEvent "
                     "join fetch l.child as a join fetch a.details.owner "
                     "left outer join fetch a.file "
                     "join fetch a.details.creationEvent where l.parent.id=%i"
                     % (self.OMERO_CLASS, self._oid))
            links = self._conn.getQueryService().findAllByQuery(
                query, None, ctx)
            self._obj._annotationLinksLoaded = True
            self._obj._annotationLinksSeq = links

    # _listAnnotationLinks
    def _getAnnotationLinks(self, ns=None):
        """
        Checks links are loaded and returns a list of Annotation Links
        filtered by namespace if specified

        :param ns:  Namespace
        :type ns:   String
        :return:    List of Annotation Links on this object
        :rtype:     List of Annotation Links
        """
        self._loadAnnotationLinks()
        rv = self.copyAnnotationLinks()
        if ns is not None:
            rv = filter(
                lambda x: x.getChild().getNs() and
                x.getChild().getNs().val == ns, rv)
        return rv

    def unlinkAnnotations(self, ns):
        """
        Submits request to unlink annotations, with specified ns

        :param ns:      Namespace
        :type ns:       String
        """
        links = defaultdict(list)
        for al in self._getAnnotationLinks(ns=ns):
            links[al.ice_id().split("::")[-1]].append(al.id.val)

        # Using omero.cmd.Delete2 rather than deleteObjects since we need
        # spec/id pairs rather than spec+id_list as arguments
        if len(links):
            delete = omero.cmd.Delete2(targetObjects=links)
            handle = self._conn.c.sf.submit(delete, self._conn.SERVICE_OPTS)
            try:
                self._conn._waitOnCmd(handle)
            finally:
                handle.close()
            self._obj.unloadAnnotationLinks()

    def removeAnnotations(self, ns):
        """
        Uses the delete service to delete annotations, with a specified ns,
        and their links on the object and any other objects. Will raise a
        :class:`omero.LockTimeout` if the annotation removal has not finished
        in 5 seconds.

        :param ns:      Namespace
        :type ns:       String
        """
        ids = list()
        for al in self._getAnnotationLinks(ns=ns):
            a = al.child
            ids.append(a.id.val)
        if len(ids):
            handle = self._conn.deleteObjects('Annotation', ids)
            try:
                self._conn._waitOnCmd(handle)
            finally:
                handle.close()
            self._obj.unloadAnnotationLinks()

    # findAnnotations(self, ns=[])
    def getAnnotation(self, ns=None):
        """
        Gets the first annotation on the object, filtered by ns if specified

        :param ns:      Namespace
        :type ns:       String
        :return:        :class:`AnnotationWrapper` or None
        """
        rv = self._getAnnotationLinks(ns)
        if len(rv):
            return AnnotationWrapper._wrap(self._conn, rv[0].child, link=rv[0])
        return None

    def getAnnotationCounts(self):
        """
        Get the annotion counts for the current object
        """

        return self._conn.countAnnotations(self.OMERO_CLASS, [self.getId()])

    def listAnnotations(self, ns=None):
        """
        List annotations in the ns namespace, linked to this object

        :return:    Generator yielding :class:`AnnotationWrapper`
        :rtype:     :class:`AnnotationWrapper` generator
        """
        for ann in self._getAnnotationLinks(ns):
            yield AnnotationWrapper._wrap(self._conn, ann.child, link=ann)

    def listOrphanedAnnotations(self, eid=None, ns=None, anntype=None,
                                addedByMe=True):
        """
        Retrieve all Annotations not linked to the given Project, Dataset,
        Image, Screen, Plate, Well ID controlled by the security system.

        :param o_type:      type of Object
        :type o_type:       String
        :param oid:         Object ID
        :type oid:          Long
        :return:            Generator yielding Tags
        :rtype:             :class:`AnnotationWrapper` generator
        """

        return self._conn.listOrphanedAnnotations(
            self.OMERO_CLASS, [self.getId()], eid, ns, anntype, addedByMe)

    def _linkObject(self, obj, lnkobjtype):
        """
        Saves the object to DB if needed - setting the permissions manually.
        Creates the object link and saves it, setting permissions manually.
        TODO: Can't set permissions manually in 4.2
            - Assumes world & group writable

        :param obj:     The object to link
        :type obj:      :class:`BlitzObjectWrapper`
        """
        ctx = self._conn.SERVICE_OPTS.copy()
        ctx.setOmeroGroup(self.details.group.id.val)
        if not obj.getId():
            # Not yet in db, save it
            obj = obj.__class__(
                self._conn,
                self._conn.getUpdateService().saveAndReturnObject(
                    obj._obj, ctx))
        lnk = getattr(omero.model, lnkobjtype)()
        lnk.setParent(self._obj.__class__(self._obj.id, False))
        lnk.setChild(obj._obj.__class__(obj._obj.id, False))
        self._conn.getUpdateService().saveObject(lnk, ctx)
        return obj

    def _linkAnnotation(self, ann):
        """
        Saves the annotation to DB if needed, setting the permissions manually.
        Creates the annotation link and saves it, setting permissions manually.
        TODO: Can't set permissions manually in 4.2
            - Assumes world & group writable

        :param ann:     The annotation object
        :type ann:      :class:`AnnotationWrapper`
        """
        return self._linkObject(ann, "%sAnnotationLinkI" % self.OMERO_CLASS)

    def linkAnnotation(self, ann, sameOwner=False):
        """
        Link the annotation to this object.

        :param ann:         The Annotation object
        :type ann:          :class:`AnnotationWrapper`
        :param sameOwner:   If True, try to make sure that the link
                            is created by the object owner
        :type sameOwner:    Boolean
        :return:            The annotation
        :rtype:             :class:`AnnotationWrapper`
        """

        """
        My notes (will) to try and work out what's going on!
        If sameOwner:
            if current user is admin AND they are not the object owner,
                if the object owner and annotation owner are the same:
                    use the Annotation connection to do the linking
                else use a new connection for the object owner
                (?same owner as ann?)
                do linking
            else:
                try to switch the current group of this object
                to the group of the annotation - do linking
        else - just do linking

        """
        if sameOwner:
            d = self.getDetails()
            ad = ann.getDetails()
            if (self._conn.isAdmin() and
                    self._conn.getUserId() != d.getOwner().id):
                # Keep the annotation owner the same as the linked of object's
                if (ad.getOwner() and
                        d.getOwner().omeName == ad.getOwner().omeName and
                        d.getGroup().name == ad.getGroup().name):
                    newConn = ann._conn
                else:
                    # p = omero.sys.Principal()
                    # p.name = d.getOwner().omeName
                    group = None
                    if d.getGroup():
                        group = d.getGroup().name
                    # TODO: Do you know that the object owner is same as ann
                    # owner??
                    newConn = self._conn.suConn(d.getOwner().omeName, group)
                    # p.eventType = "User"
                    # newConnId = self._conn.getSessionService(
                    #     ).createSessionWithTimeout(p, 60000)
                    # newConn = self._conn.clone()
                    # newConn.connect(sUuid=newConnId.getUuid().val)
                clone = self.__class__(newConn, self._obj)
                ann = clone._linkAnnotation(ann)
                if newConn != self._conn:
                    newConn.close()
            elif d.getGroup():
                # Try to match group
                # TODO: Should switch session of this object to use group from
                # annotation (ad) not this object (d) ?
                self._conn.setGroupForSession(d.getGroup().getId())
                ann = self._linkAnnotation(ann)
                self._conn.revertGroupForSession()
            else:
                ann = self._linkAnnotation(ann)
        else:
            ann = self._linkAnnotation(ann)
        self.unloadAnnotationLinks()
        return ann

    def simpleMarshal(self, xtra=None, parents=False):
        """
        Creates a dict representation of this object.
        E.g. for Image::

            {'description': '', 'author': 'Will Moore', 'date': 1286332557.0,
            'type': 'Image', 'id': 3841L, 'name': 'cb_4_w500_t03_z01.tif'}

        :param xtra:        A dict of extra keys to include. E.g. 'childCount'
        :type xtra:         Dict
        :param parents:     If True, include a list of ancestors (in
                            simpleMarshal form) as 'parents'
        :type parents:      Boolean
        :return:            A dict representation of this object
        :rtype:             Dict
        """
        rv = {'type': self.OMERO_CLASS,
              'id': self.getId(),
              'name': self.getName(),
              'description': self.getDescription(),
              }
        if hasattr(self, '_attrs'):
            # for each of the lines in _attrs an instance variable named
            #  'key' or 'title' where the line value can be:
            #   'key' -> _obj[key]
            #   '#key' -> _obj[key].value.val
            #   '()key' -> _obj.getKey()
            #   '()#key' -> _obj.getKey().value.val
            # suffix to the above we can have:
            #   'key;title' - will use 'title' as the variable name,
            #                 instead of 'key'
            #   'key|wrapper' ->  omero.gateway.wrapper(
            #                         _obj[key]).simpleMarshal()
            #   'key|' ->  key.simpleMarshal() (useful with ()key )
            for k in self._attrs:
                if ';' in k:
                    s = k.split(';')
                    k = s[0]
                    rk = ';'.join(s[1:])
                else:
                    rk = k
                if '|' in k:
                    s = k.split('|')
                    if rk == k:
                        rk = s[0]
                    k = s[0]
                    wrapper = '|'.join(s[1:])
                else:
                    wrapper = None

                if k.startswith('()'):
                    if k == rk:
                        rk = k[2:]
                    k = k[2:]
                    getter = True
                else:
                    getter = False

                if k.startswith('#'):
                    k = k[1:]
                    unwrapit = True
                else:
                    unwrapit = False

                if getter:
                    v = getattr(self, 'get'+k[0].upper()+k[1:])()
                else:
                    v = getattr(self, k)
                if unwrapit and v is not None:
                    v = v._value
                if wrapper is not None and v is not None:
                    if wrapper == '':
                        if isinstance(v, ListType):
                            v = map(lambda x: x.simpleMarshal(), v)
                        else:
                            v = v.simpleMarshal()
                    else:
                        v = getattr(omero.gateway, wrapper)(
                            self._conn, v).simpleMarshal()

                rv[rk] = v
        if xtra:  # TODO check if this can be moved to a more specific place
            if 'childCount' in xtra:
                rv['child_count'] = self.countChildren()
        if parents:
            rv['parents'] = map(
                lambda x: x.simpleMarshal(), self.getAncestry())
        return rv

    # def __str__ (self):
    #     if hasattr(self._obj, 'value'):
    #         return str(self.value)
    #     return str(self._obj)

    def __getattr__(self, attr):
        """
        Attempts to return the named attribute of this object. E.g.
        image.__getattr__('name') or 'getName' In cases where the attribute
        E.g. 'getImmersion' should return an enumeration, this is specified by
        the attr name starting with '#' #immersion. In cases where the
        attribute E.g. 'getLightSource' should return a wrapped object, this
        is handled by the parent encoding the wrapper in the attribute name.
        E.g 'lightSource|LightSourceWrapper' In both cases this returns a
        method that will return the object. In addition, lookup of methods
        that return an rtype are wrapped to the method instead returns a
        primitive type. E.g. image.getArchived() will return a boolean instead
        of rbool.

        :param attr:    The name of the attribute to get
        :type attr:     String
        :return:        The named attribute.
        :rtype:         method, value (string, long etc)
        """

        # handle lookup of 'get' methods, using '_attrs' dict to define how we
        # wrap returned objects.
        if (attr != 'get' and
                attr.startswith('get') and
                hasattr(self, '_attrs')):
            tattr = attr[3].lower() + attr[4:]      # 'getName' -> 'name'
            # find attr with 'name'
            attrs = filter(lambda x: tattr in x, self._attrs)
            for a in attrs:
                if a.startswith('#') and a[1:] == tattr:
                    v = getattr(self, tattr)
                    if v is not None:
                        v = v._value

                    def wrap():
                        return v
                    return wrap
                # E.g.  a = lightSource|LightSourceWrapper
                if len(a) > len(tattr) and a[len(tattr)] == '|':
                    # E.g. method returns a
                    # LightSourceWrapper(omero.model.lightSource)
                    def wrap():
                        return getattr(
                            omero.gateway,
                            a[len(tattr)+1:])(self._conn, getattr(self, tattr))
                    return wrap

        # handle lookup of 'get' methods when we don't have '_attrs' on the
        # object, E.g. image.getAcquisitionDate
        if attr != 'get' and attr.startswith('get'):
            # E.g. getAcquisitionDate -> acquisitionDate
            attrName = attr[3].lower() + attr[4:]
            if hasattr(self._obj, attrName):
                def wrap():
                    rv = getattr(self._obj, attrName)
                    if hasattr(rv, 'val'):
                        if isinstance(rv.val, StringType):
                            return rv.val.decode('utf8')
                        # E.g. pixels.getPhysicalSizeX()
                        if hasattr(rv, "_unit"):
                            return rv
                        return rv.val
                    elif isinstance(rv, omero.model.IObject):
                        return BlitzObjectWrapper(self._conn, rv)
                    return rv
                return wrap

        # handle direct access of attributes. E.g. image.acquisitionDate
        # also handles access to other methods E.g. image.unloadPixels()
        if not hasattr(self._obj, attr) and hasattr(self._obj, '_'+attr):
            attr = '_' + attr
        if hasattr(self._obj, attr):
            rv = getattr(self._obj, attr)
            if hasattr(rv, 'val'):   # unwrap rtypes
                # If this is a _unit, then we ignore val
                # since it's not an rtype to unwrap.
                if not hasattr(rv, "_unit"):
                    return (isinstance(rv.val, StringType) and
                            rv.val.decode('utf8') or rv.val)
            return rv
        raise AttributeError(
            "'%s' object has no attribute '%s'"
            % (self._obj.__class__.__name__, attr))

    # some methods are accessors in _obj and return and omero:: type. The
    # obvious ones we wrap to return a python type

    def getId(self):
        """
        Gets this object ID

        :return: Long or None
        """
        oid = self._obj.getId()
        if oid is not None:
            return oid.val
        return None

    def getName(self):
        """
        Gets this object name

        :return: String or None
        """
        if hasattr(self._obj, 'name'):
            if hasattr(self._obj.name, 'val'):
                return self._obj.getName().val
            else:
                return self._obj.getName()
        else:
            return None

    def getDescription(self):
        """
        Gets this object description

        :return: String
        """
        rv = hasattr(
            self._obj, 'description') and self._obj.getDescription() or None
        return rv and rv.val or ''

    def getOwner(self):
        """
        Gets user who is the owner of this object.

        :return: _ExperimenterWrapper
        """
        return self.getDetails().getOwner()

    def getOwnerFullName(self):
        """
        Gets full name of the owner of this object.

        :return: String or None
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

    def getOwnerOmeName(self):
        """
        Gets omeName of the owner of this object.

        :return: String
        """
        return self.getDetails().getOwner().omeName

    def creationEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when
        object was created.

        :return:    The datetime for object creation
        :rtype:     datetime.datetime
        """

        if self._creationDate is not None:
            return datetime.fromtimestamp(self._creationDate/1000)

        try:
            if self._obj.details.creationEvent._time is not None:
                self._creationDate = self._obj.details.creationEvent._time.val
            else:
                self._creationDate = self._conn.getQueryService().get(
                    "Event", self._obj.details.creationEvent.id.val,
                    self._conn.SERVICE_OPTS).time.val
        except:
            self._creationDate = self._conn.getQueryService().get(
                "Event", self._obj.details.creationEvent.id.val,
                self._conn.SERVICE_OPTS).time.val
        return datetime.fromtimestamp(self._creationDate/1000)

    def updateEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when
        object was updated.

        :return:    The datetime for object update
        :rtype:     datetime.datetime
        """

        try:
            if self._obj.details.updateEvent.time is not None:
                t = self._obj.details.updateEvent.time.val
            else:
                t = self._conn.getQueryService().get(
                    "Event", self._obj.details.updateEvent.id.val,
                    self._conn.SERVICE_OPTS).time.val
        except:
            t = self._conn.getQueryService().get(
                "Event", self._obj.details.updateEvent.id.val,
                self._conn.SERVICE_OPTS).time.val
        return datetime.fromtimestamp(t/1000)

    # setters are also provided

    def setName(self, value):
        """
        Sets the name of the object

        :param value:   New name
        :type value:    String
        """
        self._obj.setName(omero_type(value))

    def setDescription(self, value):
        """
        Sets the description of the object

        :param value:   New description
        :type value:    String
        """
        self._obj.setDescription(omero_type(value))


class AnnotationWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationI class wrapper extends BlitzObjectWrapper.
    """
    # class dict for type:wrapper
    # E.g. DoubleAnnotationI : DoubleAnnotationWrapper
    registry = {}
    OMERO_TYPE = None

    def __init__(self, *args, **kwargs):
        """
        Initialises the Annotation wrapper and 'link' if in kwargs
        """
        super(AnnotationWrapper, self).__init__(*args, **kwargs)
        self.link = kwargs.get('link')
        if self._obj is None and self.OMERO_TYPE is not None:
            self._obj = self.OMERO_TYPE()

    def __eq__(self, a):
        """
        Returns true if type, id, value and ns are equal

        :param a:   The annotation to compare
        :return:    True if annotations are the same - see above
        :rtype:     Boolean
        """
        return (type(a) == type(self) and self._obj.id == a._obj.id and
                self.getValue() == a.getValue() and
                self.getNs() == a.getNs())

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("Annotation")
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from Annotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    @classmethod
    def _register(cls, regklass):
        """
        Adds the AnnotationWrapper regklass to class registry

        :param regklass:    The wrapper class,
                            E.g. :class:`DoubleAnnotationWrapper`
        :type regklass:     :class:`AnnotationWrapper` subclass
        """

        cls.registry[regklass.OMERO_TYPE] = regklass

    @classmethod
    def _wrap(cls, conn=None, obj=None, link=None):
        """
        Class method for creating :class:`AnnotationWrapper` subclasses based
        on the type of annotation object, using previously registered mapping
        between OMERO types and wrapper classes

        :param conn:    The :class:`BlitzGateway` connection
        :type conn:     :class:`BlitzGateway`
        :param obj:     The OMERO annotation object.
                        E.g. omero.model.DoubleAnnotation
        :type obj:      :class:`omero.model.Annotation` subclass
        :param link:    The link for this annotation
        :type link:     E.g. omero.model.DatasetAnnotationLink
        :return:    Wrapped AnnotationWrapper object
                    or None if obj.__class__ not registered
        :rtype:     :class:`AnnotationWrapper` subclass
        """
        if obj is None:
            return AnnotationWrapper()
        if obj.__class__ in cls.registry:
            kwargs = dict()
            if link is not None:
                kwargs['link'] = BlitzObjectWrapper(conn, link)
            return cls.registry[obj.__class__](conn, obj, **kwargs)
        else:  # pragma: no cover
            logger.error("Failed to _wrap() annotation: %s" % obj.__class__)
            return None

    @classmethod
    def createAndLink(cls, target, ns, val=None, sameOwner=False):
        """
        Class method for creating an instance of this AnnotationWrapper,
        setting ns and value and linking to the target.

        :param target:      The object to link annotation to
        :type target:       :class:`BlitzObjectWrapper` subclass
        :param ns:          Annotation namespace
        :type ns:           String
        :param val:         Value of annotation. E.g Long, Text, Boolean etc.
        """

        this = cls()
        this.setNs(ns)
        if val is not None:
            this.setValue(val)
        target.linkAnnotation(this, sameOwner=sameOwner)

    def getNs(self):
        """
        Gets annotation namespace

        :return:    Namespace or None
        :rtype:     String
        """

        return self._obj.ns is not None and self._obj.ns.val or None

    def setNs(self, val):
        """
        Sets annotation namespace

        :param val:     Namespace value
        :type val:      String
        """

        self._obj.ns = omero_type(val)

    def getValue(self):  # pragma: no cover
        """ Needs to be implemented by subclasses """
        raise NotImplementedError

    def setValue(self, val):  # pragma: no cover
        """ Needs to be implemented by subclasses """
        raise NotImplementedError

    def getParentLinks(self, ptype, pids=None):
        ptype = ptype.title().replace("Plateacquisition", "PlateAcquisition")
        objs = ('Project', 'Dataset', 'Image', 'Screen',
                'Plate', 'Well', 'PlateAcquisition')
        if ptype not in objs:
            raise AttributeError(
                "getParentLinks(): ptype '%s' not supported" % ptype)
        p = omero.sys.Parameters()
        p.map = {}
        p.map["aid"] = rlong(self.id)
        sql = ("select oal from %sAnnotationLink as oal "
               "left outer join fetch oal.child as ch "
               "left outer join fetch oal.parent as pa "
               "where ch.id=:aid " % (ptype))
        if pids is not None:
            p.map["pids"] = rlist([rlong(ob) for ob in pids])
            sql += " and pa.id in (:pids)"

        for al in self._conn.getQueryService().findAllByQuery(
                sql, p, self._conn.SERVICE_OPTS):
            yield AnnotationLinkWrapper(self._conn, al)


class _AnnotationLinkWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationLinkI class wrapper
    extends omero.gateway.BlitzObjectWrapper.
    """

    def getAnnotation(self):
        return AnnotationWrapper._wrap(self._conn, self.child, self._obj)

    def getParent(self):
        """
        Gets the parent (Annotated Object) as a :class:`BlitzObjectWrapper`,
        but attempts to wrap it in the correct subclass using
        L{KNOWN_WRAPPERS}, E.g. ImageWrapper
        """
        modelClass = self.parent.__class__.__name__[
            :-1].lower()    # E.g. 'image'
        if modelClass in KNOWN_WRAPPERS:
            return KNOWN_WRAPPERS[modelClass](self._conn, self.parent)
        return BlitzObjectWrapper(self._conn, self.parent)

AnnotationLinkWrapper = _AnnotationLinkWrapper


class _AnnotationLinkWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationLinkI class wrapper
    extends omero.gateway.BlitzObjectWrapper.
    """

    def getAnnotation(self):
        return AnnotationWrapper._wrap(self._conn, self.child, self._obj)

    def getParent(self):
        """
        Gets the parent (Annotated Object) as a :class:`BlitzObjectWrapper`,
        but attempts to wrap it in the correct subclass using
        L{KNOWN_WRAPPERS}, E.g. ImageWrapper
        """
        modelClass = self.parent.__class__.__name__[
            :-1].lower()    # E.g. 'image'
        if modelClass in KNOWN_WRAPPERS:
            return KNOWN_WRAPPERS[modelClass](self._conn, self.parent)
        return BlitzObjectWrapper(self._conn, self.parent)

AnnotationLinkWrapper = _AnnotationLinkWrapper


class _EnumerationWrapper (BlitzObjectWrapper):

    def getType(self):
        """
        Gets the type (class) of the Enumeration

        :return:    The omero class
        :type:      Class
        """

        return self._obj.__class__

EnumerationWrapper = _EnumerationWrapper
