from __future__ import division
from past.utils import old_div

from datetime import datetime
import time

import omero
from omero.rtypes import rbool, rdouble, rlong, rstring, rtime, unwrap
from ._core import AnnotationWrapper
from ._core import omero_type
from omero_model_TimestampAnnotationI import TimestampAnnotationI


class TimestampAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TimestampAnnotationI class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = TimestampAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("TimestampAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from TimestampAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Returns a datetime object of the timestamp in seconds

        :return:    Timestamp value
        :rtype:     :class:`datetime.datetime`
        """

        return datetime.fromtimestamp(old_div(self._obj.timeValue.val, 1000.0))

    def setValue(self, val):
        """
        Sets the timestamp value

        :param val:     Timestamp value
        :type val:      :class:`datetime.datetime` OR :class:`omero.RTime`
                        OR Long
        """

        if isinstance(val, datetime):
            self._obj.timeValue = rtime(
                int(time.mktime(val.timetuple())*1000))
        elif isinstance(val, omero.RTime):
            self._obj.timeValue = val
        else:
            self._obj.timeValue = rtime(int(val * 1000))

AnnotationWrapper._register(TimestampAnnotationWrapper)

from omero_model_BooleanAnnotationI import BooleanAnnotationI


class BooleanAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = BooleanAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("BooleanAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from BooleanAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets boolean value

        :return:    Value
        :rtype:     Boolean
        """
        return unwrap(self._obj.boolValue)

    def setValue(self, val):
        """
        Sets boolean value

        :param val:     Value
        :type val:      Boolean
        """

        self._obj.boolValue = rbool(not not val)

AnnotationWrapper._register(BooleanAnnotationWrapper)

from omero_model_TagAnnotationI import TagAnnotationI


class TagAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = TagAnnotationI

    def countTagsInTagset(self):
        # temp solution waiting for #5785
        if self.ns in (omero.constants.metadata.NSINSIGHTTAGSET):
            params = omero.sys.Parameters()
            params.map = {}
            params.map['tid'] = self._obj.id
            sql = ("select tg from TagAnnotation tg where exists "
                   "( select aal from AnnotationAnnotationLink as aal where "
                   "aal.child=tg.id and aal.parent.id=:tid) ")

            res = self._conn.getQueryService().findAllByQuery(
                sql, params, self._conn.SERVICE_OPTS)
            return res is not None and len(res) or 0

    def listTagsInTagset(self):
        # temp solution waiting for #5785
        if self.ns in (omero.constants.metadata.NSINSIGHTTAGSET):
            params = omero.sys.Parameters()
            params.map = {}
            params.map["tid"] = rlong(self._obj.id)

            sql = ("select tg from TagAnnotation tg where exists "
                   "( select aal from AnnotationAnnotationLink as aal where "
                   "aal.child.id=tg.id and aal.parent.id=:tid) ")

            q = self._conn.getQueryService()
            for ann in q.findAllByQuery(sql, params, self._conn.SERVICE_OPTS):
                yield TagAnnotationWrapper(self._conn, ann)

    def listParents(self, withlinks=True):
        """
        We override the listParents() to look for 'Tag-Group' Tags on this Tag
        """
        # In this case, the Tag is the 'child' - 'Tag-Group' (parent) has
        # specified ns
        links = self._conn.getAnnotationLinks(
            "TagAnnotation", ann_ids=[self.getId()])
        rv = []
        for l in links:
            if l.parent.ns.val == omero.constants.metadata.NSINSIGHTTAGSET:
                rv.append(
                    omero.gateway.TagAnnotationWrapper(
                        self._conn, l.parent, l))
        return rv

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("TagAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from TagAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets the value of the Tag

        :return:    Value
        :type:      String
        """

        return unwrap(self._obj.textValue)

    def setValue(self, val):
        """
        Sets Tag value

        :param val:     Tag text value
        :type val:      String
        """

        self._obj.textValue = omero_type(val)

AnnotationWrapper._register(TagAnnotationWrapper)

from omero_model_CommentAnnotationI import CommentAnnotationI


class CommentAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_CommentAnnotationI class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = CommentAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("CommentAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from CommentAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets the value of the Comment

        :return:    Value
        :type:      String
        """
        return unwrap(self._obj.textValue)

    def setValue(self, val):
        """
        Sets comment text value

        :param val:     Value
        :type val:      String
        """

        self._obj.textValue = omero_type(val)

AnnotationWrapper._register(CommentAnnotationWrapper)

from omero_model_LongAnnotationI import LongAnnotationI


class LongAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_LongAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = LongAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("LongAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from LongAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets the value of the Long annotation

        :return:    Value
        :type:      Long
        """

        return unwrap(self._obj.longValue)

    def setValue(self, val):
        """
        Sets long annotation value

        :param val:     Value
        :type val:      Long
        """

        self._obj.longValue = rlong(val)

AnnotationWrapper._register(LongAnnotationWrapper)

from omero_model_DoubleAnnotationI import DoubleAnnotationI


class DoubleAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_DoubleAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = DoubleAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("DoubleAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from DoubleAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets the value of the Double Annotation

        :return:    Value
        :type:      Double
        """
        return unwrap(self._obj.doubleValue)

    def setValue(self, val):
        """
        Sets Double annotation value

        :param val:     Value
        :type val:      Double
        """

        self._obj.doubleValue = rdouble(val)

AnnotationWrapper._register(DoubleAnnotationWrapper)

from omero_model_TermAnnotationI import TermAnnotationI


class TermAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TermAnnotationI class wrapper extends AnnotationWrapper.

    only in 4.2+
    """
    OMERO_TYPE = TermAnnotationI

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("TermAnnotation").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = ("select obj from TermAnnotation obj "
                 "join fetch obj.details.owner as owner "
                 "join fetch obj.details.creationEvent")
        return query, [], omero.sys.ParametersI()

    def getValue(self):
        """
        Gets the value of the Term

        :return:    Value
        :type:      String
        """

        return unwrap(self._obj.termValue)

    def setValue(self, val):
        """
        Sets term value

        :param val:     Value
        :type val:      String
        """

        self._obj.termValue = rstring(val)

AnnotationWrapper._register(TermAnnotationWrapper)

from omero_model_XmlAnnotationI import XmlAnnotationI


class XmlAnnotationWrapper (CommentAnnotationWrapper):
    """
    omero_model_XmlAnnotationI class wrapper extends CommentAnnotationWrapper.
    """
    OMERO_TYPE = XmlAnnotationI

AnnotationWrapper._register(XmlAnnotationWrapper)


from omero_model_MapAnnotationI import MapAnnotationI


class MapAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_MapAnnotationI class wrapper.
    """
    OMERO_TYPE = MapAnnotationI

    def getValue(self):
        """
        Gets the value of the Map Annotation as a list of
        (key, value) tuples.

        :return:    List of tuples
        :type:      String
        """

        return [(kv.name, kv.value) for kv in self._obj.getMapValue()]

    def setValue(self, val):
        """
        Sets value of the Map Annotation where val is a list of
        (key, value) tuples or [key, value] lists.

        :param val:     List of tuples
        :type val:      String
        """

        data = [omero.model.NamedValue(d[0], d[1]) for d in val]
        self._obj.setMapValue(data)

AnnotationWrapper._register(MapAnnotationWrapper)
