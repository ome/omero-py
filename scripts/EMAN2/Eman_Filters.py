"""
 components/tools/OmeroPy/scripts/EMAN2/Eman_Filters.py 

-----------------------------------------------------------------------------
  Copyright (C) 2006-2010 University of Dundee. All rights reserved.


  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  
  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

------------------------------------------------------------------------------

This script uses EMAN2 to perform CTF correction on images in OMERO. 
Uses the command line e2ctf.py 
Uploads the resulting CTF-corrected images into a new dataset. 
    
@author  Will Moore &nbsp;&nbsp;&nbsp;&nbsp;
<a href="mailto:will@lifesci.dundee.ac.uk">will@lifesci.dundee.ac.uk</a>
@version 3.0
<small>
(<b>Internal version:</b> $Revision: $Date: $)
</small>
@since 3.0-Beta4.2
 
"""

from EMAN2 import *
import os

import numpy

import omero
import omero_api_Gateway_ice    # see http://tinyurl.com/icebuserror
import omero.scripts as scripts
from omero.rtypes import *
import omero.util.script_utils as scriptUtil


# keep track of log strings. 
logStrings = []

def log(text):
    """
    Adds the text to a list of logs. Compiled into figure legend at the end.
    """
    #print text
    logStrings.append(text)
    

def emanFilter(session, parameterMap):
    """
    This is where the action happens.
    For each image, we get the data from OMERO as an EMData object, do the filtering and write back to OMERO. 
    """
    
    # create services we need 
    queryService = session.getQueryService()
    gateway = session.createGateway()
    rawFileStore = session.createRawFileStore()
    rawPixelStore = session.createRawPixelsStore()
    rawPixelStoreUpload = session.createRawPixelsStore()
    renderingEngine = session.createRenderingEngine()
    pixelsService = session.getPixelsService()
    
    imageIds = []
    
    dataType = parameterMap["Data_Type"]
    if dataType == "Image":
        for imageId in parameterMap["IDs"]:
            iId = long(imageId.getValue())
            imageIds.append(iId)
    else:   # Dataset
        for datasetId in parameterMap["IDs"]:
            datasetIds = []
            try:
                dId = long(datasetId.getValue())
                datasetIds.append(dId)
            except: pass
            # simply aggregate all images from the datasets
            images = gateway.getImages(omero.api.ContainerClass.Dataset, datasetIds)
            for i in images:
                imageIds.append(i.getId().getValue())
            
    if len(imageIds) == 0:
        return
        
    # get the project from the first image
    project = None
    dataset = None
    imageId = imageIds[0]
    query_string = "select i from Image i join fetch i.datasetLinks idl join fetch idl.parent d join fetch d.projectLinks pl join fetch pl.parent where i.id in (%s)" % imageId
    image = queryService.findByQuery(query_string, None)
    if image:
        for link in image.iterateDatasetLinks():
            dataset = link.parent
            print "Dataset", dataset.name.val
            for dpLink in dataset.iterateProjectLinks():
                project = dpLink.parent
                print "Project", project.name.val
                break # only use 1st Project
            break    # only use 1st Dataset
    
    if "New_Dataset_Name" in parameterMap:
        # make a dataset for images
        dataset = omero.model.DatasetI()
        dataset.name = rstring(parameterMap["New_Dataset_Name"])
        dataset = gateway.saveAndReturnObject(dataset)
        if project:        # and put it in the same project
            link = omero.model.ProjectDatasetLinkI()
            link.parent = omero.model.ProjectI(project.id.val, False)
            link.child = omero.model.DatasetI(dataset.id.val, False)
            gateway.saveAndReturnObject(link)
    
    filterName = parameterMap["Filter_Name"]
    paramStrings = []
    filterParamMap = None
    if "Filter_Params" in parameterMap:
        filterParamMap = {}
        fpMap = parameterMap["Filter_Params"]
        for p, v in fpMap.items():
            paramStrings.append("%s: %s" % (p, v.getValue())) # get value from rtype
            try:
                filterParamMap[p] = float(v.getValue())  # if the value is a float
            except:
                filterParamMap[p] = v.getValue()
    paramString = ", ".join(paramStrings)   # just for adding to new image description
    
    e = EMData()
    bypassOriginalFile = True
    
    for imageId in imageIds:
        # set up pixel-store and get the pixels object
        query_string = "select p from Pixels p join fetch p.image as i join fetch p.pixelsType where i.id='%d'" % imageId
        pixels = queryService.findByQuery(query_string, None)
        sizeX = pixels.getSizeX().getValue()
        sizeY = pixels.getSizeY().getValue()
        sizeZ = pixels.getSizeZ().getValue()
        sizeC = pixels.getSizeC().getValue()
        sizeT = pixels.getSizeT().getValue()
        rawPixelStore.setPixelsId(pixels.getId().getValue(), bypassOriginalFile)
        em = EMData(sizeX,sizeY,sizeZ)
        pixelsType = pixels.pixelsType
        # create the new image, ready to take planes
        description = "Created from image ID: %s by applying EMAN2 filter: '%s' with parameters: %s" % (imageId, filterName, paramString)
        imageName = pixels.image.name.val   # new image has same name
        print imageName, description
        
        iId = None
        image = None
        # need to loop through extra dimensions, since EMAN2 only handles 3D. 
        for theC in range(sizeC):
            minValue = None
            maxValue = 0
            for theT in range(sizeT):
                for z in range(sizeZ):
                    plane2D = scriptUtil.downloadPlane(rawPixelStore, pixels, z, theC, theT)
                    plane2D.resize((sizeY, sizeX))  # not sure why we have to resize (y, x)
                    EMNumPy.numpy2em(plane2D, e)
                    em.insert_clip(e,(0,0,z))
                # do the filtering
                if filterParamMap:  em.process_inplace(filterName, filterParamMap)
                else:   em.process_inplace(filterName)
                # convert back to numpy (datatype may be different) and upload to OMERO as new image
                filteredPlanes = EMNumPy.em2numpy(em)
                print "em.get_zsize()", em.get_zsize()
                print "filteredPlanes", filteredPlanes.shape
                if iId == None:
                    iId = createImage(pixelsService, queryService, filteredPlanes, sizeT, sizeC, imageName, description)
                    image = gateway.getImage(iId)
                    pixelsId = image.getPrimaryPixels().getId().getValue()
                    rawPixelStoreUpload.setPixelsId(pixelsId, bypassOriginalFile)
                if em.get_zsize() > 1:      # 3D array
                    for z, plane in enumerate(filteredPlanes):
                        if minValue == None: minValue = plane.min()
                        minValue = min(minValue, plane.min())
                        maxValue = max(maxValue, plane.max())
                        scriptUtil.uploadPlane(rawPixelStoreUpload, plane, z, theC, theT)
                else:   # 2D array
                    if minValue == None: minValue = filteredPlanes.min()
                    minValue = min(minValue, filteredPlanes.min())
                    maxValue = max(maxValue, filteredPlanes.max())
                    scriptUtil.uploadPlane(rawPixelStoreUpload, filteredPlanes, z, theC, theT)
            print "Setting the min, max ", minValue, maxValue
            pixelsService.setChannelGlobalMinMax(pixelsId, theC, float(minValue), float(maxValue))
            scriptUtil.resetRenderingSettings(renderingEngine, pixelsId, theC, minValue, maxValue)

        
        image.name = rstring(imageName)
        image.description = rstring(description)
        gateway.saveObject(image)
        # put image in dataset
        if dataset:
            dlink = omero.model.DatasetImageLinkI()
            dlink.parent = omero.model.DatasetI(dataset.id.val, False)
            dlink.child = omero.model.ImageI(iId, False)
            gateway.saveAndReturnObject(dlink)
        
        
def createImage(pixelsService, queryService, numpyData, sizeT, sizeC, imageName, description):
    
    pType = numpyData.dtype.name
    if len(numpyData.shape) == 3:
        sizeZ, sizeY, sizeX = numpyData.shape
    elif len(numpyData.shape) == 2:
        sizeY, sizeX = numpyData.shape
        sizeZ = 1
    pixelsType = queryService.findByQuery("from PixelsType as p where p.value='%s'" % pType, None) # omero::model::PixelsType
    if pixelsType == None and pType.startswith("float"):
        pixelsType = queryService.findByQuery("from PixelsType as p where p.value='%s'" % "float", None) # omero::model::PixelsType
    if pixelsType == None:
        raise("Unknown pixels type for: " % pType)
    #iId = gateway.copyImage(imageId, sizeX, sizeY, sizeT, sizeZ, channelList, None)
    channelList = range(sizeC)
    print sizeX, sizeY, sizeZ, sizeT, channelList, pixelsType, imageName, description
    iId = pixelsService.createImage(sizeX, sizeY, sizeZ, sizeT, channelList, pixelsType, imageName, description)
    return iId.getValue()

def runAsScript():
    """
    The main entry point of the script, as called by the client via the scripting service, passing the required parameters. 
    """
    dataTypes = [rstring('Dataset'),rstring('Image')]
    
    client = scripts.client('Eman_Filters.py', """Use EMAN2 to filter images and upload results back to OMERO. 
Filters: http://blake.bcm.edu/eman2/processors.html
See http://trac.openmicroscopy.org.uk/omero/wiki/EmPreviewFunctionality""", 
    scripts.String("Data_Type", optional=False, grouping="1",
        description="The data you want to work with.", values=dataTypes, default="Dataset"),
    scripts.List("IDs", optional=False, grouping="2",
        description="List of Dataset IDs or Image IDs").ofType(rlong(0)),
    scripts.String("Filter_Name", optional=False, grouping="3",
        description="E.g. 'filter.lowpass.gauss'   http://blake.bcm.edu/eman2/processors.html"),
    scripts.Map("Filter_Params", grouping="4",  # map of strings. Where possible, values are converted to floats
        description="Map of parameters to add to filter. E.g. sigma: 0.125"), # See http://blake.bcm.edu/emanwiki/Eman2ProgQuickstart
    scripts.String("New_Dataset_Name", grouping="5",
        description="If specified, put the filtered images in a new dataset.")) 
    
    try:
        session = client.getSession()
    
        # process the list of args above. 
        parameterMap = {}
        for key in client.getInputKeys():
            if client.getInput(key):
                parameterMap[key] = client.getInput(key).getValue()
    
        emanFilter(session, parameterMap)
    except: raise
    finally: client.closeSession()
    
if __name__ == "__main__":
    runAsScript()
    
