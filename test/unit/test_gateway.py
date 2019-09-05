#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2014 Glencoe Software, Inc. All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


"""
Test of various things under omero.gateway
"""

import Ice
import pytest

from omero.gateway import BlitzGateway, ImageWrapper, \
    ExperimenterWrapper, ProjectWrapper, AnnotationWrapper, \
    PlateWrapper, WellWrapper, LogicalChannelWrapper
from omero.model import ImageI, PixelsI, ExperimenterI, EventI, \
    ProjectI, TagAnnotationI, FileAnnotationI, OriginalFileI, \
    MapAnnotationI, NamedValue, PlateI, WellI, \
    LogicalChannelI, LengthI, IlluminationI, BinningI, \
    DetectorSettingsI
from omero.model.enums import UnitsLength
from omero.rtypes import rstring, rtime, rlong, rint, rdouble


class MockQueryService(object):

    def findByQuery(self, query, params, _ctx=None):
        experimenter = ExperimenterI()
        experimenter.firstName = rstring('first_name')
        experimenter.lastName = rstring('last_name')
        return experimenter


class MockConnection(object):

    SERVICE_OPTS = dict()

    def getQueryService(self):
        return MockQueryService()

    def getMaxPlaneSize(self):
        return (64, 64)


@pytest.fixture(scope='function')
def wrapped_image():
    image = ImageI()
    image.id = rlong(1L)
    image.description = rstring('description')
    image.name = rstring('name')
    image.acquisitionDate = rtime(1000)  # In milliseconds
    image.details.owner = ExperimenterI(1L, False)
    creation_event = EventI()
    creation_event.time = rtime(2000)  # In milliseconds
    image.details.creationEvent = creation_event
    return ImageWrapper(conn=MockConnection(), obj=image)


class TestObjectsUnicode(object):
    """
    Tests that ExperimenterWrapper methods return correct unicode
    """

    def test_experimenter(self):
        """
        Tests methods handled by BlitzObjectWrapper.__getattr__

        These will return unicode strings
        """
        first_name = u'fîrst_nąmę'
        last_name = u'làst_NÅMÉ'
        experimenter = ExperimenterI()
        experimenter.firstName = rstring(first_name)
        experimenter.lastName = rstring(last_name)

        exp = ExperimenterWrapper(None, experimenter)
        assert exp.getFirstName() == first_name
        assert exp.getLastName() == last_name
        assert exp.getFullName() == "%s %s" % (first_name, last_name)

    def test_project(self):
        """Tests BlitzObjectWrapper.getName() returns string"""
        name = u'Pròjëct ©ψ'
        desc = u"Desc Φωλ"
        project = ProjectI()
        project.name = rstring(name)
        project.description = rstring(desc)

        proj = ProjectWrapper(None, project)
        assert proj.getName() == name.encode('utf8')
        assert proj.name == name
        assert proj.getDescription() == desc.encode('utf8')
        assert proj.description == desc

    def test_tag_annotation(self):
        """Tests AnnotationWrapper methods return strings"""
        ns = u'πλζ.test.ζ'
        text_value = u'Tαg - ℗'
        obj = TagAnnotationI()
        obj.textValue = rstring(text_value)
        obj.ns = rstring(ns)

        tag = AnnotationWrapper._wrap(None, obj)
        assert tag.getValue() == text_value.encode('utf8')
        assert tag.textValue == text_value
        assert tag.getNs() == ns.encode('utf8')
        assert tag.ns == ns

    def test_file_annotation(self):
        """Tests AnnotationWrapper methods return strings"""
        file_name = u'₩€_file_$$'
        f = OriginalFileI()
        f.name = rstring(file_name)
        obj = FileAnnotationI()
        obj.file = f

        file_ann = AnnotationWrapper._wrap(None, obj)
        assert file_ann.getFileName() == file_name.encode('utf8')

    def test_map_annotation(self):
        """Tests MapAnnotationWrapper.getValue() returns unicode"""
        values = [(u'one', u'₹₹'), (u'two', u'¥¥')]
        obj = MapAnnotationI()
        data = [NamedValue(d[0], d[1]) for d in values]
        obj.setMapValue(data)

        map_ann = AnnotationWrapper._wrap(None, obj)
        assert map_ann.getValue() == values

    def test_plate(self):
        """Tests label methods for Plate and Well."""
        name = u'plate_∞'
        cols = 4
        rows = 3
        obj = PlateI()
        obj.name = rstring(name)

        plate = PlateWrapper(None, obj)
        assert plate.getName() == name.encode('utf8')
        plate._gridSize = {'rows': rows, 'columns': cols}
        assert plate.getColumnLabels() == [c for c in range(1, cols + 1)]
        assert plate.getRowLabels() == ['A', 'B', 'C']

        well_obj = WellI()
        well_obj.column = rint(1)
        well_obj.row = rint(2)

        class MockWell(WellWrapper):
            def getParent(self):
                return plate

        well = MockWell(None, well_obj)
        assert well.getWellPos() == "C2"


class TestBlitzObjectGetAttr(object):
    """
    Tests returning objects via the BlitzObject.__getattr__
    """

    def test_logical_channel(self):
        name = u'₩€_name_$$'
        ill_val = u'πλζ.test.ζ'
        fluor = u'GFP-₹₹'
        binning_value = u'Φωλ'
        ph_size = 1.11
        ph_units = UnitsLength.MICROMETER
        ex_wave = 3.34
        ex_units = UnitsLength.ANGSTROM
        version = 123
        zoom = 100
        gain = 1010.23

        obj = LogicalChannelI()
        obj.name = rstring(name)
        obj.pinHoleSize = LengthI(ph_size, ph_units)
        illumination = IlluminationI()
        illumination.value = rstring(ill_val)
        obj.illumination = illumination
        obj.excitationWave = LengthI(ex_wave, ex_units)
        obj.setFluor(rstring(fluor))

        ds = DetectorSettingsI()
        ds.version = rint(version)
        ds.gain = rdouble(gain)
        ds.zoom = rdouble(zoom)
        binning = BinningI()
        binning.value = rstring(binning_value)
        ds.binning = binning
        obj.detectorSettings = ds

        channel = LogicalChannelWrapper(None, obj)
        assert channel.getName() == name.encode('utf8')
        assert channel.name == name
        assert channel.getPinHoleSize().getValue() == ph_size
        assert channel.getPinHoleSize().getUnit() == ph_units
        assert channel.getPinHoleSize().getSymbol() == 'µm'
        # Illumination is an enumeration
        assert channel.getIllumination().getValue() == ill_val.encode('utf8')
        assert channel.getExcitationWave().getValue() == ex_wave
        assert channel.getExcitationWave().getUnit() == ex_units
        assert channel.getExcitationWave().getSymbol() == 'Å'
        assert channel.getFluor() == fluor
        assert channel.fluor == fluor

        d_settings = channel.getDetectorSettings()
        assert d_settings.getVersion() == version
        assert d_settings.version == version
        assert d_settings.getGain() == gain
        assert d_settings.gain == gain
        assert d_settings.getZoom() == zoom
        assert d_settings.getBinning().getValue() == binning_value
        assert d_settings.getBinning().value == binning_value


class TestBlitzGatewayUnicode(object):
    """
    Tests to ensure that unicode encoding of usernames and passwords are
    performed successfully.  `gateway.connect()` will not even attempt to
    perform a connection and just return `False` if the encoding fails.
    """

    def test_unicode_username(self):
        with pytest.raises(Ice.ConnectionRefusedException):
            gateway = BlitzGateway(
                username=u'ążźćółę', passwd='secret',
                host='localhost', port=65535
            )
            gateway.connect()

    def test_unicode_password(self):
        with pytest.raises(Ice.ConnectionRefusedException):
            gateway = BlitzGateway(
                username='user', passwd=u'ążźćółę',
                host='localhost', port=65535
            )
            gateway.connect()


class TestBlitzGatewayImageWrapper(object):
    """Tests for various methods associated with the `ImageWrapper`."""

    def assert_data(self, data):
        assert data['description'] == 'description'
        assert data['author'] == 'first_name last_name'
        assert data['date'] == 1.0  # In seconds
        assert data['type'] == 'Image'
        assert data['id'] == 1L
        assert data['name'] == 'name'

    def test_simple_marshal(self, wrapped_image):
        self.assert_data(wrapped_image.simpleMarshal())

    def test_simple_marshal_tiled(self, wrapped_image):
        image = wrapped_image._obj
        pixels = PixelsI()
        pixels.sizeX = rint(65)
        pixels.sizeY = rint(65)
        image.addPixels(pixels)
        data = wrapped_image.simpleMarshal(xtra={'tiled': True})
        self.assert_data(data)
        assert data['tiled'] is True

    def test_simple_marshal_not_tiled(self, wrapped_image):
        data = wrapped_image.simpleMarshal(xtra={'tiled': True})
        self.assert_data(data)
        assert data['tiled'] is False
