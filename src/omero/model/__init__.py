#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is an import-only file providing a mechanism for other files to
# import a range of modules in a controlled way. It could be made to pass
# flake8 but given its simplicity it is being marked as noqa for now.
#
# flake8: noqa

from omero import ObjectFactoryRegistrar
from typing import TYPE_CHECKING

import IceImport

if TYPE_CHECKING:
    from omero_model_Filter_ice import Filter, FilterPrx
    from omero_model_Mask_ice import Mask, MaskPrx
    from omero_model_PlateAcquisitionAnnotationLink_ice import PlateAcquisitionAnnotationLink, PlateAcquisitionAnnotationLinkPrx
    from omero_model_Experimenter_ice import Experimenter, ExperimenterPrx
    from omero_model_OriginalFile_ice import OriginalFile, OriginalFilePrx
    from omero_model_FilesetEntry_ice import FilesetEntry, FilesetEntryPrx
    from omero_model_InstrumentAnnotationLink_ice import InstrumentAnnotationLink, InstrumentAnnotationLinkPrx
    from omero_model_LogicalChannel_ice import LogicalChannel, LogicalChannelPrx
    from omero_model_ContrastStretchingContext_ice import ContrastStretchingContext, ContrastStretchingContextPrx
    from omero_model_ExternalInfo_ice import ExternalInfo, ExternalInfoPrx
    from omero_model_ScreenPlateLink_ice import ScreenPlateLink, ScreenPlateLinkPrx
    from omero_model_DoubleAnnotation_ice import DoubleAnnotation, DoubleAnnotationPrx
    from omero_model_TypeAnnotation_ice import TypeAnnotation, TypeAnnotationPrx
    from omero_model_ScreenAnnotationLink_ice import ScreenAnnotationLink, ScreenAnnotationLinkPrx
    from omero_model_ContrastMethod_ice import ContrastMethod, ContrastMethodPrx
    from omero_model_QuantumDef_ice import QuantumDef, QuantumDefPrx
    from omero_model_NamespaceAnnotationLink_ice import NamespaceAnnotationLink, NamespaceAnnotationLinkPrx
    from omero_model_LightPathAnnotationLink_ice import LightPathAnnotationLink, LightPathAnnotationLinkPrx
    from omero_model_PlaneInfo_ice import PlaneInfo, PlaneInfoPrx
    from omero_model_DichroicAnnotationLink_ice import DichroicAnnotationLink, DichroicAnnotationLinkPrx
    from omero_model_ScriptJob_ice import ScriptJob, ScriptJobPrx
    from omero_model_Laser_ice import Laser, LaserPrx
    from omero_model_Immersion_ice import Immersion, ImmersionPrx
    from omero_model_StatsInfo_ice import StatsInfo, StatsInfoPrx
    from omero_model_FolderAnnotationLink_ice import FolderAnnotationLink, FolderAnnotationLinkPrx
    from omero_model_ElectricPotential_ice import ElectricPotential, ElectricPotentialPrx
    from omero_model_Format_ice import Format, FormatPrx
    from omero_model_DBPatch_ice import DBPatch, DBPatchPrx
    from omero_model_FolderRoiLink_ice import FolderRoiLink, FolderRoiLinkPrx
    from omero_model_Correction_ice import Correction, CorrectionPrx
    from omero_model_ObjectiveAnnotationLink_ice import ObjectiveAnnotationLink, ObjectiveAnnotationLinkPrx
    from omero_model_AnnotationAnnotationLink_ice import AnnotationAnnotationLink, AnnotationAnnotationLinkPrx
    from omero_model_Folder_ice import Folder, FolderPrx
    from omero_model_PlaneSlicingContext_ice import PlaneSlicingContext, PlaneSlicingContextPrx
    from omero_model_Pixels_ice import Pixels, PixelsPrx
    from omero_model_Medium_ice import Medium, MediumPrx
    from omero_model_RenderingModel_ice import RenderingModel, RenderingModelPrx
    from omero_model_ExperimenterAnnotationLink_ice import ExperimenterAnnotationLink, ExperimenterAnnotationLinkPrx
    from omero_model_LongAnnotation_ice import LongAnnotation, LongAnnotationPrx
    from omero_model_IntegrityCheckJob_ice import IntegrityCheckJob, IntegrityCheckJobPrx
    from omero_model_UploadJob_ice import UploadJob, UploadJobPrx
    from omero_model_NodeAnnotationLink_ice import NodeAnnotationLink, NodeAnnotationLinkPrx
    from omero_model_PixelsType_ice import PixelsType, PixelsTypePrx
    from omero_model_AffineTransform_ice import AffineTransform, AffineTransformPrx
    from omero_model_Project_ice import Project, ProjectPrx
    from omero_model_Family_ice import Family, FamilyPrx
    from omero_model_PhotometricInterpretation_ice import PhotometricInterpretation, PhotometricInterpretationPrx
    from omero_model_BasicAnnotation_ice import BasicAnnotation, BasicAnnotationPrx
    from omero_model_Namespace_ice import Namespace, NamespacePrx
    from omero_model_Point_ice import Point, PointPrx
    from omero_model_WellSample_ice import WellSample, WellSamplePrx
    from omero_model_Detector_ice import Detector, DetectorPrx
    from omero_model_Reagent_ice import Reagent, ReagentPrx
    from omero_model_Units_ice import Units, UnitsPrx
    from omero_model_LightEmittingDiode_ice import LightEmittingDiode, LightEmittingDiodePrx
    from omero_model_ShapeAnnotationLink_ice import ShapeAnnotationLink, ShapeAnnotationLinkPrx
    from omero_model_FilamentType_ice import FilamentType, FilamentTypePrx
    from omero_model_Power_ice import Power, PowerPrx
    from omero_model_ImportJob_ice import ImportJob, ImportJobPrx
    from omero_model_OTF_ice import OTF, OTFPrx
    from omero_model_DatasetAnnotationLink_ice import DatasetAnnotationLink, DatasetAnnotationLinkPrx
    from omero_model_ReagentAnnotationLink_ice import ReagentAnnotationLink, ReagentAnnotationLinkPrx
    from omero_model_Fileset_ice import Fileset, FilesetPrx
    from omero_model_DetectorAnnotationLink_ice import DetectorAnnotationLink, DetectorAnnotationLinkPrx
    from omero_model_MicroscopeType_ice import MicroscopeType, MicroscopeTypePrx
    from omero_model_Node_ice import Node, NodePrx
    from omero_model_MapAnnotation_ice import MapAnnotation, MapAnnotationPrx
    from omero_model_Polygon_ice import Polygon, PolygonPrx
    from omero_model_OriginalFileAnnotationLink_ice import OriginalFileAnnotationLink, OriginalFileAnnotationLinkPrx
    from omero_model_ImageAnnotationLink_ice import ImageAnnotationLink, ImageAnnotationLinkPrx
    from omero_model_CodomainMapContext_ice import CodomainMapContext, CodomainMapContextPrx
    from omero_model_Dataset_ice import Dataset, DatasetPrx
    from omero_model_MetadataImportJob_ice import MetadataImportJob, MetadataImportJobPrx
    from omero_model_LightSettings_ice import LightSettings, LightSettingsPrx
    from omero_model_ProjectionAxis_ice import ProjectionAxis, ProjectionAxisPrx
    from omero_model_Job_ice import Job, JobPrx
    from omero_model_FilterSetEmissionFilterLink_ice import FilterSetEmissionFilterLink, FilterSetEmissionFilterLinkPrx
    from omero_model_Plate_ice import Plate, PlatePrx
    from omero_model_ParseJob_ice import ParseJob, ParseJobPrx
    from omero_model_IndexingJob_ice import IndexingJob, IndexingJobPrx
    from omero_model_FilterAnnotationLink_ice import FilterAnnotationLink, FilterAnnotationLinkPrx
    from omero_model_FilesetJobLink_ice import FilesetJobLink, FilesetJobLinkPrx
    from omero_model_FilterType_ice import FilterType, FilterTypePrx
    from omero_model_LightPathExcitationFilterLink_ice import LightPathExcitationFilterLink, LightPathExcitationFilterLinkPrx
    from omero_model_ExperimentType_ice import ExperimentType, ExperimentTypePrx
    from omero_model_JobStatus_ice import JobStatus, JobStatusPrx
    from omero_model_Experiment_ice import Experiment, ExperimentPrx
    from omero_model_RTypes_ice import RTypes, RTypesPrx
    from omero_model_EventLog_ice import EventLog, EventLogPrx
    from omero_model_GroupExperimenterMap_ice import GroupExperimenterMap, GroupExperimenterMapPrx
    from omero_model_FilesetAnnotationLink_ice import FilesetAnnotationLink, FilesetAnnotationLinkPrx
    from omero_model_NumericAnnotation_ice import NumericAnnotation, NumericAnnotationPrx
    from omero_model_FolderImageLink_ice import FolderImageLink, FolderImageLinkPrx
    from omero_model_ImagingEnvironment_ice import ImagingEnvironment, ImagingEnvironmentPrx
    from omero_model_ChannelBinding_ice import ChannelBinding, ChannelBindingPrx
    from omero_model_Share_ice import Share, SharePrx
    from omero_model_WellAnnotationLink_ice import WellAnnotationLink, WellAnnotationLinkPrx
    from omero_model_GenericExcitationSource_ice import GenericExcitationSource, GenericExcitationSourcePrx
    from omero_model_FilterSet_ice import FilterSet, FilterSetPrx
    from omero_model_Pressure_ice import Pressure, PressurePrx
    from omero_model_Temperature_ice import Temperature, TemperaturePrx
    from omero_model_PlateAnnotationLink_ice import PlateAnnotationLink, PlateAnnotationLinkPrx
    from omero_model_Microscope_ice import Microscope, MicroscopePrx
    from omero_model_ChannelAnnotationLink_ice import ChannelAnnotationLink, ChannelAnnotationLinkPrx
    from omero_model_Instrument_ice import Instrument, InstrumentPrx
    from omero_model_DetectorSettings_ice import DetectorSettings, DetectorSettingsPrx
    from omero_model_Screen_ice import Screen, ScreenPrx
    from omero_model_StageLabel_ice import StageLabel, StageLabelPrx
    from omero_model_ObjectiveSettings_ice import ObjectiveSettings, ObjectiveSettingsPrx
    from omero_model_EventType_ice import EventType, EventTypePrx
    from omero_model_ThumbnailGenerationJob_ice import ThumbnailGenerationJob, ThumbnailGenerationJobPrx
    from omero_model_Channel_ice import Channel, ChannelPrx
    from omero_model_Event_ice import Event, EventPrx
    from omero_model_XmlAnnotation_ice import XmlAnnotation, XmlAnnotationPrx
    from omero_model_MicrobeamManipulationType_ice import MicrobeamManipulationType, MicrobeamManipulationTypePrx
    from omero_model_Dichroic_ice import Dichroic, DichroicPrx
    from omero_model_Frequency_ice import Frequency, FrequencyPrx
    from omero_model_TagAnnotation_ice import TagAnnotation, TagAnnotationPrx
    from omero_model_ProjectionDef_ice import ProjectionDef, ProjectionDefPrx
    from omero_model_Label_ice import Label, LabelPrx
    from omero_model_Thumbnail_ice import Thumbnail, ThumbnailPrx
    from omero_model_Binning_ice import Binning, BinningPrx
    from omero_model_Objective_ice import Objective, ObjectivePrx
    from omero_model_Rectangle_ice import Rectangle, RectanglePrx
    from omero_model_ProjectionType_ice import ProjectionType, ProjectionTypePrx
    from omero_model_PixelsOriginalFileMap_ice import PixelsOriginalFileMap, PixelsOriginalFileMapPrx
    from omero_model_AdminPrivilege_ice import AdminPrivilege, AdminPrivilegePrx
    from omero_model_DatasetImageLink_ice import DatasetImageLink, DatasetImageLinkPrx
    from omero_model_Illumination_ice import Illumination, IlluminationPrx
    from omero_model_DimensionOrder_ice import DimensionOrder, DimensionOrderPrx
    from omero_model_ShareMember_ice import ShareMember, ShareMemberPrx
    from omero_model_Time_ice import Time, TimePrx
    from omero_model_ReverseIntensityContext_ice import ReverseIntensityContext, ReverseIntensityContextPrx
    from omero_model_JobOriginalFileLink_ice import JobOriginalFileLink, JobOriginalFileLinkPrx
    from omero_model_Link_ice import Link, LinkPrx
    from omero_model_PlateAcquisition_ice import PlateAcquisition, PlateAcquisitionPrx
    from omero_model_Arc_ice import Arc, ArcPrx
    from omero_model_ListAnnotation_ice import ListAnnotation, ListAnnotationPrx
    from omero_model_Well_ice import Well, WellPrx
    from omero_model_ArcType_ice import ArcType, ArcTypePrx
    from omero_model_TextAnnotation_ice import TextAnnotation, TextAnnotationPrx
    from omero_model_AcquisitionMode_ice import AcquisitionMode, AcquisitionModePrx
    from omero_model_ProjectDatasetLink_ice import ProjectDatasetLink, ProjectDatasetLinkPrx
    from omero_model_Permissions_ice import Permissions, PermissionsPrx
    from omero_model_ExperimenterGroupAnnotationLink_ice import ExperimenterGroupAnnotationLink, ExperimenterGroupAnnotationLinkPrx
    from omero_model_RoiAnnotationLink_ice import RoiAnnotationLink, RoiAnnotationLinkPrx
    from omero_model_Path_ice import Path, PathPrx
    from omero_model_Details_ice import Details, DetailsPrx
    from omero_model_Annotation_ice import Annotation, AnnotationPrx
    from omero_model_MicrobeamManipulation_ice import MicrobeamManipulation, MicrobeamManipulationPrx
    from omero_model_PlaneInfoAnnotationLink_ice import PlaneInfoAnnotationLink, PlaneInfoAnnotationLinkPrx
    from omero_model_LightSourceAnnotationLink_ice import LightSourceAnnotationLink, LightSourceAnnotationLinkPrx
    from omero_model_FileAnnotation_ice import FileAnnotation, FileAnnotationPrx
    from omero_model_Pulse_ice import Pulse, PulsePrx
    from omero_model_SessionAnnotationLink_ice import SessionAnnotationLink, SessionAnnotationLinkPrx
    from omero_model_TransmittanceRange_ice import TransmittanceRange, TransmittanceRangePrx
    from omero_model_RenderingDef_ice import RenderingDef, RenderingDefPrx
    from omero_model_DetectorType_ice import DetectorType, DetectorTypePrx
    from omero_model_TimestampAnnotation_ice import TimestampAnnotation, TimestampAnnotationPrx
    from omero_model_BooleanAnnotation_ice import BooleanAnnotation, BooleanAnnotationPrx
    from omero_model_IObject_ice import IObject, IObjectPrx
    from omero_model_ExperimenterGroup_ice import ExperimenterGroup, ExperimenterGroupPrx
    from omero_model_WellReagentLink_ice import WellReagentLink, WellReagentLinkPrx
    from omero_model_ProjectAnnotationLink_ice import ProjectAnnotationLink, ProjectAnnotationLinkPrx
    from omero_model_PixelDataJob_ice import PixelDataJob, PixelDataJobPrx
    from omero_model_TermAnnotation_ice import TermAnnotation, TermAnnotationPrx
    from omero_model_NamedValue_ice import NamedValue, NamedValuePrx
    from omero_model_CommentAnnotation_ice import CommentAnnotation, CommentAnnotationPrx
    from omero_model_Shape_ice import Shape, ShapePrx
    from omero_model_LightPathEmissionFilterLink_ice import LightPathEmissionFilterLink, LightPathEmissionFilterLinkPrx
    from omero_model_Filament_ice import Filament, FilamentPrx
    from omero_model_Ellipse_ice import Ellipse, EllipsePrx
    from omero_model_LaserMedium_ice import LaserMedium, LaserMediumPrx
    from omero_model_Length_ice import Length, LengthPrx
    from omero_model_Session_ice import Session, SessionPrx
    from omero_model_LightSource_ice import LightSource, LightSourcePrx
    from omero_model_LightPath_ice import LightPath, LightPathPrx
    from omero_model_Image_ice import Image, ImagePrx
    from omero_model_Line_ice import Line, LinePrx
    from omero_model_Polyline_ice import Polyline, PolylinePrx
    from omero_model_Roi_ice import Roi, RoiPrx
    from omero_model_LaserType_ice import LaserType, LaserTypePrx
    from omero_model_FilterSetExcitationFilterLink_ice import FilterSetExcitationFilterLink, FilterSetExcitationFilterLinkPrx
    from omero_model_ChecksumAlgorithm_ice import ChecksumAlgorithm, ChecksumAlgorithmPrx

    from omero_model_AcquisitionModeI import AcquisitionModeI
    from omero_model_AdminPrivilegeI import AdminPrivilegeI
    from omero_model_AffineTransformI import AffineTransformI
    from omero_model_AnnotationAnnotationLinkI import AnnotationAnnotationLinkI
    from omero_model_ArcI import ArcI
    from omero_model_ArcTypeI import ArcTypeI
    from omero_model_BinningI import BinningI
    from omero_model_BooleanAnnotationI import BooleanAnnotationI
    from omero_model_ChannelAnnotationLinkI import ChannelAnnotationLinkI
    from omero_model_ChannelBindingI import ChannelBindingI
    from omero_model_ChannelI import ChannelI
    from omero_model_ChecksumAlgorithmI import ChecksumAlgorithmI
    from omero_model_CommentAnnotationI import CommentAnnotationI
    from omero_model_ContrastMethodI import ContrastMethodI
    from omero_model_ContrastStretchingContextI import ContrastStretchingContextI
    from omero_model_CorrectionI import CorrectionI
    from omero_model_DBPatchI import DBPatchI
    from omero_model_DatasetAnnotationLinkI import DatasetAnnotationLinkI
    from omero_model_DatasetI import DatasetI
    from omero_model_DatasetImageLinkI import DatasetImageLinkI
    from omero_model_DetailsI import DetailsI
    from omero_model_DetectorAnnotationLinkI import DetectorAnnotationLinkI
    from omero_model_DetectorI import DetectorI
    from omero_model_DetectorSettingsI import DetectorSettingsI
    from omero_model_DetectorTypeI import DetectorTypeI
    from omero_model_DichroicAnnotationLinkI import DichroicAnnotationLinkI
    from omero_model_DichroicI import DichroicI
    from omero_model_DimensionOrderI import DimensionOrderI
    from omero_model_DoubleAnnotationI import DoubleAnnotationI
    from omero_model_ElectricPotentialI import ElectricPotentialI
    from omero_model_EllipseI import EllipseI
    from omero_model_EventI import EventI
    from omero_model_EventLogI import EventLogI
    from omero_model_EventTypeI import EventTypeI
    from omero_model_ExperimentI import ExperimentI
    from omero_model_ExperimentTypeI import ExperimentTypeI
    from omero_model_ExperimenterAnnotationLinkI import ExperimenterAnnotationLinkI
    from omero_model_ExperimenterGroupAnnotationLinkI import ExperimenterGroupAnnotationLinkI
    from omero_model_ExperimenterGroupI import ExperimenterGroupI
    from omero_model_ExperimenterI import ExperimenterI
    from omero_model_ExternalInfoI import ExternalInfoI
    from omero_model_FamilyI import FamilyI
    from omero_model_FilamentI import FilamentI
    from omero_model_FilamentTypeI import FilamentTypeI
    from omero_model_FileAnnotationI import FileAnnotationI
    from omero_model_FilesetAnnotationLinkI import FilesetAnnotationLinkI
    from omero_model_FilesetEntryI import FilesetEntryI
    from omero_model_FilesetI import FilesetI
    from omero_model_FilesetJobLinkI import FilesetJobLinkI
    from omero_model_FilterAnnotationLinkI import FilterAnnotationLinkI
    from omero_model_FilterI import FilterI
    from omero_model_FilterSetEmissionFilterLinkI import FilterSetEmissionFilterLinkI
    from omero_model_FilterSetExcitationFilterLinkI import FilterSetExcitationFilterLinkI
    from omero_model_FilterSetI import FilterSetI
    from omero_model_FilterTypeI import FilterTypeI
    from omero_model_FolderAnnotationLinkI import FolderAnnotationLinkI
    from omero_model_FolderI import FolderI
    from omero_model_FolderImageLinkI import FolderImageLinkI
    from omero_model_FolderRoiLinkI import FolderRoiLinkI
    from omero_model_FormatI import FormatI
    from omero_model_FrequencyI import FrequencyI
    from omero_model_GenericExcitationSourceI import GenericExcitationSourceI
    from omero_model_GroupExperimenterMapI import GroupExperimenterMapI
    from omero_model_IlluminationI import IlluminationI
    from omero_model_ImageAnnotationLinkI import ImageAnnotationLinkI
    from omero_model_ImageI import ImageI
    from omero_model_ImagingEnvironmentI import ImagingEnvironmentI
    from omero_model_ImmersionI import ImmersionI
    from omero_model_ImportJobI import ImportJobI
    from omero_model_IndexingJobI import IndexingJobI
    from omero_model_InstrumentAnnotationLinkI import InstrumentAnnotationLinkI
    from omero_model_InstrumentI import InstrumentI
    from omero_model_IntegrityCheckJobI import IntegrityCheckJobI
    from omero_model_JobI import JobI
    from omero_model_JobOriginalFileLinkI import JobOriginalFileLinkI
    from omero_model_JobStatusI import JobStatusI
    from omero_model_LabelI import LabelI
    from omero_model_LaserI import LaserI
    from omero_model_LaserMediumI import LaserMediumI
    from omero_model_LaserTypeI import LaserTypeI
    from omero_model_LengthI import LengthI
    from omero_model_LightEmittingDiodeI import LightEmittingDiodeI
    from omero_model_LightPathAnnotationLinkI import LightPathAnnotationLinkI
    from omero_model_LightPathEmissionFilterLinkI import LightPathEmissionFilterLinkI
    from omero_model_LightPathExcitationFilterLinkI import LightPathExcitationFilterLinkI
    from omero_model_LightPathI import LightPathI
    from omero_model_LightSettingsI import LightSettingsI
    from omero_model_LightSourceAnnotationLinkI import LightSourceAnnotationLinkI
    from omero_model_LinkI import LinkI
    from omero_model_ListAnnotationI import ListAnnotationI
    from omero_model_LogicalChannelI import LogicalChannelI
    from omero_model_LongAnnotationI import LongAnnotationI
    from omero_model_MapAnnotationI import MapAnnotationI
    from omero_model_MaskI import MaskI
    from omero_model_MediumI import MediumI
    from omero_model_MetadataImportJobI import MetadataImportJobI
    from omero_model_MicrobeamManipulationI import MicrobeamManipulationI
    from omero_model_MicrobeamManipulationTypeI import MicrobeamManipulationTypeI
    from omero_model_MicroscopeI import MicroscopeI
    from omero_model_MicroscopeTypeI import MicroscopeTypeI
    from omero_model_NamespaceAnnotationLinkI import NamespaceAnnotationLinkI
    from omero_model_NamespaceI import NamespaceI
    from omero_model_NodeAnnotationLinkI import NodeAnnotationLinkI
    from omero_model_NodeI import NodeI
    from omero_model_OTFI import OTFI
    from omero_model_ObjectiveAnnotationLinkI import ObjectiveAnnotationLinkI
    from omero_model_ObjectiveI import ObjectiveI
    from omero_model_ObjectiveSettingsI import ObjectiveSettingsI
    from omero_model_OriginalFileAnnotationLinkI import OriginalFileAnnotationLinkI
    from omero_model_OriginalFileI import OriginalFileI
    from omero_model_ParseJobI import ParseJobI
    from omero_model_PathI import PathI
    from omero_model_PermissionsI import PermissionsI
    from omero_model_PhotometricInterpretationI import PhotometricInterpretationI
    from omero_model_PixelDataJobI import PixelDataJobI
    from omero_model_PixelsI import PixelsI
    from omero_model_PixelsOriginalFileMapI import PixelsOriginalFileMapI
    from omero_model_PixelsTypeI import PixelsTypeI
    from omero_model_PlaneInfoAnnotationLinkI import PlaneInfoAnnotationLinkI
    from omero_model_PlaneInfoI import PlaneInfoI
    from omero_model_PlaneSlicingContextI import PlaneSlicingContextI
    from omero_model_PlateAcquisitionAnnotationLinkI import PlateAcquisitionAnnotationLinkI
    from omero_model_PlateAcquisitionI import PlateAcquisitionI
    from omero_model_PlateAnnotationLinkI import PlateAnnotationLinkI
    from omero_model_PlateI import PlateI
    from omero_model_PointI import PointI
    from omero_model_PolygonI import PolygonI
    from omero_model_PolylineI import PolylineI
    from omero_model_PowerI import PowerI
    from omero_model_PressureI import PressureI
    from omero_model_ProjectAnnotationLinkI import ProjectAnnotationLinkI
    from omero_model_ProjectDatasetLinkI import ProjectDatasetLinkI
    from omero_model_ProjectI import ProjectI
    from omero_model_ProjectionAxisI import ProjectionAxisI
    from omero_model_ProjectionDefI import ProjectionDefI
    from omero_model_ProjectionTypeI import ProjectionTypeI
    from omero_model_PulseI import PulseI
    from omero_model_QuantumDefI import QuantumDefI
    from omero_model_ReagentAnnotationLinkI import ReagentAnnotationLinkI
    from omero_model_ReagentI import ReagentI
    from omero_model_RectangleI import RectangleI
    from omero_model_RenderingDefI import RenderingDefI
    from omero_model_RenderingModelI import RenderingModelI
    from omero_model_ReverseIntensityContextI import ReverseIntensityContextI
    from omero_model_RoiAnnotationLinkI import RoiAnnotationLinkI
    from omero_model_RoiI import RoiI
    from omero_model_ScreenAnnotationLinkI import ScreenAnnotationLinkI
    from omero_model_ScreenI import ScreenI
    from omero_model_ScreenPlateLinkI import ScreenPlateLinkI
    from omero_model_ScriptJobI import ScriptJobI
    from omero_model_SessionAnnotationLinkI import SessionAnnotationLinkI
    from omero_model_SessionI import SessionI
    from omero_model_ShapeAnnotationLinkI import ShapeAnnotationLinkI
    from omero_model_ShareI import ShareI
    from omero_model_ShareMemberI import ShareMemberI
    from omero_model_StageLabelI import StageLabelI
    from omero_model_StatsInfoI import StatsInfoI
    from omero_model_TagAnnotationI import TagAnnotationI
    from omero_model_TemperatureI import TemperatureI
    from omero_model_TermAnnotationI import TermAnnotationI
    from omero_model_ThumbnailGenerationJobI import ThumbnailGenerationJobI
    from omero_model_ThumbnailI import ThumbnailI
    from omero_model_TimeI import TimeI
    from omero_model_TimestampAnnotationI import TimestampAnnotationI
    from omero_model_TransmittanceRangeI import TransmittanceRangeI
    from omero_model_UploadJobI import UploadJobI
    from omero_model_WellAnnotationLinkI import WellAnnotationLinkI
    from omero_model_WellI import WellI
    from omero_model_WellReagentLinkI import WellReagentLinkI
    from omero_model_WellSampleI import WellSampleI
    from omero_model_XmlAnnotationI import XmlAnnotationI

IceImport.load("omero_model_NamedValue_ice")
