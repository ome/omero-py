import datetime
import logging
logger = logging.getLogger(__name__)

import omero
from omero.rtypes import rint, rlong, unwrap
from omero.util.decorators import timeit
from .core import BlitzObjectWrapper
from .core import OmeroRestrictionWrapper
from .core import getChannelsQuery
from .core import getPixelsQuery
from .core import omero_type


def add_plate_filter(clauses, params, opts):
    """Helper for adding 'plate' to filtering clauses and parameters."""
    if opts is not None and 'plate' in opts:
        clauses.append('obj.plate.id = :pid')
        params.add('pid', rlong(opts['plate']))


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
