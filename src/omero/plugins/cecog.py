#!/usr/bin/env python
"""
   Methods for working with cecog

   Copyright 2010 University of Dundee, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import os
import re
import sys
import exceptions

from omero.cli import BaseControl, CLI, OMERODIR
from omero_ext.argparse import FileType

import omero
import omero.constants

from omero.rtypes import *


class CecogControl(BaseControl):
    """CeCog integration plugin.

Provides actions for prepairing data and otherwise
integrating with Cecog. See the Run_Cecog_4.1.py
script.
    """

    # [MetaMorph_PlateScanPackage]
    #regex_subdirectories = re.compile('(?=[^_]).*?(?P<D>\d+).*?')
    #regex_position = re.compile('P(?P<P>.+?)_')
    #continuous_frames = 1
    regex_token = re.compile(r'(?P<Token>.+)\.')
    regex_time = re.compile(r'T(?P<T>\d+)')
    regex_channel = re.compile(r'_C(?P<C>.+?)(_|$)')
    regex_zslice = re.compile(r'_Z(?P<Z>\d+)')

    def _configure(self, parser):
        sub = parser.sub()

        class Action(object):

            def __init__(this, name):
                func = getattr(self, name)
                this.parser = sub.add_parser(name, help=func.__doc__, description=func.__doc__)
                this.parser.set_defaults(func=func)

            def add_argument(this, *args, **kwargs):
                this.parser.add_argument(*args, **kwargs)
                return this

        merge = Action("merge")
        merge.add_argument("path", help="Path to image files")

        rois = Action("rois")
        rois.add_argument("-f", "--file", required=True, help="Details file to be parsed")
        rois.add_argument("-i", "--image", required=True, help="Image id which should have ids attached")

    ##
    ## Public methods
    ##
    def merge(self, args):
        """Uses PIL to read multiple planes from a local folder.

Planes are combined and uploaded to OMERO as new images with additional T, C, Z dimensions.

It should be run as a local script (not via scripting service) in order that it has
access to the local users file system. Therefore need EMAN2 or PIL installed locally.

Example usage:
will$ bin/omero cecog merge /Applications/CecogPackage/Data/Demo_data/0037/

Since this dir does not contain folders, this will upload images in '0037' into a Dataset called Demo_data
in a Project called 'Data'.

will$ bin/omero cecog merge /Applications/CecogPackage/Data/Demo_data/

Since this dir does contain folders, this will look for images in all subdirectories of 'Demo_data' and
upload images into a Dataset called Demo_data in a Project called 'Data'.

Images will be combined in Z, C and T according to the MetaMorph_PlateScanPackage naming convention.
E.g. tubulin_P0037_T00005_Cgfp_Z1_S1.tiff is Point 37, Timepoint 5, Channel gfp, Z 1. S?
see /Applications/CecogPackage/CecogAnalyzer.app/Contents/Resources/resources/naming_schemes.conf
"""
        """
        Processes the command args, makes project and dataset then calls uploadDirAsImages() to process and
        upload the images to OMERO.
        """
        from omero.rtypes import unwrap
        from omero.util.script_utils import uploadDirAsImages

        path = args.path
        client = self.ctx.conn(args)
        queryService = client.sf.getQueryService()
        updateService = client.sf.getUpdateService()
        pixelsService = client.sf.getPixelsService()

        # if we don't have any folders in the 'dir' E.g. CecogPackage/Data/Demo_data/0037/
        # then 'Demo_data' becomes a dataset
        subDirs = []
        for f in os.listdir(path):
            fullpath = path + f
            # process folders in root dir:
            if os.path.isdir(fullpath):
                subDirs.append(fullpath)

        # get the dataset name and project name from path
        if len(subDirs) == 0:
            p = path[:-1]   # will remove the last folder
            p = os.path.dirname(p)
        else:
            if os.path.basename(path) == "":
                p = path[:-1]   # remove slash

        datasetName = os.path.basename(p)   # e.g. Demo_data
        p = p[:-1]
        p = os.path.dirname(p)
        projectName = os.path.basename(p)   # e.g. Data
        self.ctx.err("Putting images in Project: %s  Dataset: %s" % (projectName, datasetName))

        # create dataset
        dataset = omero.model.DatasetI()
        dataset.name = rstring(datasetName)
        dataset = updateService.saveAndReturnObject(dataset)
        # create project
        project = omero.model.ProjectI()
        project.name = rstring(projectName)
        project = updateService.saveAndReturnObject(project)
        # put dataset in project
        link = omero.model.ProjectDatasetLinkI()
        link.parent = omero.model.ProjectI(project.id.val, False)
        link.child = omero.model.DatasetI(dataset.id.val, False)
        updateService.saveAndReturnObject(link)

        if len(subDirs) > 0:
            for subDir in subDirs:
                self.ctx.err("Processing images in %s" % subDir)
                rv = uploadDirAsImages(client.sf, queryService, updateService, pixelsService, subDir, dataset)
                self.ctx.out("%s" % unwrap(rv))

        # if there are no sub-directories, just put all the images in the dir
        else:
            self.ctx.err("Processing images in %s" % path)
            rv = uploadDirAsImages(client.sf, queryService, updateService, pixelsService, path, dataset)
            self.ctx.out("%s" % unwrap(rv))

    def rois(self, args):
        """Parses an object_details text file, as generated by CeCog Analyzer and saves the data as ROIs on an Image in OMERO.

Text file is of the form:

frame	objID	classLabel	className	centerX	centerY	mean	        sd
1	    10  	6       	lateana	    1119	41	    76.8253796095	54.9305640673


Example usage:
bin/omero cecog rois -f Data/Demo_output/analyzed/0037/statistics/P0037__object_details.txt -i 502
"""
        """
        Processes the command args, parses the object_details.txt file and creates ROIs on the image specified in OMERO
        """
        filePath = args.file
        imageId = args.image
        if not os.path.exists(filePath):
            self.ctx.die(654, "Could find the object_details file at %s" % filePath)

        client = self.ctx.conn(args)
        updateService = client.sf.getUpdateService()
        object_details = open(filePath, 'r')

        try:
            for line in object_details:
                self.parseObject(updateService, imageId, line)
        finally:
            object_details.close()


    ##
    ## Internal methods
    ##
    def addRoi(self, updateService, imageId, x, y, theT, theZ, roiText=None, roiDescription=None):

        # create an ROI, add the point and save
        roi = omero.model.RoiI()
        roi.setImage(omero.model.ImageI(imageId, False))
        roi.setDescription(omero.rtypes.rstring(roiDescription))
        r = updateService.saveAndReturnObject(roi)

        # create and save a point
        point = omero.model.PointI()
        point.cx = rdouble(x)
        point.cy = rdouble(y)
        point.theZ = rint(theT)
        point.theT = rint(theZ)
        if roiText:
            point.textValue = rstring(roiText)    # for display only

        # link the point to the ROI and save it
        point.setRoi(r)
        r.addShape(point)
        updateService.saveAndReturnObject(point)

        return r.id.val


    def parseObject(self, updateService, imageId, line):
        """
        Parses a single line of cecog output and saves as a roi.

        Adds a Rectangle (particle) to the current OMERO image, at point x, y.
        Uses the self.image (OMERO image) and self.updateService
        """
        theZ = 0
        theT = None
        x = None
        y = None

        parts = line.split("\t")
        names = ("frame", "objID", "primaryClassLabel", "primaryClassName", "centerX", "centerY", "mean", "sd", "secondaryClassabel", "secondaryClassName", "secondaryMean", "secondarySd")
        values = {}
        for idx, name in enumerate(names):
            if len(parts) >= idx:
                values[name] = parts[idx]

        frame = values["frame"]
        try:
            frame = long(frame)
        except ValueError:
            self.ctx.dbg("Non-roi line: %s " % line)
            return

        theT = frame - 1
        className = values["primaryClassName"]
        x = float(values["centerX"])
        y = float(values["centerY"])

        description = ""
        for name in names:
            description += ("%s=%s\n" % (name, values.get(name, "(missing)")))

        if theT and x and y:
            self.ctx.err("Adding point '%s' to frame: %s, x: %s, y: %s" % (className, theT, x, y))
            self.ctx.out(self.addRoi(updateService, imageId, x, y, theT, theZ, className, description))

try:
    register("cecog", CecogControl, CecogControl.__doc__)
except NameError:
    if __name__ == "__main__":
        cli = CLI()
        cli.register("cecog", CecogControl, CecogControl.__doc__)
        cli.invoke(sys.argv[1:])
