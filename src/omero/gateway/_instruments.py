import omero
from omero.rtypes import rlong
from ._core import BlitzObjectWrapper
from ._core import EnumerationWrapper

# INSTRUMENT AND ACQUISITION #


class _ImageStageLabelWrapper (BlitzObjectWrapper):
    """
    omero_model_StageLabelI class wrapper extends BlitzObjectWrapper.
    """
    pass

ImageStageLabelWrapper = _ImageStageLabelWrapper


class _ImagingEnvironmentWrapper(BlitzObjectWrapper):
    """
    omero_model_ImagingEnvironment class wrapper extends BlitzObjectWrapper.
    """
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

    OMERO_CLASS = 'ImagingEnvironment'

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

    OMERO_CLASS = 'TransmittanceRange'

TransmittanceRangeWrapper = _TransmittanceRangeWrapper


class _DetectorSettingsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetectorSettingsI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('voltage',
              'gain',
              'offsetValue',
              'readOutRate',
              'binning|BinningWrapper',
              'detector|DetectorWrapper',
              'version')

    OMERO_CLASS = 'DetectorSettings'

DetectorSettingsWrapper = _DetectorSettingsWrapper


class _BinningWrapper (BlitzObjectWrapper):
    """
    omero_model_BinningI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'Binning'

BinningWrapper = _BinningWrapper


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

    OMERO_CLASS = 'Detector'

    def getDetectorType(self):
        """
        The type of detector (enum value)

        :return:    Detector type
        :rtype:     :class:`EnumerationWrapper`
        """

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
              'iris',
              'version')

    OMERO_CLASS = 'Objective'

    def getImmersion(self):
        """
        The type of immersion for this objective (enum value)

        :return:    Immersion type, or None
        :rtype:     :class:`EnumerationWrapper`
        """

        rv = self.immersion
        if self.immersion is not None:
            rv = EnumerationWrapper(self._conn, self.immersion)
            if not self.immersion.loaded:
                self.immersion = rv._obj
            return rv

    def getCorrection(self):
        """
        The type of Correction for this objective (enum value)

        :return:    Correction type, or None
        :rtype:     :class:`EnumerationWrapper`
        """

        rv = self.correction
        if self.correction is not None:
            rv = EnumerationWrapper(self._conn, self.correction)
            if not self.correction.loaded:
                self.correction = rv._obj
            return rv

    def getIris(self):
        """
        The type of Iris for this objective (enum value)

        :return:    Iris type
        :rtype:     :class:`EnumerationWrapper`
        """

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

    OMERO_CLASS = 'ObjectiveSettings'

    def getObjective(self):
        """
        Gets the Objective that these settings refer to

        :return:    Objective
        :rtype:     :class:`ObjectiveWrapper`
        """

        rv = self.objective
        if self.objective is not None:
            rv = ObjectiveWrapper(self._conn, self.objective)
            if not self.objective.loaded:
                self.objective = rv._obj
        return rv

    def getMedium(self):
        """
        Gets the Medium type that these settings refer to (enum value)

        :return:    Medium
        :rtype:     :class:`EnumerationWrapper`
        """

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

    OMERO_CLASS = 'Filter'

    def getFilterType(self):
        """
        Gets the Filter type for this filter (enum value)

        :return:    Filter type
        :rtype:     :class:`EnumerationWrapper`
        """

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

    OMERO_CLASS = 'Dichroic'

DichroicWrapper = _DichroicWrapper


class _FilterSetWrapper (BlitzObjectWrapper):
    """
    omero_model_FilterSetI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'dichroic|DichroicWrapper',
              'version')

    OMERO_CLASS = 'FilterSet'

    def copyEmissionFilters(self):
        """ TODO: not implemented """
        pass

    def copyExcitationFilters(self):
        """ TODO: not implemented """
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

    OMERO_CLASS = 'OTF'

OTFWrapper = _OTFWrapper


class _LightSettingsWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('attenuation',
              'wavelength',
              # 'lightSource|LightSourceWrapper',
              'microbeamManipulation',
              'version')

    OMERO_CLASS = 'LightSettings'

    def getLightSource(self):
        if self._obj.lightSource is None:
            return None
        if not self._obj.lightSource.isLoaded():    # see #5742
            lid = self._obj.lightSource.id.val
            params = omero.sys.Parameters()
            params.map = {"id": rlong(lid)}
            query = ("select l from Laser as l left outer join fetch l.type "
                     "left outer join fetch l.laserMedium "
                     "left outer join fetch l.pulse as pulse "
                     "left outer join fetch l.pump as pump "
                     "left outer join fetch pump.type as pt "
                     "where l.id = :id")
            self._obj.lightSource = self._conn.getQueryService().findByQuery(
                query, params, self._conn.SERVICE_OPTS)
        return LightSourceWrapper(self._conn, self._obj.lightSource)

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
        """
        Gets the Light Source type for this light source (enum value)

        :return:    Light Source type
        :rtype:     :class:`EnumerationWrapper`
        """

        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

# map of light source gateway classes to omero model objects. E.g.
# omero.model.Arc : 'ArcWrapper'
_LightSourceClasses = {}


def LightSourceWrapper(conn, obj, **kwargs):
    """
    Creates wrapper instances for omero.model light source objects

    :param conn:    :class:`BlitzGateway` connection
    :param obj:     omero.model object
    :return:        :class:`_LightSourceWrapper` subclass
    """
    for k, v in list(_LightSourceClasses.items()):
        if isinstance(obj, k):
            return getattr(omero.gateway, v)(conn, obj, **kwargs)
    return None


class _FilamentWrapper (_LightSourceWrapper):
    """
    omero_model_FilamentI class wrapper extends LightSourceWrapper.
    """

    OMERO_CLASS = 'Filament'

FilamentWrapper = _FilamentWrapper
_LightSourceClasses[omero.model.FilamentI] = 'FilamentWrapper'


class _ArcWrapper (_FilamentWrapper):
    """
    omero_model_ArcI class wrapper extends FilamentWrapper.
    """

    OMERO_CLASS = 'Arc'

ArcWrapper = _ArcWrapper
_LightSourceClasses[omero.model.ArcI] = 'ArcWrapper'


class _LaserWrapper (_LightSourceWrapper):
    """
    omero_model_LaserI class wrapper extends LightSourceWrapper.
    """

    OMERO_CLASS = 'Laser'

    def __bstrap__(self):
        super(_LaserWrapper, self).__bstrap__()
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
        """
        Gets the laser medium type for this Laser (enum value)

        :return:    Laser medium type
        :rtype:     :class:`EnumerationWrapper`
        """

        rv = self.laserMedium
        if self.laserMedium is not None:
            rv = EnumerationWrapper(self._conn, self.laserMedium)
            if not self.laserMedium.loaded:
                self.laserMedium = rv._obj
            return rv

    def getPump(self):
        """
        Gets the pump (Light Source) for this Laser

        :return:    Pump (Light Source)
        :rtype:     :class:`LightSourceWrapper`
        """
        rv = self.pump
        if rv is not None:
            return LightSourceWrapper(self._conn, rv)

LaserWrapper = _LaserWrapper
_LightSourceClasses[omero.model.LaserI] = 'LaserWrapper'


class _LightEmittingDiodeWrapper (_LightSourceWrapper):
    """
    omero_model_LightEmittingDiodeI class wrapper extends LightSourceWrapper.
    """

    OMERO_CLASS = 'LightEmittingDiode'

LightEmittingDiodeWrapper = _LightEmittingDiodeWrapper
_LightSourceClasses[
    omero.model.LightEmittingDiodeI] = 'LightEmittingDiodeWrapper'


class _MicroscopeWrapper (BlitzObjectWrapper):
    """
    omero_model_MicroscopeI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              '#type;microscopeType',
              'version')

    OMERO_CLASS = 'Microscope'

    def getMicroscopeType(self):
        """
        Returns the 'type' of microscope this is.

        :return:    Microscope type.
        :rtype:     :class:`EnumerationWrapper`
        """

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

    OMERO_CLASS = 'Instrument'

    def getMicroscope(self):
        """
        Returns the microscope component of the Instrument.

        :return:    Microscope
        :rtype:     omero.model.Microscope
        """

        if self._obj.microscope is not None:
            return MicroscopeWrapper(self._conn, self._obj.microscope)
        return None

    def getDetectors(self):
        """
        Gets the Instrument detectors.

        :return:    List of Detectors
        :rtype:     :class:`DetectorWrapper` list
        """

        return [DetectorWrapper(self._conn, x) for x in self._detectorSeq]

    def getObjectives(self):
        """
        Gets the Instrument Objectives.

        :return:    List of Objectives
        :rtype:     :class:`ObjectiveWrapper` list
        """

        return [ObjectiveWrapper(self._conn, x) for x in self._objectiveSeq]

    def getFilters(self):
        """
        Gets the Instrument Filters.

        :return:    List of Filters
        :rtype:     :class:`FilterWrapper` list
        """

        return [FilterWrapper(self._conn, x) for x in self._filterSeq]

    def getDichroics(self):
        """
        Gets the Instrument Dichroics.

        :return:    List of Dichroics
        :rtype:     :class:`DichroicWrapper` list
        """

        return [DichroicWrapper(self._conn, x) for x in self._dichroicSeq]

    def getFilterSets(self):
        """
        Gets the Instrument FilterSets.

        :return:    List of FilterSets
        :rtype:     :class:`FilterSetWrapper` list
        """

        return [FilterSetWrapper(self._conn, x) for x in self._filterSetSeq]

    def getOTFs(self):
        """
        Gets the Instrument OTFs.

        :return:    List of OTFs
        :rtype:     :class:`OTFWrapper` list
        """

        return [OTFWrapper(self._conn, x) for x in self._otfSeq]

    def getLightSources(self):
        """
        Gets the Instrument LightSources.

        :return:    List of LightSources
        :rtype:     :class:`LightSourceWrapper` list
        """

        return [LightSourceWrapper(self._conn, x)
                for x in self._lightSourceSeq]

    def simpleMarshal(self):
        if self._obj:
            rv = super(_InstrumentWrapper, self).simpleMarshal(parents=False)
            rv['detectors'] = [x.simpleMarshal() for x in self.getDetectors()]
            rv['objectives'] = [x.simpleMarshal()
                                for x in self.getObjectives()]
            rv['filters'] = [x.simpleMarshal() for x in self.getFilters()]
            rv['dichroics'] = [x.simpleMarshal() for x in self.getDichroics()]
            rv['filterSets'] = [x.simpleMarshal()
                                for x in self.getFilterSets()]
            rv['otfs'] = [x.simpleMarshal() for x in self.getOTFs()]
            rv['lightsources'] = [x.simpleMarshal()
                                  for x in self.getLightSources()]
        else:
            rv = {}
        return rv

InstrumentWrapper = _InstrumentWrapper
