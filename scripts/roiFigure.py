"""
 components/tools/OmeroPy/scripts/roiFigure.py

-----------------------------------------------------------------------------
  Copyright (C) 2006-2009 University of Dundee. All rights reserved.


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

This script takes a number of images and displays regions defined by their ROIs as
zoomed panels beside the images.

@author  William Moore &nbsp;&nbsp;&nbsp;&nbsp;
<a href="mailto:will@lifesci.dundee.ac.uk">will@lifesci.dundee.ac.uk</a>
@author  Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
<a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
@author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
<a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
@version 3.0
<small>
(<b>Internal version:</b> $Revision: $Date: $)
</small>
@since 3.0-Beta4.1
 
"""

import omero.scripts as scripts
import omero.util.imageUtil as imgUtil
import omero.util.figureUtil as figUtil
import omero.util.script_utils as scriptUtil
from omero.rtypes import *
import omero.gateway
import omero_api_Gateway_ice	# see http://tinyurl.com/icebuserror
import omero_api_IRoi_ice
# import util.figureUtil as figUtil	# need to comment out for upload to work. But need import for script to work!!
import getopt, sys, os, subprocess
import Image, ImageDraw, ImageFont
import StringIO
from omero_sys_ParametersI import ParametersI
from datetime import date
	
JPEG = "image/jpeg"
PNG = "image/png"
formatExtensionMap = {JPEG:"jpg", PNG:"png"};

WHITE = (255,255,255)


logStrings = []
def log(text):
	"""
	Adds the text to a list of logs. Compiled into figure legend at the end.
	"""
	#print text
	logStrings.append(text)	


def addScalebar(scalebar, xIndent, yIndent, image, pixels, colour):
	""" adds a scalebar at the bottom right of an image, No text. 
	
	@scalebar 		length of scalebar in microns 
	@xIndent		indent from the right of the image
	@yIndent 		indent from the bottom of the image
	@image			the PIL image to add scalebar to. 
	@pixels 		the pixels object
	@colour 		colour of the overlay as r,g,b tuple
	"""
	draw = ImageDraw.Draw(image)
	if pixels.getPhysicalSizeX() == None:
		return False
	pixelSizeX = pixels.getPhysicalSizeX().getValue()
	if pixelSizeX <= 0:
		return False
	iWidth, iHeight = image.size
	lineThickness = (iHeight//100) + 1
	scaleBarY = iHeight - yIndent
	scaleBarX = iWidth - scalebar//pixelSizeX - xIndent
	scaleBarX2 = iWidth - xIndent
	if scaleBarX<=0 or scaleBarX2<=0 or scaleBarY<=0 or scaleBarX2>iWidth:
		return False
	for l in range(lineThickness):
		draw.line([(scaleBarX,scaleBarY), (scaleBarX2,scaleBarY)], fill=colour)
		scaleBarY -= 1
	return True


def getTimeIndexes(timePoints, maxFrames):
	""" 
	If we want to display a number of timepoints (e.g. 11), without exceeding maxFrames (e.g. 5), 
	need to pick a selection of t-indexes e.g. 0, 2, 4, 7, 10
	This method returns the list of indexes. """
	frames = min(maxFrames, timePoints)
	intervalCount = frames-1
	smallestInterval = (timePoints-1)/intervalCount
	# make a list of intervals, making the last intervals bigger if needed
	intervals = [smallestInterval] * intervalCount
	extra = (timePoints-1) % intervalCount
	for e in range(extra):
		lastIndex = -(e+1)
		intervals[lastIndex] += 1
	# convert the list of intervals into indexes. 
	indexes = []
	time = 0
	indexes.append(time)
	for i in range(frames-1):
		time += intervals[i]
		indexes.append(time)
	return indexes
		
	
def getROImovieView	(session, pixels, zStart, zEnd, tStart, tEnd, splitIndexes, channelNames, colourChannels, mergedIndexes, 
			mergedColours, roiX, roiY, roiWidth, roiHeight, roiZoom, tStep=1, spacer = 12, algorithm=None, stepping = 1, fontsize=24):
	""" This takes a ROI rectangle from an image and makes a movie canvas of the region in the ROI, zoomed 
		by a defined factor. 
	"""
	
	mode = "RGB"
	white = (255, 255, 255)	
	
	# create a rendering engine
	re = session.createRenderingEngine()
	
	sizeX = pixels.getSizeX().getValue()
	sizeY = pixels.getSizeY().getValue()
	sizeZ = pixels.getSizeZ().getValue()
	sizeC = pixels.getSizeC().getValue()
	sizeT = pixels.getSizeT().getValue()
	
	if pixels.getPhysicalSizeX():
		physicalX = pixels.getPhysicalSizeX().getValue()
	else:
		physicalX = 0 
	if pixels.getPhysicalSizeY():
		physicalY = pixels.getPhysicalSizeY().getValue()
	else:
		physicalY = 0
	log("  Pixel size (um): x: %s  y: %s" % (str(physicalX), str(physicalY)))
	log("  Image dimensions (pixels): x: %d  y: %d" % (sizeX, sizeY))
	
	log(" Projecting Movie Frame ROIs...")
	proStart = zStart
	proEnd = zEnd
	# make sure we're within Z range for projection. 
	if proEnd >= sizeZ:
		proEnd = sizeZ - 1
		if proStart > sizeZ:
			proStart = 0
		log(" WARNING: Current image has fewer Z-sections than the primary image projection.")
	if proStart < 0:
		proStart = 0
	log("  Projecting z range: %d - %d   (max Z is %d)" % (proStart+1, proEnd+1, sizeZ))
	# set up rendering engine with the pixels
	pixelsId = pixels.getId().getValue()
	re.lookupPixels(pixelsId)
	re.lookupRenderingDef(pixelsId)
	re.load()
	
	# now get each channel in greyscale (or colour)
	# a list of renderedImages (data as Strings) for the split-view row
	renderedImages = []
	panelWidth = 0
	channelMismatch = False
	# first, turn off all channels in pixels
	for i in range(sizeC): 
		re.setActive(i, False)		
			
	# turn on channels in mergedIndexes. 
	for i in mergedIndexes: 
		if i >= sizeC:
			channelMismatch = True
		else:
			rgba = mergedColours[i]
			re.setActive(i, True)
			re.setRGBA(i, *rgba)
				
	# get the combined image, using the existing rendering settings 
	channelsString = ", ".join([str(i) for i in mergedIndexes])
	log("  Rendering Movie channels: %s" % channelsString)
	
	queryService = session.getQueryService()
	box = (roiX, roiY, roiX+roiWidth, roiY+roiHeight)
	#timeIndexes = getTimeIndexes(tEnd-tStart, ROIframes)
	timeIndexes = range(tStart, tEnd, tStep)
	fullFirstFrame = None
	for timepoint in timeIndexes:
		merged = re.renderProjectedCompressed(algorithm, timepoint, stepping, proStart, proEnd)
		fullMergedImage = Image.open(StringIO.StringIO(merged))
		if fullFirstFrame == None:
			fullFirstFrame = fullMergedImage
		roiMergedImage = fullMergedImage.crop(box)
		roiMergedImage.load()	# make sure this is not just a lazy copy of the full image
		if roiZoom is not 1:
			newSize = (int(roiWidth*roiZoom), int(roiHeight*roiZoom))
			roiMergedImage = roiMergedImage.resize(newSize)
		panelWidth = roiMergedImage.size[0]
		renderedImages.append(roiMergedImage)
		
	if channelMismatch:
		log(" WARNING channel mismatch: The current image has fewer channels than the primary image.")

	# now assemble the roi split-view canvas, with space above for text
	imageCount = len(renderedImages)
	font = imgUtil.getFont(fontsize)
	textHeight = font.getsize("Textq")[1]
	canvasWidth = ((panelWidth + spacer) * imageCount) - spacer	# no spaces around panels
	canvasHeight = renderedImages[0].size[1] + textHeight + spacer
	size = (canvasWidth, canvasHeight)
	canvas = Image.new(mode, size, white)		# create a canvas of appropriate width, height
	
	px = 0
	textY = spacer/2
	panelY = textHeight + spacer
	# paste the images in, with time labels
	draw = ImageDraw.Draw(canvas)
	timeLabels = figUtil.getTimeLabels(queryService, pixelsId, timeIndexes, sizeT, "HOURS_MINS")
	for i, img in enumerate(renderedImages):
		label = timeLabels[i]
		indent = (panelWidth - (font.getsize(label)[0])) / 2
		draw.text((px+indent, textY), label, font=font, fill=(0,0,0))
		imgUtil.pasteImage(img, canvas, px, panelY)
		px = px + panelWidth + spacer
	
	# return the roi splitview canvas, as well as the full merged image
	return (canvas, fullFirstFrame, textHeight + spacer)
	
def getROIsplitView	(session, pixels, zStart, zEnd, splitIndexes, channelNames, colourChannels, mergedIndexes, 
			mergedColours, roiX, roiY, roiWidth, roiHeight, roiZoom, spacer = 12, algorithm = None, stepping = 1, fontsize=24):
	""" This takes a ROI rectangle from an image and makes a split view canvas of the region in the ROI, zoomed 
		by a defined factor. 
	"""
	
	if algorithm is None:	# omero::constants::projection::ProjectionType
		algorithm = omero.constants.projection.ProjectionType.MAXIMUMINTENSITY
	timepoint = 0
	mode = "RGB"
	white = (255, 255, 255)	
	
	# create a rendering engine
	re = session.createRenderingEngine()
	
	sizeX = pixels.getSizeX().getValue()
	sizeY = pixels.getSizeY().getValue()
	sizeZ = pixels.getSizeZ().getValue()
	sizeC = pixels.getSizeC().getValue()
	
	if pixels.getPhysicalSizeX():
		physicalX = pixels.getPhysicalSizeX().getValue()
	else:
		physicalX = 0 
	if pixels.getPhysicalSizeY():
		physicalY = pixels.getPhysicalSizeY().getValue()
	else:
		physicalY = 0
	log("  Pixel size (um): x: %s  y: %s" % (str(physicalX), str(physicalY)))
	log("  Image dimensions (pixels): x: %d  y: %d" % (sizeX, sizeY))
	
	log(" Projecting ROIs...")
	proStart = zStart
	proEnd = zEnd
	# make sure we're within Z range for projection. 
	if proEnd >= sizeZ:
		proEnd = sizeZ - 1
		if proStart > sizeZ:
			proStart = 0
		log(" WARNING: Current image has fewer Z-sections than the primary image projection.")
	if proStart < 0:
		proStart = 0
	log("  Projecting z range: %d - %d   (max Z is %d)" % (proStart+1, proEnd+1, sizeZ))
	# set up rendering engine with the pixels
	pixelsId = pixels.getId().getValue()
	re.lookupPixels(pixelsId)
	re.lookupRenderingDef(pixelsId)
	re.load()
	
	# now get each channel in greyscale (or colour)
	# a list of renderedImages (data as Strings) for the split-view row
	renderedImages = []
	panelWidth = 0
	channelMismatch = False
	# first, turn off all channels in pixels
	for i in range(sizeC): 
		re.setActive(i, False)
		
	# for each channel in the splitview...
	for index in splitIndexes:
		if index >= sizeC:
			channelMismatch = True		# can't turn channel on - simply render black square! 
		else:
			re.setActive(index, True)				# turn channel on
			if colourChannels:							# if split channels are coloured...
				if index in mergedIndexes:			# and this channel is in the combined image
					rgba = tuple(mergedColours[index])
					re.setRGBA(index, *rgba)		# set coloured 
				else:
					re.setRGBA(index,255,255,255,255)	# otherwise set white (max alpha)
			else:
				re.setRGBA(index,255,255,255,255)	# if not colourChannels - channels are white
			info = (channelNames[index], re.getChannelWindowStart(index), re.getChannelWindowEnd(index))
			log("  Render channel: %s  start: %d  end: %d" % info)
		projection = re.renderProjectedCompressed(algorithm, timepoint, stepping, proStart, proEnd)
		fullImage = Image.open(StringIO.StringIO(projection))
		box = (roiX, roiY, roiX+roiWidth, roiY+roiHeight)
		roiImage = fullImage.crop(box)
		roiImage.load()		# hoping that when we zoom, don't zoom fullImage 
		if roiZoom is not 1:
			newSize = (int(roiWidth*roiZoom), int(roiHeight*roiZoom))
			roiImage = roiImage.resize(newSize)
		renderedImages.append(roiImage)
		panelWidth = roiImage.size[0]
		if index < sizeC:
			re.setActive(index, False)				# turn the channel off again!
			
			
	# turn on channels in mergedIndexes. 
	for i in mergedIndexes: 
		if i >= sizeC:
			channelMismatch = True
		else:
			rgba = mergedColours[i]
			re.setActive(i, True)
			re.setRGBA(i, *rgba)
				
	# get the combined image, using the existing rendering settings 
	channelsString = ", ".join([str(i) for i in mergedIndexes])
	log("  Rendering merged channels: %s" % channelsString)
	merged = re.renderProjectedCompressed(algorithm, timepoint, stepping, proStart, proEnd)
	fullMergedImage = Image.open(StringIO.StringIO(merged))
	roiMergedImage = fullMergedImage.crop(box)
	roiMergedImage.load()	# make sure this is not just a lazy copy of the full image
	if roiZoom is not 1:
		newSize = (int(roiWidth*roiZoom), int(roiHeight*roiZoom))
		roiMergedImage = roiMergedImage.resize(newSize)
		
	if channelMismatch:
		log(" WARNING channel mismatch: The current image has fewer channels than the primary image.")
			
	# now assemble the roi split-view canvas
	imageCount = len(renderedImages) + 1 	# extra image for merged image
	font = imgUtil.getFont(fontsize)
	textHeight = font.getsize("Textq")[1]
	canvasWidth = ((panelWidth + spacer) * imageCount) - spacer	# no spaces around panels
	canvasHeight = renderedImages[0].size[1] + textHeight + spacer
	size = (canvasWidth, canvasHeight)
	canvas = Image.new(mode, size, white)		# create a canvas of appropriate width, height
	
	px = 0
	textY = spacer/2
	panelY = textHeight + spacer
	# paste the split images in, with channel labels
	draw = ImageDraw.Draw(canvas)
	for i, index in enumerate(splitIndexes):
		label = channelNames[index]
		indent = (panelWidth - (font.getsize(label)[0])) / 2
		draw.text((px+indent, textY), label, font=font, fill=(0,0,0))
		imgUtil.pasteImage(renderedImages[i], canvas, px, panelY)
		px = px + panelWidth + spacer
	# and the merged image
	indent = (panelWidth - (font.getsize("Merged")[0])) / 2
	draw.text((px+indent, textY), "Merged", font=font, fill=(0,0,0))
	imgUtil.pasteImage(roiMergedImage, canvas, px, panelY)
	
	# return the roi splitview canvas, as well as the full merged image
	return (canvas, fullMergedImage, textHeight + spacer)

def drawRectangle(image, roiX, roiY, roiX2, roiY2, colour, stroke=1):
	roiDraw = ImageDraw.Draw(image)
	for s in range(stroke):
		roiBox = (roiX, roiY, roiX2, roiY2)
		roiDraw.rectangle(roiBox, outline = colour)
		roiX +=1
		roiY +=1
		roiX2 -=1
		roiY2 -=1

def getRectangle(session, imageId):
	""" Returns (x, y, width, height) of the first rectange in the image """
	
	shapes = []		# string set. 
	
	roiService = session.getRoiService()
	result = roiService.findByImage(imageId, None)
	
	rectCount = 0
	for roi in result.rois:
		for shape in roi.copyShapes():
			if type(shape) == omero.model.RectI:
				if rectCount == 0:
					zMin = shape.getTheZ().getValue()
					zMax = zMin
					tMin = shape.getTheT().getValue()
					tMax = tMin
					x = shape.getX().getValue()
					y = shape.getY().getValue()
					width = shape.getWidth().getValue()
					height = shape.getHeight().getValue()
				else:
					zMin = min(zMin, shape.getTheZ().getValue())
					zMax = max(zMax, shape.getTheZ().getValue())
					tMin = min(tMin, shape.getTheT().getValue())
					tMax = max(tMax, shape.getTheT().getValue())
				rectCount += 1
		if rectCount > 0:
			return (int(x), int(y), int(width), int(height), int(zMin), int(zMax), int(tMin), int(tMax))
				
				
def getVerticalLabels(labels, font, textGap):
	""" Returns an image with the labels written vertically with the given font, black on white background """
	
	maxWidth = 0
	height = 0
	textHeight = font.getsize("testq")[1]
	for label in labels:
		maxWidth = max(maxWidth, font.getsize(label)[0])
		if height > 0: height += textGap
		height += textHeight
	size = (maxWidth, height)
	textCanvas = Image.new("RGB", size, WHITE)
	textdraw = ImageDraw.Draw(textCanvas)
	py = 0
	for label in labels:
		indent = (maxWidth - font.getsize(label)[0]) / 2
		textdraw.text((indent, py), label, font=font, fill=(0,0,0))
		py += textHeight + textGap
	return textCanvas.rotate(90)
	
	
def getSplitView(session, imageIds, pixelIds, zStart, zEnd, splitIndexes, channelNames, colourChannels, mergedIndexes, 
		mergedColours, width, height, imageLabels, spacer = 12, algorithm = None, stepping = 1, scalebar = None, 
		overlayColour=(255,255,255), roiZoom=None):
	""" This method makes a figure of a number of images, arranged in rows with each row being the split-view
	of a single image. The channels are arranged left to right, with the combined image added on the right.
	The combined image is rendered according to current settings on the server, but it's channels will be
	turned on/off according to @mergedIndexes. 
	
	The figure is returned as a PIL 'Image' 
	
	@ session	session for server access
	@ pixelIds		a list of the Ids for the pixels we want to display
	@ zStart		the start of Z-range for projection
	@ zEnd 			the end of Z-range for projection
	@ splitIndexes 	a list of the channel indexes to display. Same channels for each image/row
	@ channelNames 		the Map of index:names to go above the columns for each split channel
	@ colourChannels 	the colour to make each column/ channel
	@ mergedIndexes  	list or set of channels in the merged image 
	@ mergedColours 	index: colour dictionary of channels in the merged image
	@ width			the size in pixels to show each panel
	@ height		the size in pixels to show each panel
	@ spacer		the gap between images and around the figure. Doubled between rows. 
	"""
	
	gateway = session.createGateway()
	
	# establish dimensions and roiZoom for the primary image
	# getTheseValues from the server
	roiX, roiY, roiWidth, roiHeight, yMin, yMax, tMin, tMax = getRectangle(session, imageIds[0])
	
	roiOutline = ((max(width, height)) / 200 ) + 1
	
	if roiZoom == None:
		# get the pixels for priamry image. 
		pixels = gateway.getPixels(pixelIds[0])
		sizeY = pixels.getSizeY().getValue()
	
		roiZoom = float(height) / float(roiHeight)
		log("ROI zoom set by primary image is %F X" % roiZoom)
	else:
		log("ROI zoom: %F X" % roiZoom)
	
	textGap = spacer/3
	fontsize = max(12, width/10)
	font = imgUtil.getFont(fontsize)
	textHeight = font.getsize("Textq")[1]
	maxCount = 0
	for row in imageLabels:
		maxCount = max(maxCount, len(row))
	leftTextWidth = (textHeight + textGap) * maxCount + spacer
	
	projectRoiPlanes = (zEnd < 0)
	maxSplitPanelWidth = 0
	totalcanvasHeight = 0
	mergedImages = []
	roiSplitPanes = []
	
	for row, pixelsId in enumerate(pixelIds):
		log("Rendering row %d" % (row))
		
		# need to get the roi dimensions from the server
		imageId = imageIds[row]
		roi = getRectangle(session, imageId)
		if roi == None:
			log("No Rectangle ROI found for this image")
			del imageLabels[row]	# remove the corresponding labels
			continue
		roiX, roiY, roiWidth, roiHeight, zMin, zMax, tStart, tEnd = roi
		
		pixels = gateway.getPixels(pixelsId)
		sizeX = pixels.getSizeX().getValue()
		sizeY = pixels.getSizeY().getValue()
		
		if projectRoiPlanes:
			zStart = zMin
			zEnd = zMax
		
		# work out if any additional zoom is needed (if the full-sized image is different size from primary image)
		fullSize =  (sizeX, sizeY)
		imageZoom = imgUtil.getZoomFactor(fullSize, width, height)
		if imageZoom != 1.0:
			log("  Scaling down the full-size image by a factor of %F" % imageZoom)
		
		log("  ROI location (top-left) x: %d  y: %d  and size width: %d  height: %d" % (roiX, roiY, roiWidth, roiHeight))
		log("  ROI time %d - %d" % (tStart, tEnd))
		# get the split pane and full merged image
		if tStart == tEnd:
			roiSplitPane, fullMergedImage, topSpacer = getROIsplitView	(session, pixels, zStart, zEnd, splitIndexes, channelNames, 
				colourChannels, mergedIndexes, mergedColours, roiX, roiY, roiWidth, roiHeight, roiZoom, spacer, algorithm, stepping, fontsize)
		else:
			tStep = 1
			roiSplitPane, fullMergedImage, topSpacer = getROImovieView	(session, pixels, zStart, zEnd, tStart, tEnd, splitIndexes, channelNames, 
				colourChannels, mergedIndexes, mergedColours, roiX, roiY, roiWidth, roiHeight, roiZoom, tStep, spacer, algorithm, stepping, fontsize)
			
		
		# and now zoom the full-sized merged image, add scalebar 
		mergedImage = imgUtil.resizeImage(fullMergedImage, width, height)
		if scalebar:
			xIndent = spacer
			yIndent = xIndent
			sbar = float(scalebar) / imageZoom			# and the scale bar will be half size
			if not addScalebar(sbar, xIndent, yIndent, mergedImage, pixels, overlayColour):
				log("  Failed to add scale bar: Pixel size not defined or scale bar is too large.")
				
		# draw ROI onto mergedImage...
		# recalculate roi if the image has been zoomed
		x = roiX / imageZoom
		y = roiY / imageZoom
		roiX2 = (roiX + roiWidth) / imageZoom
		roiY2 = (roiY + roiHeight) / imageZoom
		drawRectangle(mergedImage, x, y, roiX2, roiY2, overlayColour, roiOutline)
		
		# note the maxWidth of zoomed panels and total height for row
		maxSplitPanelWidth = max(maxSplitPanelWidth, roiSplitPane.size[0])
		totalcanvasHeight += spacer + max(height+topSpacer, roiSplitPane.size[1])
		
		mergedImages.append(mergedImage)
		roiSplitPanes.append(roiSplitPane)
	
		
	# make a figure to combine all split-view rows
	# each row has 1/2 spacer above and below the panels. Need extra 1/2 spacer top and bottom
	canvasWidth = leftTextWidth + width + spacer + maxSplitPanelWidth + spacer	# 
	figureSize = (canvasWidth, totalcanvasHeight + spacer)
	figureCanvas = Image.new("RGB", figureSize, (255,255,255))
	
	rowY = spacer
	for row, image in enumerate(mergedImages):
		labelCanvas = getVerticalLabels(imageLabels[row], font, textGap)
		vOffset = (image.size[1] - labelCanvas.size[1]) / 2
		imgUtil.pasteImage(labelCanvas, figureCanvas, spacer/2, rowY+topSpacer+ vOffset)
		imgUtil.pasteImage(image, figureCanvas, leftTextWidth, rowY+topSpacer)
		x = leftTextWidth + width + spacer
		imgUtil.pasteImage(roiSplitPanes[row], figureCanvas, x, rowY)
		rowY = rowY + max(image.size[1]+topSpacer, roiSplitPanes[row].size[1])+ spacer

	return figureCanvas
			

def roiFigure(session, commandArgs):	
	
	# create the services we're going to need. 
	metadataService = session.getMetadataService()
	queryService = session.getQueryService()
	updateService = session.getUpdateService()
	rawFileStore = session.createRawFileStore()
	
	log("ROI figure created by OMERO on %s" % date.today())
	log("")
	
	pixelIds = []
	imageIds = []
	imageLabels = []
	imageNames = {}
	gateway = session.createGateway()
	omeroImage = None	# this is set as the first image, to link figure to

	# function for getting image labels.
	def getLabels(fullName, tagsList, pdList):
		name = fullName.split("/")[-1]
		return [name]
		
	# default function for getting labels is getName (or use datasets / tags)
	if "imageLabels" in commandArgs:
		if commandArgs["imageLabels"] == "DATASETS":
			def getDatasets(name, tagsList, pdList):
				return [dataset for project, dataset in pdList]
			getLabels = getDatasets
		elif commandArgs["imageLabels"] == "TAGS":
			def getTags(name, tagsList, pdList):
				return tagsList
			getLabels = getTags
			
	# process the list of images. If imageIds is not set, script can't run. 
	log("Image details:")
	if "imageIds" in commandArgs:
		for idCount, imageId in enumerate(commandArgs["imageIds"]):
			iId = long(imageId.getValue())
			imageIds.append(iId)
			image = gateway.getImage(iId)
			if idCount == 0:
				omeroImage = image		# remember the first image to attach figure to
			pixelIds.append(image.getPrimaryPixels().getId().getValue())
			imageNames[iId] = image.getName().getValue()
		
			
	pdMap = figUtil.getDatasetsProjectsFromImages(queryService, imageIds)	# a map of imageId : list of (project, dataset) names. 
	tagMap = figUtil.getTagsFromImages(metadataService, imageIds)
	# Build a legend entry for each image
	for iId in imageIds:
		name = imageNames[iId]
		imageDate = image.getAcquisitionDate().getValue()
		tagsList = tagMap[iId]
		pdList = pdMap[iId]
		
		tags = ", ".join(tagsList)
		pdString = ", ".join(["%s/%s" % pd for pd in pdList])
		log(" Image: %s  ID: %d" % (name, iId))
		log("  Date: %s" % date.fromtimestamp(imageDate/1000))
		log("  Tags: %s" % tags)
		log("  Project/Datasets: %s" % pdString)
		
		imageLabels.append(getLabels(name, tagsList, pdList))
	
	# use the first image to define dimensions, channel colours etc. 
	pixelsId = pixelIds[0]
	pixels = gateway.getPixels(pixelsId)

	sizeX = pixels.getSizeX().getValue();
	sizeY = pixels.getSizeY().getValue();
	sizeZ = pixels.getSizeZ().getValue();
	sizeC = pixels.getSizeC().getValue();
		
	
	# set image dimensions
	if("zStart" not in commandArgs):
		commandArgs["zStart"] = 0
	if("zEnd" not in commandArgs):
		commandArgs["zEnd"] = sizeZ-1
	if("splitPanelsGrey" not in commandArgs):
		commandArgs["splitPanelsGrey"] = False
	
	zStart = int(commandArgs["zStart"])
	zEnd = int(commandArgs["zEnd"])
	
	width = sizeX
	if "width" in commandArgs:
		w = commandArgs["width"]
		try:
			width = int(w)
		except:
			log("Invalid width: %s Using default value: %d" % (str(w), sizeX))
	
	height = sizeY
	if "height" in commandArgs:
		h = commandArgs["height"]
		try:
			height = int(h)
		except:
			log("Invalid height: %s Using default value" % (str(h), sizeY))
			
	log("Image dimensions for all panels (pixels): width: %d  height: %d" % (width, height))
		
						
	mergedIndexes = []	# the channels in the combined image, 
	mergedColours = {}	
	if "mergedColours" in commandArgs:
		cColourMap = commandArgs["mergedColours"]
		for c in cColourMap:
			rgb = cColourMap[c].getValue()
			rgba = imgUtil.RGBIntToRGBA(rgb)
			mergedColours[int(c)] = rgba
			mergedIndexes.append(int(c))
	else:
		mergedIndexes = range(sizeC)[1:]
		for c in mergedIndexes:	# make up some colours 
			if c%3 == 0:
				mergedColours[c] = (0,0,255,255)	# blue
			if c%3 == 1:
				mergedColours[c] = (0,255,0,255)	# green
			if c%3 == 2:
				mergedColours[c] = (255,0,0,255)	# red
	
	# Make channel list. 
	splitIndexes = []
	channelNames = {}
	if "splitChannelNames" in commandArgs:
		cNameMap = commandArgs["splitChannelNames"]
		for c in cNameMap:
			index = int(c)
			channelNames[index] = cNameMap[c].getValue()
			splitIndexes.append(index)
		splitIndexes.sort()
	else:	# If argument wasn't specified, include them all. 
		for c in range(sizeC):
			channelNames[c] = str(c)
		splitIndexes = range(sizeC)
		
	colourChannels = True
	if commandArgs["splitPanelsGrey"]:
		colourChannels = False
	
	algorithm = omero.constants.projection.ProjectionType.MAXIMUMINTENSITY
	if "algorithm" in commandArgs:
		a = commandArgs["algorithm"]
		if (a == "MEANINTENSITY"):
			algorithm = omero.constants.projection.ProjectionType.MEANINTENSITY
	
	stepping = 1
	if "stepping" in commandArgs:
		s = commandArgs["stepping"]
		if (0 < s < sizeZ):
			stepping = s
	
	scalebar = None
	if "scalebar" in commandArgs:
		sb = commandArgs["scalebar"]
		try:
			scalebar = int(sb)
			if scalebar <= 0:
				scalebar = None
			else:
				log("Scalebar is %d microns" % scalebar)
		except:
			log("Invalid value for scalebar: %s" % str(sb))
			scalebar = None
	
	overlayColour = (255,255,255)
	if "overlayColour" in commandArgs:
		overlayColour = imgUtil.RGBIntToRGB(commandArgs["overlayColour"])
	
	roiZoom = None
	if "roiZoom" in commandArgs:
		roiZoom = float(commandArgs["roiZoom"])
		if roiZoom == 0:
			roiZoom = None
			
	spacer = (width/50) + 2
	
	fig = getSplitView(session, imageIds, pixelIds, zStart, zEnd, splitIndexes, channelNames, colourChannels, 
			mergedIndexes, mergedColours, width, height, imageLabels, spacer, algorithm, stepping, scalebar, overlayColour, roiZoom)
													
	#fig.show()		# bug-fixing only
	
	log("")
	figLegend = "\n".join(logStrings)
	
	#print figLegend	# bug fixing only
	
	format = JPEG
	if "format" in commandArgs:
		if commandArgs["format"] == PNG:
			format = PNG
			
	output = "roiFigure"
	if "figureName" in commandArgs:
		output = str(commandArgs["figureName"])
		
	if format == PNG:
		output = output + ".png"
		fig.save(output, "PNG")
	else:
		output = output + ".jpg"
		fig.save(output)
	

	fileId = scriptUtil.uploadAndAttachFile(queryService, updateService, rawFileStore, omeroImage, output, format, figLegend)
	return fileId

def runAsScript():
	# splitViewROIFigure.py
	client = scripts.client('roiFigure.py', 'Create a figure of split-view images.', 
	scripts.List("imageIds").inout(),		# List of image IDs. Resulting figure will be attached to first image 
	scripts.Long("zStart").inout(),			# projection range
	scripts.Long("zEnd").inout(),			# projection range
	scripts.Map("splitChannelNames").inout(),	# map of index: channel name for Split channels
	scripts.Bool("splitPanelsGrey").inout(),# if true, all split panels are greyscale
	scripts.Map("mergedColours").inout(),	# a map of index:int colours for each merged channel
	scripts.Long("width", optional=True).inout(),		# the max width of each image panel 
	scripts.Long("height", optional=True).inout(),		# the max height of each image panel
	scripts.String("imageLabels").inout(),	# label with IMAGENAME or DATASETS or TAGS
	scripts.String("algorithm", optional=True).inout(),	# algorithum for projection. MAXIMUMINTENSITY or MEANINTENSITY
	scripts.Long("stepping", optional=True).inout(),	# the plane increment from projection (default = 1)
	scripts.Long("scalebar", optional=True).inout(),	# scale bar (same as makemovie script)
	scripts.String("format").inout(),		# format to save image. Currently JPEG or PNG
	scripts.String("figureName").inout(),	# name of the file to save.
	scripts.Long("overlayColour", optional=True).inout(),	# the colour of the scalebar 
	scripts.Long("roiZoom", optional=True).inout(),		# how much to zoom the ROI. If <= 0 then zoom is chosen to fit 
	scripts.Long("fileAnnotation").out());  # script returns a file annotation
	
	session = client.getSession();
	gateway = session.createGateway();
	commandArgs = {"imageIds":client.getInput("imageIds").getValue()}
	
	for key in client.getInputKeys():
		if client.getInput(key):
			commandArgs[key] = client.getInput(key).getValue()
	
	fileId = roiFigure(session, commandArgs)
	client.setOutput("fileAnnotation",fileId)
	
if __name__ == "__main__":
	runAsScript()
