#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# webclient_gateway
#
# Copyright (c) 2008-2011 University of Dundee.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Aleksandra Tarkowska <A(dot)Tarkowska(at)dundee(dot)ac(dot)uk>, 2012
#
# Version: 1.0
#

import logging
import json

try:
    long
except:
    # Python 3
    long = int

logger = logging.getLogger(__name__)


class GatewayConfig(object):

    """
    Global Gateway configuration:

    - :attr:`IMG_RDEFNS`:  a namespace for annotations linked on images holding
                           the default rendering settings object id.
    - :attr:`IMG_ROPTSNS`: a namespace for annotations linked on images holding
                           default rendering options that don't get saved in
                           the rendering settings.
    """

    def __init__(self):
        self.IMG_RDEFNS = None
        self.IMG_ROPTSNS = None


class ServiceOptsDict(dict):

    def __new__(cls, *args, **kwargs):
        return super(ServiceOptsDict, cls).__new__(cls, *args, **kwargs)

    def __init__(self, data=None, *args, **kwargs):
        if data is None:
            data = dict()
        if len(kwargs) > 0:
            for key, val in dict(*args, **kwargs).items():
                self[key] = val
        if isinstance(data, dict):
            for key in data:
                item = data[key]
                if self._testItem(item):
                    self[key] = str(item)
                else:
                    logger.debug(
                        "None or non- string, unicode or numeric type"
                        "values are ignored, (%r, %r)" % (key, item))
        else:
            raise AttributeError(
                "%s argument (%r:%s) must be a dictionary"
                % (self.__class__.__name__, data, type(data)))

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__,
                             super(ServiceOptsDict, self).__repr__())

    def __setitem__(self, key, item):
        """Set key to value as string."""
        if self._testItem(item):
            super(ServiceOptsDict, self).__setitem__(key, str(item))
            logger.debug("Setting %r to %r" % (key, item))
        else:
            raise AttributeError(
                "%s argument (%r:%s) must be a string, unicode or numeric type"
                % (self.__class__.__name__, item, type(item)))

    def __getitem__(self, key):
        """
        Return the value for key if key is in the dictionary.
        Raises a KeyError if key is not in the map.
        """
        try:
            return super(ServiceOptsDict, self).__getitem__(key)
        except KeyError:
            raise KeyError("Key %r not found in %r" % (key, self))

    def __delitem__(self, key):
        """
        Remove dict[key] from dict.
        Raises a KeyError if key is not in the map.
        """
        super(ServiceOptsDict, self).__delitem__(key)
        logger.debug("Deleting %r" % (key))

    def copy(self):
        """Returns a copy of this object."""
        return self.__class__(self)

    def clear(self):
        """Remove all items from the dictionary."""
        super(ServiceOptsDict, self).clear()

    def get(self, key, default=None):
        """
        Return the value for key if key is in the dictionary, else default.
        If default is not given, it defaults to None, so that this method
        never raises a KeyError.
        """
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def set(self, key, value):
        """Set key to value as string."""
        return self.__setitem__(key, value)

    def getOmeroGroup(self):
        return self.get('omero.group')

    def setOmeroGroup(self, value=None):
        if value is not None:
            self.set('omero.group', value)
        else:
            try:
                del self['omero.group']
            except KeyError:
                logger.debug("Key 'omero.group' not found in %r" % self)

    def getOmeroUser(self):
        return self.get('omero.user')

    def setOmeroUser(self, value=None):
        if value is not None:
            self.set('omero.user', value)
        else:
            try:
                del self['omero.user']
            except KeyError:
                logger.debug("Key 'omero.user' not found in %r" % self)

    def getOmeroShare(self):
        return self.get('omero.share')

    def setOmeroShare(self, value=None):
        if value is not None:
            self.set('omero.share', value)
        else:
            try:
                del self['omero.share']
            except KeyError:  # pragma: no cover
                logger.debug("Key 'omero.share' not found in %r" % self)

    def _testItem(self, item):
        if item is not None and not isinstance(item, bool) and \
            (isinstance(item, str) or
             isinstance(item, int) or
             isinstance(item, long) or
             isinstance(item, float)):
            return True
        return False


def toBoolean(val):
    """
    Get the boolean value of the provided input.

        If the value is a boolean return the value.
        Otherwise check to see if the value is in
        ["true", "yes", "y", "t", "1"]
        and returns True if value is in the list
    """

    if val is True or val is False:
        return val

    trueItems = ["true", "yes", "y", "t", "1", "on"]

    return str(val).strip().lower() in trueItems


def propertiesToDict(m, prefix=None):
    """
    Convert omero properties to nested dictionary, skipping common prefix
    """

    nested_dict = {}
    for item, value in m.items():
        d = nested_dict
        if prefix is not None:
            item = item.replace(prefix, "")
        items = item.split('.')
        for key in items[:-1]:
            d = d.setdefault(key, {})
        try:
            if value.strip().lower() in ('true', 'false'):
                d[items[-1]] = toBoolean(value)
            else:
                d[items[-1]] = json.loads(value)
        except:
            d[items[-1]] = value
    return nested_dict

def image_to_html(image):
    import base64

    try:
        pixsizeX = '{:.3f}'.format(image.getPixelSizeX())
        pixsizeY = '{:.3f}'.format(image.getPixelSizeY())
        pixsizeZ = '{:.3f}'.format(image.getPixelSizeZ())
        UnitX = image.getPixelSizeX(units=True).getUnit()
        UnitY = image.getPixelSizeY(units=True).getUnit()
        UnitZ = image.getPixelSizeZ(units=True).getUnit()
    except:
        pixsizeX, pixsizeY, pixsizeZ = 'na', 'na', 'na'
        UnitX, UnitY, UnitZ = 'na', 'na', 'na'

    html_style_header = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Image Details</title>
        <style>
            img {
                min-width: 250px; /* Set the minimum width for all images */
                min-height: 250px; /* Set the minimum height for all images */
            }
            .align-top {
            vertical-align: top;
            }
            .text-right {
            text-align: right;
            }
        </style>
    </head>
    """

    def obj_html(obj, otype):
        return f"""<tr>
                <td><b>{otype}</b></td>
                <td class=text-right>{obj.id if obj else ""}</td>
                <td class=text-right>{obj.name if obj else ""}</td>
                </tr>
            """

    # create a sub-table for image information
    table_imageinfo = f"""
    <table>
        <tr><th></th><th>ID</th><th>Name</th></tr>
        {obj_html(image, 'Image')}
        {obj_html(image.getParent(), 'Dataset')}
        {obj_html(image.getProject(), 'Project')}
    </table>
    """

    # get entries for thumbnail and dimensions
    encoded_image = base64.b64encode(image.getThumbnail()).decode('utf-8')
    dimensions = f"""(
        {image.getSizeT()},
        {image.getSizeC()},
        {image.getSizeZ()},
        {image.getSizeY()},
        {image.getSizeX()})"""
    physical_dims = f"""({pixsizeZ}, {pixsizeY}, {pixsizeX})""".format()
    physical_units = f"""({UnitZ}, {UnitY}, {UnitX})"""

    table_dimensions = f"""
    <table>\n
        <tr>\n
            <td><b>Dimensions (TCZYX): </b></td> <td class=text-right>{dimensions}</td>\n
        </tr>\n
        <tr>\n
            <td><b>Voxel/Pixel dimensions (ZYX): </b></td> <td class=text-right>{physical_dims}</td>\n
        </tr>\n
        <tr>\n
            <td><b>Physical units: </b></td> <td class=text-right>{physical_units}</td>\n
        </tr>\n
        <tr>\n
            <td><b>Channel Names: </b></td> <td class=text-right>{image.getChannelLabels()}</td>\n
        </tr>\n
    </table>
    """

    table_assembly = f"""
    <table>
    <tr>
        <td><div class="thumbnail">
            <img src="data:image/jpeg;base64,{encoded_image}" alt="Thumbnail">
        </div></td>
        <td class="align-top"><h2>Image information </h2>
        {table_imageinfo}
        </td>
    </tr>
    </table>
    <table>
        <tr>
            <td>{table_dimensions}</td>
        </tr>
    </table>
    """

    return '\n'.join([
        html_style_header,
        '<body>',
        table_assembly,
        '</body>',
        '</html>'
    ])