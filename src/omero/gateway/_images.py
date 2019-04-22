import Ice
import array
import math
import os
from math import sqrt
from decimal import Decimal
from types import IntType, ListType
from types import TupleType
from datetime import datetime

from cStringIO import StringIO

import traceback
import time
import warnings
import logging
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

import omero
from omero.rtypes import rlong, rint, unwrap
from ._core import BlitzObjectWrapper

from ._annotations import LongAnnotationWrapper
from ._core import OmeroRestrictionWrapper
# TODO: move these into this file
from ._core import getPixelsQuery
from ._core import getChannelsQuery
from ._core import fileread
from ._core import fileread_gen
from ._containers import PlateWrapper
from ._containers import ProjectWrapper
from ._files import OriginalFileWrapper
from ._instruments import FilterWrapper
from ._instruments import ImageStageLabelWrapper
from ._instruments import ImagingEnvironmentWrapper
from ._instruments import InstrumentWrapper
from ._instruments import ObjectiveSettingsWrapper
import omero.scripts as scripts

from omero.model.enums import PixelsTypeint8, PixelsTypeuint8, PixelsTypeint16
from omero.model.enums import PixelsTypeuint16, PixelsTypeint32
from omero.model.enums import PixelsTypeuint32, PixelsTypefloat
from omero.model.enums import PixelsTypedouble


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
