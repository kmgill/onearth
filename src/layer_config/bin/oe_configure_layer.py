#!/bin/env python

# Copyright (c) 2002-2015, California Institute of Technology.
# All rights reserved.  Based on Government Sponsored Research under contracts NAS7-1407 and/or NAS7-03001.
# 
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#   1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#   2. Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#   3. Neither the name of the California Institute of Technology (Caltech), its operating division the Jet Propulsion Laboratory (JPL),
#      the National Aeronautics and Space Administration (NASA), nor the names of its contributors may be used to
#      endorse or promote products derived from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE CALIFORNIA INSTITUTE OF TECHNOLOGY BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#
# oe_configure_layer.py
# The OnEarth Layer Configurator.
#
#
# Example XML configuration file:
#
'''
<?xml version="1.0" encoding="UTF-8"?>
<LayerConfiguration>
 <Identifier>MODIS_Aqua_Cloud_Top_Temp_Night</Identifier>
 <Title>MODIS AQUA Nighttime Cloud Top Temperature</Title>
 <FileNamePrefix>MYR6CTTLLNI</FileNamePrefix>
 <TiledGroupName>MODIS AQUA Nighttime Cloud Top Temperature tileset</TiledGroupName>
 <Compression>PNG</Compression>
 <TileMatrixSet>EPSG4326_2km</TileMatrixSet>
 <EmptyTileSize offset="0">1397</EmptyTileSize>
 <Projection>EPSG:4326</Projection> 
 <EnvironmentConfig>/layer_config/conf/environment_geographic.xml</EnvironmentConfig>
 <ArchiveLocation static="false" year="true">/data/EPSG4326/MYR6CTTLLNI</ArchiveLocation>
 <ColorMap>http://localhost/colormap/sample.xml</ColorMap>
 <Time>DETECT</Time>
 <Time>2014-04-01/DETECT/P1D</Time>
</LayerConfiguration>
'''
#
# Global Imagery Browse Services
# NASA Jet Propulsion Laboratory
# 2015

import os
import subprocess
import sys
import socket
import urllib
import urllib2
import xml.dom.minidom
import logging
import shutil
import re
import distutils.spawn
from datetime import datetime, time, timedelta
from time import asctime
from dateutil.relativedelta import relativedelta
from optparse import OptionParser
from lxml import etree
from shutil import copyfile

versionNumber = '0.7.0'

class WMTSEndPoint:
    """End point data for WMTS"""
    
    def __init__(self, path, cacheConfigLocation, cacheConfigBasename, getCapabilities, projection):
        self.path = path
        self.cacheConfigLocation = cacheConfigLocation
        self.cacheConfigBasename = cacheConfigBasename
        self.getCapabilities = getCapabilities
        self.projection = projection
        
class TWMSEndPoint:
    """End point data for TWMS"""
    
    def __init__(self, path, cacheConfigLocation, cacheConfigBasename, getCapabilities, getTileService, projection):
        self.path = path
        self.cacheConfigLocation = cacheConfigLocation
        self.cacheConfigBasename = cacheConfigBasename
        self.getCapabilities = getCapabilities
        self.getTileService = getTileService
        self.projection = projection

class Environment:
    """Environment information for layer(s)"""
    
    def __init__(self, cacheLocation_wmts, cacheLocation_twms, cacheBasename_wmts, cacheBasename_twms, getCapabilities_wmts, getCapabilities_twms, getTileService, wmtsServiceUrl, twmsServiceUrl, 
        projection_wmts_dir, projection_twms_dir, legend_dir, legendUrl, colormap_dir, colormapUrl, mapfileConfigLocation, mapfileConfigBasename, mapfile):
        self.cacheLocation_wmts = cacheLocation_wmts
        self.cacheLocation_twms = cacheLocation_twms
        self.cacheBasename_wmts = cacheBasename_wmts
        self.cacheBasename_twms = cacheBasename_twms
        self.getCapabilities_wmts = getCapabilities_wmts
        self.getCapabilities_twms = getCapabilities_twms
        self.getTileService = getTileService
        self.wmtsServiceUrl = wmtsServiceUrl
        self.twmsServiceUrl = twmsServiceUrl
        self.wmts_dir = projection_wmts_dir
        self.twms_dir = projection_twms_dir
        self.legend_dir = legend_dir
        self.legendUrl = legendUrl
        self.colormap_dir = colormap_dir
        self.colormapUrl = colormapUrl
        self.mapfileConfigLocation = mapfileConfigLocation
        self.mapfileConfigBasename = mapfileConfigBasename
        self.mapfile = mapfile
        
class Projection:
    """Projection information for layer"""
    
    def __init__(self, projection_id, projection_wkt, projection_bbox, projection_tilematrixsets, projection_tilematrixset_xml, projection_lowercorner, projection_uppercorner):
        self.id = projection_id
        self.wkt = projection_wkt
        self.bbox_xml = projection_bbox
        self.tilematrixsets = projection_tilematrixsets #returns TileMatrixSetMeta
        self.tilematrixset_xml = projection_tilematrixset_xml
        self.lowercorner = projection_lowercorner
        self.uppercorner = projection_uppercorner
        
class TileMatrixSetMeta:
    """TileMatrixSet metadata for WMTS"""
     
    def __init__(self, levels, scale):
        self.levels = levels
        self.scale = scale

warnings = []
errors = []

def sigevent(type, mssg, sigevent_url):
    """
    Send a message to sigevent service.
    Arguments:
        type -- 'INFO', 'WARN', 'ERROR'
        mssg -- 'message for operations'
        sigevent_url -- Example:  'http://[host]/sigevent/events/create'
                        'http://localhost:8100/sigevent/events/create'
    """
    # Constrain mssg to 256 characters (including '...').
    if len(mssg) > 256:
        mssg=str().join([mssg[0:253], '...'])
    print str().join(['sigevent ', type, ' - ', mssg])
    # Remove any trailing slash from URL.
    if sigevent_url[-1] == '/':
        sigevent_url=sigevent_url[0:len(sigevent_url)-1]
    # Remove any question mark from URL.  It is added later.
    if sigevent_url[-1] == '?':
        sigevent_url=sigevent_url[0:len(sigevent_url)-1]
    # Remove any trailing slash from URL.  (Again.)
    if sigevent_url[-1] == '/':
        sigevent_url=sigevent_url[0:len(sigevent_url)-1]
    # Define sigevent parameters that get encoded into the URL.
    data={}
    data['type']=type
    data['description']=mssg
    data['computer']=socket.gethostname()
    data['source']='ONEARTH'
    data['format']='TEXT'
    data['category']='ONEARTH'
    data['provider']='GIBS'
    # Format sigevent parameters that get encoded into the URL.
    values=urllib.urlencode(data)
    # Create complete URL.
    full_url=sigevent_url+'?'+values
    data=urllib2.urlopen(full_url)

def log_info_mssg(mssg):
    """
    For information messages only.  Not for warning or error.
    Arguments:
        mssg -- 'message for operations'
    """
    # Send to log.
    print mssg
    logging.info(mssg)

def log_info_mssg_with_timestamp(mssg):
    """
    For information messages only.  Not for warning or error.
    Arguments:
        mssg -- 'message for operations'
    """
    # Send to log.
    print asctime()
    logging.info(asctime())
    log_info_mssg(mssg)

def log_sig_warn(mssg, sigevent_url):
    """
    Send a warning to the log and to sigevent.
    Arguments:
        mssg -- 'message for operations'
        sigevent_url -- Example:  'http://[host]/sigevent/events/create'
    """
    # Send to log.
    logging.warning(asctime() + " " + mssg)
    global warnings
    warnings.append(asctime() + " " + mssg)
    # Send to sigevent.
    try:
        sigevent('WARN', mssg, sigevent_url)
    except urllib2.URLError:
        print 'sigevent service is unavailable'
        
def log_sig_err(mssg, sigevent_url):
    """
    Send a warning to the log and to sigevent.
    Arguments:
        mssg -- 'message for operations'
        sigevent_url -- Example:  'http://[host]/sigevent/events/create'
    """
    # Send to log.
    logging.error(asctime() + " " + mssg)
    global errors
    errors.append(asctime() + " " + mssg)
    # Send to sigevent.
    try:
        sigevent('ERROR', mssg, sigevent_url)
    except urllib2.URLError:
        print 'sigevent service is unavailable'

def log_sig_exit(type, mssg, sigevent_url):
    """
    Send a message to the log, to sigevent, and then exit.
    Arguments:
        type -- 'INFO', 'WARN', 'ERROR'
        mssg -- 'message for operations'
        sigevent_url -- Example:  'http://[host]/sigevent/events/create'
    """
    # Add "Exiting" to mssg.
    mssg=str().join([mssg, '  Exiting oe_configure_layer.'])
    # Send to sigevent.
    try:
        sigevent(type, mssg, sigevent_url)
    except urllib2.URLError:
        print 'sigevent service is unavailable'
    # Send to log.
    if type == 'INFO':
        log_info_mssg_with_timestamp(mssg)
    elif type == 'WARN':
        logging.warning(asctime())
        logging.warning(mssg)
    elif type == 'ERROR':
        logging.error(asctime())
        logging.error(mssg)
    # Exit.
    sys.exit()

def log_the_command(command_list):
    """
    Send a command list to the log.
    Arguments:
        command_list -- list containing all elements of a subprocess command.
    """
    # Add a blank space between each element.
    spaced_command=''
    for ndx in range(len(command_list)):
        spaced_command=str().join([spaced_command, command_list[ndx], ' '])
    # Send to log.
    log_info_mssg_with_timestamp(spaced_command)

def get_dom_tag_value(dom, tag_name):
    """
    Return value of a tag from dom (XML file).
    Arguments:
        tag_name -- name of dom tag for which the value should be returned.
    """
    tag = dom.getElementsByTagName(tag_name)
    value = tag[0].firstChild.nodeValue.strip()
    return value

def change_dom_tag_value(dom, tag_name, value):
    """
    Return value of a tag from dom (XML file).
    Arguments:
        tag_name -- name of dom tag for which the value should be returned.
        value -- the replacement value.
    """
    tag = dom.getElementsByTagName(tag_name)
    tag[0].firstChild.nodeValue = value
    
def run_command(cmd, sigevent_url):
    """
    Runs the provided command on the terminal.
    Arguments:
        cmd -- the command to be executed.
    """
    print '\nRunning command: ' + cmd
    process = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    process.wait()
    for output in process.stdout:
        print output.strip()
    for error in process.stderr:
        log_sig_err(error.strip(), sigevent_url)
        raise Exception(error.strip())
    
def add_trailing_slash(directory_path):
    """
    Add trailing slash if one is not already present.
    Argument:
        directory_path -- path to which trailing slash should be confirmed.
    """
    # Add trailing slash.
    if directory_path[-1] != '/':
        directory_path=str().join([directory_path, '/'])
    # Return directory_path with trailing slash.
    return directory_path

def get_pretty_xml(xml_dom):
    """
    Formats an XML document into a string with nice-looking line-breaks (for get_mrf).
    """
    parser = etree.XMLParser(strip_cdata=False)
    xml = etree.fromstring(xml_dom.toxml(), parser)
    pretty_xml = etree.tostring(xml, pretty_print=True)
    return pretty_xml

def delete_mapfile_layer(mapfile, layerName):
    """
    Deletes a LAYER entry from a Mapfile.
    """
    mapfile.seek(0)
    endTagCount = None
    bytePosition = 0
    layerFound = False
    for line in mapfile.readlines():
        # Record byte position of LAYER tag in case we're about to find that it's a dupe
        if 'layer' in line.lower():
            layerStart = bytePosition
        # If this is a duplicate tag, start counting END tags
        if all(tag in line.lower() for tag in ('name',identifier)):
            endTagCount = 1
        # Increment the END count if additional tags that require an END appear
        if endTagCount > 0 and any(keyword in line.lower() for keyword in ('validation','projection','metadata')):
            endTagCount += 1
        # Decrement the END count each time an END tag is found
        if endTagCount > 0 and "end" in line.lower():
            endTagCount -= 1
        # Increment the overall file position
        bytePosition += len(line)
        # When last END tag is found, record the position of the final line and push LAYER start and end positions to list
        if endTagCount == 0:
            mapfile.seek(bytePosition)
            remainder = mapfile.read()
            mapfile.seek(layerStart)
            mapfile.truncate()
            mapfile.write(remainder)
            layerFound = True
            break
    return layerFound

def get_environment(environmentConfig):
    """
    Gets environment metadata from a environment configuration file.
    Arguments:
        environmentConfig -- the location of the projection configuration file
    """
    try:
        # Open file.
        environment_config=open(environmentConfig, 'r')
        print ('\nUsing environment config: ' + environmentConfig + '\n')
    except IOError:
        mssg=str().join(['Cannot read environment configuration file:  ', environmentConfig])
        raise Exception(mssg)
        
    dom = xml.dom.minidom.parse(environment_config)
    
    # Caches
    try:
        cacheLocationElements = dom.getElementsByTagName('CacheLocation')
        cacheLocation_wmts = None
        cacheLocation_twms = None
        cacheBasename_wmts = None
        cacheBasename_twms = None
        for cacheLocation in cacheLocationElements:
            try:
                if str(cacheLocation.attributes['service'].value).lower() == "wmts":
                    cacheLocation_wmts = cacheLocation.firstChild.nodeValue.strip()
                    cacheBasename_wmts = cacheLocation.attributes['basename'].value
                elif str(cacheLocation.attributes['service'].value).lower() == "twms":
                    cacheLocation_twms = cacheLocation.firstChild.nodeValue.strip()
                    cacheBasename_twms = cacheLocation.attributes['basename'].value
            except KeyError:
                # Set to defaults
                cacheLocation_wmts = cacheLocation.firstChild.nodeValue.strip()
                cacheBasename_wmts = "cache_all_wmts" 
                cacheLocation_twms = cacheLocation.firstChild.nodeValue.strip()
                cacheBasename_twms = "cache_all_twms"                
                log_sig_warn("'service' or 'basename' not defined in <CacheLocation>"+cacheLocation_wmts+"</CacheLocation> Using defaults TWMS:'cache_all_twms', WMTS:'cache_all_wmts'", sigevent_url)    
    except IndexError:
        raise Exception('Required <CacheLocation> element is missing in ' + environmentConfig)
        
    # Services
    try:
        getTileService = get_dom_tag_value(dom, 'GetTileServiceLocation')
    except IndexError:
        getTileService = None
    
    getCapabilitiesElements = dom.getElementsByTagName('GetCapabilitiesLocation')
    wmts_getCapabilities = None
    twms_getCapabilities = None
    for getCapabilities in getCapabilitiesElements:
        try:
            if str(getCapabilities.attributes['service'].value).lower() == "wmts":
                wmts_getCapabilities = getCapabilities.firstChild.nodeValue.strip()
            elif str(getCapabilities.attributes['service'].value).lower() == "twms":
                twms_getCapabilities = getCapabilities.firstChild.nodeValue.strip()
        except KeyError:
            raise Exception('service is not defined in <GetCapabilitiesLocation>')
            
    serviceUrlElements = dom.getElementsByTagName('ServiceURL')
    wmtsServiceUrl = None
    twmsServiceUrl = None
    for serviceUrl in serviceUrlElements:
        try:
            if str(serviceUrl.attributes['service'].value).lower() == "wmts":
                wmtsServiceUrl = serviceUrl.firstChild.nodeValue.strip()
            elif str(serviceUrl.attributes['service'].value).lower() == "twms":
                twmsServiceUrl = serviceUrl.firstChild.nodeValue.strip()
        except KeyError:
            raise Exception('service is not defined in <ServiceURL>')      
 
    stagingLocationElements = dom.getElementsByTagName('StagingLocation')
    wmtsStagingLocation = None
    twmsStagingLocation = None
    for stagingLocation in stagingLocationElements:
        try:
            if str(stagingLocation.attributes['service'].value).lower() == "wmts":
                wmtsStagingLocation = stagingLocation.firstChild.nodeValue.strip()
            elif str(stagingLocation.attributes['service'].value).lower() == "twms":
                twmsStagingLocation = stagingLocation.firstChild.nodeValue.strip()
        except KeyError:
            raise Exception('service is not defined in <StagingLocation>') 
    
    if twmsStagingLocation != None:
        add_trailing_slash(twmsStagingLocation)
        if not os.path.exists(twmsStagingLocation):
            os.makedirs(twmsStagingLocation)
    if wmtsStagingLocation != None:
        add_trailing_slash(wmtsStagingLocation)
        if not os.path.exists(wmtsStagingLocation):
            os.makedirs(wmtsStagingLocation) 
    try:
        legendLocation = add_trailing_slash(get_dom_tag_value(dom, 'LegendLocation'))
    except IndexError:
        legendLocation = None
    try:
        legendUrl = add_trailing_slash(get_dom_tag_value(dom, 'LegendURL'))
    except IndexError:
        legendUrl = None
        
    try:
        colormapLocation = add_trailing_slash(get_dom_tag_value(dom, 'ColorMapLocation'))
    except IndexError:
        colormapLocation = None
    try:
        colormapUrl = add_trailing_slash(get_dom_tag_value(dom, 'ColorMapURL'))
    except IndexError:
        colormapUrl = None

    if create_mapfile == True:
        try:
            mapfileConfigLocation = get_dom_tag_value(dom,'MapfileConfigLocation')
        except IndexError:
            mapfileConfigLocation = '/etc/onearth/config/mapserver/'
            log_sig_warn('Mapfile configuration is missing in <MapfileConfigLocation>. Using /etc/onearth/config/mapserver/', sigevent_url)
        try:
            mapfileConfigBasename = dom.getElementsByTagName('MapfileConfigLocation')[0].attributes['basename'].value
        except KeyError:
            mapfileConfigBasename = None
            log_sig_warn('No Mapfile configuration basename specified. Using EPSGXXXX.xxx format.', sigevent_url)
        try:
            mapfile = get_dom_tag_value(dom,'Mapfile')
        except IndexError:
            mapfile = None
            raise Exception('Required <Mapfile> element is missing in: ' + environmentConfig)
    else:
        mapfileConfigLocation = None
        mapfileConfigBasename = None
        mapfile = None
        
    return Environment(add_trailing_slash(cacheLocation_wmts),
                       add_trailing_slash(cacheLocation_twms),
                       cacheBasename_wmts, cacheBasename_twms,
                       add_trailing_slash(wmts_getCapabilities), 
                       add_trailing_slash(twms_getCapabilities), 
                       add_trailing_slash(getTileService),
                       add_trailing_slash(wmtsServiceUrl), 
                       add_trailing_slash(twmsServiceUrl),
                       wmtsStagingLocation, twmsStagingLocation,
                       legendLocation, legendUrl,
                       colormapLocation, colormapUrl,
                       mapfileConfigLocation, mapfileConfigBasename, mapfile
                       )

def get_archive(archive_root, archive_configuration):
    """
    Gets archive location from an archive configuration file based on the archive root ID.
    Arguments:
        archive_root -- the key used for the archive
        archive_configuration -- the location of the archive configuration file
    """
    try:
        # Open file.
        archive_config=open(archive_configuration, 'r')
        print ('Using archive config: ' + archive_configuration)
    except IOError:
        mssg=str().join(['Cannot read archive configuration file:  ', archive_configuration])
        log_sig_exit('ERROR', mssg, sigevent_url)
    
    location = ""
    dom = xml.dom.minidom.parse(archive_config)
    archiveElements = dom.getElementsByTagName('Archive')
    for archiveElement in archiveElements:
        if str(archiveElement.attributes['id'].value).lower() == archive_root.lower():
                location = archiveElement.getElementsByTagName('Location')[0].firstChild.data.strip()
                print "Archive location: " + location + " \n"
    if location == "":
        log_sig_err('Archive "' + archive_root + '" not found in ' + archive_configuration, sigevent_url)
    return location
    
def get_projection(projectionId, projectionConfig, lcdir, tilematrixset_configuration):
    """
    Gets projection metadata from a projection configuration file based on the projection ID.
    Arguments:
        projectionId -- the name of the projection and key used
        projectionConfig -- the location of the projection configuration file
    """
    try:
        # Open file.
        projection_config=open(projectionConfig, 'r')
        print ('Using projection config: ' + projectionConfig + '\n')
    except IOError:
        mssg=str().join(['Cannot read projection configuration file:  ', projectionConfig])
        log_sig_exit('ERROR', mssg, sigevent_url)
        
    dom = xml.dom.minidom.parse(projection_config)
    projection = None
    projectionTags = dom.getElementsByTagName('Projection')
    for projectionElement in projectionTags:
        if projectionElement.attributes['id'].value == projectionId:
            wkt = projectionElement.getElementsByTagName('WKT')[0].firstChild.data.strip()
            try:
                wgsbbox = projectionElement.getElementsByTagName('WGS84BoundingBox')[0].toxml().replace("WGS84BoundingBox", "ows:WGS84BoundingBox")
            except:
                wgsbbox = ""
            try:
                boundbox = "\n         " + projectionElement.getElementsByTagName('BoundingBox')[0].toxml().replace("BoundingBox", "ows:BoundingBox")
            except:
                boundbox = ""
            bbox = str(wgsbbox + boundbox).replace("LowerCorner","ows:LowerCorner").replace("UpperCorner","ows:UpperCorner")
            # get corners...a bit messy
            lowercorner = xml.dom.minidom.parseString("<bbox>"+str(boundbox+wgsbbox).replace("ows:", "")+"</bbox>").getElementsByTagName('LowerCorner')[0].firstChild.nodeValue.split(" ")
            uppercorner = xml.dom.minidom.parseString("<bbox>"+str(boundbox+wgsbbox).replace("ows:", "")+"</bbox>").getElementsByTagName('UpperCorner')[0].firstChild.nodeValue.split(" ")
            tilematrixsets = {}
            try:
                # Open file.
                tilematrixsetconfig=open(tilematrixset_configuration, 'r')
                print ('Using TileMatrixSet config: ' + tilematrixset_configuration + '\n')
            except IOError:
                mssg=str().join(['Cannot read TileMatrixSet configuration file:  ', tilematrixset_configuration])
                log_sig_exit('ERROR', mssg, sigevent_url)
            tms_dom = xml.dom.minidom.parse(tilematrixsetconfig)
            tms_projections = tms_dom.getElementsByTagName('Projection')
            tms_xml = ""
            for tms_projection in tms_projections:
                try:
                    if tms_projection.attributes['id'].value == projectionId:
                        tms_xml = '\n'.join(tms_projection.toxml().split('\n')[1:-1]) # remove <Projection> lines
                        tms_xml = re.sub(r'<TileMatrixSet level="\d+">', '<TileMatrixSet>', tms_xml) # remove added level metadata
                        tileMatrixSetElements = tms_projection.getElementsByTagName('TileMatrixSet')
                        for tilematrixset in tileMatrixSetElements:
                            scale_denominators = tilematrixset.getElementsByTagName("ScaleDenominator")
                            if scale_denominators.length > 1:
                                scale = int(round(float(scale_denominators[0].firstChild.nodeValue.strip())/float(scale_denominators[1].firstChild.nodeValue.strip())))
                            else:
                                scale = 2 # default to powers of 2 scale
                            print "TileMatrixSet: " + tilematrixset.getElementsByTagName('ows:Identifier')[0].firstChild.nodeValue.strip() + " - levels: " + str(tilematrixset.getElementsByTagName("TileMatrix").length) + ", overview scale: " + str(scale)
                            tilematrixsets[tilematrixset.getElementsByTagName('ows:Identifier')[0].firstChild.nodeValue.strip()] = TileMatrixSetMeta(tilematrixset.getElementsByTagName("TileMatrix").length, scale)
                                
                except KeyError, e:
                    log_sig_exit('ERROR', 'Projection ' + projectionId + " " + str(e) + ' missing in TileMatrixSet configuration ' + tilematrixset_configuration, sigevent_url)
                
            projection = Projection(projectionId, wkt, bbox, tilematrixsets, tms_xml, lowercorner, uppercorner)
    
    if projection == None:
        mssg = "Projection " + projectionId + " could not be found in projection configuration file."
        raise Exception(mssg)
    
    return projection

def detect_time(time, archiveLocation, fileNamePrefix, year):
    """
    Checks time element to see if start or end time must be detected on the file system.
    Arguments:
        time -- the time element (DETECT) keyword is utilized
        archiveLocation -- the location of the archive data
        fileNamePrefix -- the prefix of the MRF files
        year -- whether or not the layer uses a year-based directory structure
    """
    times = []
    print "\nAssessing time", time
    time = time.upper()
    detect = "DETECT"
    period = "P1D"
    period_value = 1 # numeric value of period
    archiveLocation = add_trailing_slash(archiveLocation)
    subdaily = False
    
    if not os.path.isdir(archiveLocation):
        message = archiveLocation + " is not a valid location"
        log_sig_err(message, sigevent_url)
        return times
    
    if time == detect or time == '' or time.startswith(detect+'/P'):
    #detect everything including breaks in date
        dates = []
        for dirname, dirnames, filenames in os.walk(archiveLocation, followlinks=True):
            # Print subdirectories
            for subdirname in dirnames:
                print "Searching:", os.path.join(dirname, subdirname)

            for filename in filenames:
                if str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJ") + 5):
                    try:
                        filetime = filename[-12:-5]
                        filedate = datetime.strptime(filetime,"%Y%j")
                        dates.append(filedate)
                    except ValueError:
                        print "Skipping", filename
                elif str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJHHMMSS") + 5):
                    try:
                        filetime = filename[-18:-5]
                        filedate = datetime.strptime(filetime,"%Y%j%H%M%S")
                        dates.append(filedate)
                        subdaily = True
                        period = "PT24H"
                    except ValueError:
                        print "Skipping", filename
                else:
                    print "Ignoring", filename
        dates = sorted(list(set(dates)))
        for testdate in dates:
            print datetime.strftime(testdate,"%Y-%m-%dT%H:%M:%SZ")
        # Get period, attempt to figure out period (in days) if none
        if time.startswith(detect+'/P'):
            period = time.split('/')[1]
        else:
            if len(dates) > 3: #check if the difference between first three dates are the same
                if subdaily == False:
                    diff1 = abs((dates[0] - dates[1]).days)
                    diff2 = abs((dates[1] - dates[2]).days)
                    diff3 = abs((dates[2] - dates[3]).days)
                    if diff1==diff2==diff3:
                        period = "P"+str(diff1)+"D"
                    elif 31 in [diff1, diff2, diff3]:
                        period = "P1M"
                    if 365 in [diff1, diff2, diff3]:
                        period = "P1Y"
                else:
                    diff1 = abs((dates[0] - dates[1]))
                    diff2 = abs((dates[1] - dates[2]))
                    diff3 = abs((dates[2] - dates[3]))
                    if diff1==diff2==diff3:
                        if diff1.seconds % 3600 == 0:
                            period = "PT"+str(diff1.seconds/3600)+"H"
                        elif diff1.seconds % 60 == 0:
                            period = "PT"+str(diff1.seconds/60)+"M"
                        else:
                            period = "PT"+str(diff1.seconds)+"S"
            message = "No period in time configuration for " + fileNamePrefix + " - detected " + period
            log_sig_warn(message, sigevent_url)
        print "Using period " + str(period)
        try:
            if subdaily == False:
                period_value = int(period[1:-1])
            else:
                period_value = int(period[2:-1])
        except ValueError:
            log_sig_err("Mixed period values are not supported on server: " + period, sigevent_url)
        # Search for date ranges
        if len(dates) == 0:
            message = "No files with dates found for '" + fileNamePrefix + "' in '" + archiveLocation + "' - please check if data exists."
            log_sig_err(message, sigevent_url)
            startdate = datetime.now() # default to now
        else:
            startdate = min(dates)
            print "Start of data " + datetime.strftime(startdate,"%Y-%m-%dT%H:%M:%SZ")
        enddate = startdate # set end date to start date for lone dates
        for i, d in enumerate(dates):
            # print d
            if period[-1] == "W":
                next_day = d + timedelta(weeks=period_value)
            elif period[-1] == "M" and subdaily == False:
                next_day = d + relativedelta(months=period_value)
            elif period[-1] == "Y":
                next_day = d + relativedelta(years=period_value)
            elif period[-1] == "H":
                next_day = d + relativedelta(hours=period_value)
            elif period[-1] == "M" and subdaily == True:
                next_day = d + relativedelta(minutes=period_value)
            elif period[-1] == "S":
                next_day = d + relativedelta(seconds=period_value)
            else:
                next_day = d + timedelta(days=period_value)
            
            try:
                if dates[i+1] == next_day:
                    enddate = next_day # set end date to next existing day
                else: # end of range
                    if subdaily == False:
                        print "Break in data beginning on " + datetime.strftime(next_day,"%Y-%m-%d")
                        start = datetime.strftime(startdate,"%Y-%m-%d")
                        end = datetime.strftime(enddate,"%Y-%m-%d")
                    else:
                        print "Break in data beginning on " + datetime.strftime(next_day,"%Y-%m-%dT%H:%M:%SZ")
                        start = datetime.strftime(startdate,"%Y-%m-%dT%H:%M:%SZ")
                        end = datetime.strftime(enddate,"%Y-%m-%dT%H:%M:%SZ")    
                    times.append(start+'/'+end+'/'+period)
                    startdate = dates[i+1] # start new range loop
                    enddate = startdate
            except IndexError:
                # breaks when loop completes
                if subdaily == False:
                    start = datetime.strftime(startdate,"%Y-%m-%d")
                    end = datetime.strftime(enddate,"%Y-%m-%d")
                else:
                    start = datetime.strftime(startdate,"%Y-%m-%dT%H:%M:%SZ")
                    end = datetime.strftime(enddate,"%Y-%m-%dT%H:%M:%SZ")                    
                times.append(start+'/'+end+'/'+period)
                print "End of data " + end
                print "Time ranges: " + ", ".join(times)
                return times
    
    else:
        intervals = time.split('/')
        if intervals[0][0] == 'P': #starts with period, so no start date
            start = detect
        else:
            start = ''
        has_period = False
        for interval in list(intervals):
            if len(interval) > 0:
                if interval[0] == 'P':
                    has_period = True
                    period = interval
                    intervals.remove(interval)
            else:
                intervals.remove(interval)
        if has_period == False:
            message = "No period in time configuration for " + fileNamePrefix + " - using P1D"
            log_sig_warn(message, sigevent_url)
        print "Using period " + period
        if len(intervals) == 2:
            start = intervals[0]
            end = intervals[1]
        else:
            if start == detect:
                end = intervals[0]
            else:
                start = intervals[0]
                end = detect
              
        if start==detect or end==detect:
            newest_year = ''
            oldest_year = ''
            if year == True: # get newest and oldest years
                years = []
                for subdirname in os.walk(archiveLocation, followlinks=True).next()[1]:
                    if subdirname != 'YYYY':
                        years.append(subdirname)
                years = sorted(years)
                print "Year directories available: " + ",".join(years)
                for idx in range(0, len(years)):
                    if len(os.listdir(archiveLocation+'/'+years[idx])) > 0:
                        oldest_year = years[idx]
                        break; 
                for idx in reversed(range(0, len(years))):
                    if len(os.listdir(archiveLocation+'/'+years[idx])) > 0:
                        newest_year = years[idx]
                        break;
        
            print "Available range with data is %s to %s" % (oldest_year, newest_year)
            if newest_year == '' or oldest_year == '':
                mssg = "No data files found in year directories in " + archiveLocation 
                log_sig_err(mssg, sigevent_url)
                return times
                            
        if start==detect:
            for dirname, dirnames, filenames in os.walk(archiveLocation+'/'+oldest_year, followlinks=True):
                dates = []
                for filename in filenames:
                    if str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJ") + 5):
                        try:
                            filetime = filename[-12:-5]
                            filedate = datetime.strptime(filetime,"%Y%j")
                            dates.append(filedate)
                        except ValueError:
                            print "Skipping", filename
                    elif str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJHHMMSS") + 5):
                        try:
                            filetime = filename[-18:-5]
                            filedate = datetime.strptime(filetime,"%Y%j%H%M%S")
                            dates.append(filedate)
                            subdaily = True
                        except ValueError:
                            print "Skipping", filename
                    else:
                        print "Ignoring", filename
                if len(dates) == 0:
                    message = "No valid files with dates found for '" + fileNamePrefix + "' in '" + archiveLocation +"/"+oldest_year + "' - please check if data exists."
                    log_sig_err(message, sigevent_url)
                    return times
                startdate = min(dates)
                if subdaily == False:
                    start = datetime.strftime(startdate,"%Y-%m-%d")
                else:
                    start = datetime.strftime(startdate,"%Y-%m-%dT%H:%M:%SZ")
        
        if end==detect:
            for dirname, dirnames, filenames in os.walk(archiveLocation+'/'+newest_year, followlinks=True):
                dates = []
                for filename in filenames:
                    if str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJ") + 5):
                        try:
                            filetime = filename[-12:-5]
                            filedate = datetime.strptime(filetime,"%Y%j")
                            dates.append(filedate)
                        except ValueError:
                            print "Skipping", filename
                    elif str(filename).startswith(fileNamePrefix) and len(filename) == (len(fileNamePrefix) + len("YYYYJJJHHMMSS") + 5):
                        try:
                            filetime = filename[-18:-5]
                            filedate = datetime.strptime(filetime,"%Y%j%H%M%S")
                            dates.append(filedate)
                            subdaily = True
                        except ValueError:
                            print "Skipping", filename
                    else:
                        print "Ignoring", filename
                enddate = max(dates)
                if subdaily == False:
                    end = datetime.strftime(enddate,"%Y-%m-%d")
                else:
                    end = datetime.strftime(enddate,"%Y-%m-%dT%H:%M:%SZ")
        
        print "Time: start="+start+" end="+end+" period="+period
        time = start+'/'+end+'/'+period
        times.append(time)
        
    return times

def generate_legend(colormap, output, legend_url, orientation):
    """
    Generate an SVG legend graphic from GIBS color map.
    Arguments:
        colormap -- the color map file name
        output -- the output file name
        legend_url -- URL to access legend from GetCapabilities
        orientation -- the orientation of the legend
    """
    
    print "\nLegend location: " + output
    print "Legend URL: " + legend_url
    print "Color Map: " + colormap
    print "Orientation: " + orientation
    pt = 1.25 #pixels in point
    
    if os.path.isfile(output) == False:
        print "Generating new legend"
        cmd = 'oe_generate_legend.py -c '+colormap+' -o ' + output + ' -r ' + orientation
        try:
            run_command(cmd, sigevent_url)
        except Exception, e:
            log_sig_err("Error generating legend: " + str(e), sigevent_url)
    else:
        print "Legend already exists"
        try:
            colormap_file = urllib.urlopen(colormap)
            last_modified = colormap_file.info().getheader("Last-Modified")
            colormap_file.close()
            colormap_time = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S GMT")
            legend_time = datetime.fromtimestamp(os.path.getmtime(output))
            print "Color map last modified on: " + str(colormap_time)
            print "Legend last modified on: " + str(legend_time)
            if colormap_time > legend_time:
                print "Updated color map found"
                print "Generating new legend"
                cmd = 'oe_generate_legend.py -c '+colormap+' -o ' + output + ' -r ' + orientation
                run_command(cmd, sigevent_url)
        except Exception, e:
            log_sig_err("Error generating legend: " + str(e), sigevent_url)
    # check file
    try:
        # Open file.
        svg=open(output, 'r')
    except IOError:
        mssg=str().join(['Cannot read SVG legend file:  ', output])
        sigevent('ERROR', mssg, sigevent_url)
        
    # get width and height
    dom = xml.dom.minidom.parse(svg)
    svgElement = dom.getElementsByTagName('svg')[0]
    height = float(svgElement.attributes['height'].value.replace('pt','')) * pt
    width = float(svgElement.attributes['width'].value.replace('pt','')) * pt
    svg.close()
    
    if orientation == 'horizontal':
        legend_url_template = '<LegendURL format="image/svg+xml" xlink:type="simple" xlink:role="http://earthdata.nasa.gov/gibs/legend-type/horizontal" xlink:href="%s" xlink:title="GIBS Color Map Legend: Horizontal" width="%d" height="%d"/>' % (legend_url, int(width), int(height))
    else:
        legend_url_template = '<LegendURL format="image/svg+xml" xlink:type="simple" xlink:role="http://earthdata.nasa.gov/gibs/legend-type/vertical" xlink:href="%s" xlink:title="GIBS Color Map Legend: Vertical" width="%d" height="%d"/>' % (legend_url, int(width), int(height))
    
    return legend_url_template

def generate_empty_tile(colormap, output, width, height):
    """
    Generate an empty tile from nodata value in GIBS color map.
    Arguments:
        colormap -- the color map file name
        output -- the output file name
        width -- the width of the empty tile
        height -- the height of the empty tile
    """
    
    print "Generating empty tile"
    print "Empty Tile Location: " + output
    print "Color Map: " + colormap
    print "Width: " + str(width)
    print "Height: " + str(height)
    
    try:
        cmd = 'oe_generate_empty_tile.py -c '+colormap+' -o ' + output + ' -x ' + str(width) + ' -y ' + str(height)
        run_command(cmd, sigevent_url)
    except Exception, e:
        log_sig_err("Error generating empty tile: " + str(e), sigevent_url)

    # check file
    try:
        # Get file size
        empty_size = os.path.getsize(output)
        print "Empty tile size: " + str(empty_size)
    except:
        mssg=str().join(['Cannot read generated empty tile:  ', output])
        log_sig_err(mssg, sigevent_url)
    
    return empty_size

def generate_links(detected_times, archiveLocation, fileNamePrefix, year, dataFileLocation):
    """
    Generate a archive links for a layer based on the last provided time period
    Arguments:
        detected_times -- the list of available time periods
        archiveLocation -- the location of the archive data
        fileNamePrefix -- the prefix of the MRF files
        year -- whether or not the layer uses a year-based directory structure
        dataFileLocation -- file location for the default data file
    """
    
    last_time = detected_times[-1].split("/")[1]
    if 'T' in last_time: # sub-daily files
        t = datetime.strptime(last_time,"%Y-%m-%dT%H:%M:%SZ")
        filename = fileNamePrefix + datetime.strftime(t,"%Y%j%H%M%S") + "_"
        last_year = datetime.strftime(t,"%Y")
    else:
        t = datetime.strptime(last_time,"%Y-%m-%d")
        filename = fileNamePrefix + datetime.strftime(t,"%Y%j") + "_"
        last_year = datetime.strftime(t,"%Y")
    
    link_pre, data_ext = os.path.splitext(dataFileLocation)
    link_dir = os.path.dirname(link_pre)
    
    mrf = archiveLocation + ("",str(last_year)+"/")[year] + filename + ".mrf"
    idx = archiveLocation + ("",str(last_year)+"/")[year] + filename + ".idx"
    data = archiveLocation + ("",str(last_year)+"/")[year] + filename + data_ext
    zdb = archiveLocation + ("",str(last_year)+"/")[year] + filename + ".zdb"
    
    mrf_link = link_pre + ".mrf"
    idx_link = link_pre + ".idx"
    data_link = link_pre + data_ext
    zdb_link = link_pre + ".zdb"
    
    # make sure link directory exists
    if not os.path.exists(link_dir):
        os.makedirs(link_dir)
        print "Created directory " + link_dir   
    
    if os.path.isfile(mrf):
        if os.path.lexists(mrf_link):
            os.remove(mrf_link)
            print "Removed existing file " + mrf_link
        os.symlink(mrf, mrf_link)
        print "Created soft link " + mrf_link + " -> " + mrf
    if os.path.isfile(idx):
        if os.path.lexists(idx_link):
            os.remove(idx_link)
            print "Removed existing file " + idx_link
        os.symlink(idx, idx_link)
        print "Created soft link " + idx_link + " -> " + idx
    else:
        log_sig_warn("Default MRF index file " + idx + " does not exist", sigevent_url)
    if os.path.isfile(data):
        if os.path.lexists(data_link):
            os.remove(data_link)
            print "Removed existing file " + data_link
        os.symlink(data, data_link)
        print "Created soft link " + data_link + " -> " + data
    else:
        log_sig_warn("Default MRF data file " + data + " does not exist", sigevent_url)
    if os.path.isfile(zdb):
        if os.path.lexists(zdb_link):
            os.remove(zdb_link)
            print "Removed existing file " + zdb_link
        os.symlink(zdb, zdb_link)
        print "Created soft link " + zdb_link + " -> " + zdb
    
    return mrf_link, idx_link, data_link, zdb_link
    
#-------------------------------------------------------------------------------   

print 'OnEarth Layer Configurator v' + versionNumber

if os.environ.has_key('LCDIR') == False:
    print 'LCDIR environment variable not set.\nLCDIR should point to your OnEarth layer_config directory.\n'
    lcdir = os.path.abspath(os.path.dirname(__file__) + '/..')
else:
    lcdir = os.environ['LCDIR']

usageText = 'oe_configure_layer.py --conf_file [layer_configuration_file.xml] --layer_dir [$LCDIR/layers/] --lcdir [$LCDIR] --projection_config [projection.xml] --sigevent_url [url] --time [ISO 8601] --restart_apache --no_xml --no_cache --no_twms --no_wmts --generate_legend --generate_links --skip_empty_tiles --create_mapfile'

# Define command line options and args.
parser=OptionParser(usage=usageText, version=versionNumber)
parser.add_option('-a', '--archive_config',
                  action='store', type='string', dest='archive_configuration',
                  help='Full path of archive configuration file.  Default: $LCDIR/conf/archive.xml')
parser.add_option('-c', '--conf_file',
                  action='store', type='string', dest='layer_config_filename',
                  help='Full path of layer configuration filename.')
parser.add_option('-d', '--layer_dir',
                  action='store', type='string', dest='layer_directory',
                  help='Full path of directory containing configuration files for layers.  Default: $LCDIR/layers/')
parser.add_option("-e", "--skip_empty_tiles",
                  action="store_true", dest="skip_empty_tiles", 
                  default=False, help="Do not generate empty tiles for layers using color maps in configuration.")
parser.add_option("-g", "--generate_legend",
                  action="store_true", dest="generate_legend", 
                  default=False, help="Generate legends for layers using color maps in configuration.")
parser.add_option('-l', '--lcdir',
                  action='store', type='string', dest='lcdir',
                  default=lcdir,
                  help='Full path of the OnEarth Layer Configurator (layer_config) directory.  Default: $LCDIR')
parser.add_option('-m', '--tilematrixset_config',
                  action='store', type='string', dest='tilematrixset_configuration',
                  help='Full path of TileMatrixSet configuration file.  Default: $LCDIR/conf/tilematrixsets.xml')
parser.add_option("-n", "--no_twms",
                  action="store_true", dest="no_twms", 
                  default=False, help="Do not use configurations for Tiled-WMS")
parser.add_option('-p', '--projection_config',
                  action='store', type='string', dest='projection_configuration',
                  help='Full path of projection configuration file.  Default: $LCDIR/conf/projection.xml')
parser.add_option("-r", "--restart_apache",
                  action="store_true", dest="restart", 
                  default=False, help="Restart the Apache server on completion (requires sudo).")
parser.add_option('-s', '--sigevent_url',
                  action='store', type='string', dest='sigevent_url',
                  default=
                  'http://localhost:8100/sigevent/events/create',
                  help='Default:  http://localhost:8100/sigevent/events/create')
parser.add_option('-t', '--time',
                  action='store', type='string', dest='time',
                  help='ISO 8601 time(s) for single configuration file (conf_file must be specified).')
parser.add_option("-w", "--no_wmts",
                  action="store_true", dest="no_wmts", 
                  default=False, help="Do not use configurations for WMTS.")
parser.add_option("-x", "--no_xml",
                  action="store_true", dest="no_xml", 
                  default=False, help="Do not generate getCapabilities and getTileService XML.")
parser.add_option("-y", "--generate_links",
                  action="store_true", dest="generate_links", 
                  default=False, help="Generate default/current day links in the archive for time varying layers.")
parser.add_option("-z", "--no_cache",
                  action="store_true", dest="no_cache", 
                  default=False, help="Do not copy cache configuration files to cache location.")
parser.add_option("--create_mapfile",
                  action="store_true", dest="create_mapfile", 
                  default=False, help="Create MapServer configuration.")

# Read command line args.
(options, args) = parser.parse_args()
# Configuration filename.
configuration_filename = options.layer_config_filename
# Command line set LCDIR.
lcdir = options.lcdir
# Configuration directory.
if options.layer_directory:
    configuration_directory = options.layer_directory
else:
    configuration_directory = lcdir+'/layers/'
# No XML configurations (getCapabilities, getTileService)
no_xml = options.no_xml
# No cache configuration.
no_cache = options.no_cache
# No Tiled-WMS configuration.
no_twms = options.no_twms
# No WMTS configuration.
no_wmts = options.no_wmts
# No MapServer configuration.
create_mapfile = options.create_mapfile
# Do restart Apache.
restart = options.restart
# Time for conf file.
configuration_time = options.time
# Generate Empty Tiles
skip_empty_tiles = options.skip_empty_tiles
# Generate legends
legend = options.generate_legend
# Generate links
links = options.generate_links
# Projection configuration
if options.projection_configuration:
    projection_configuration = options.projection_configuration
else:
    projection_configuration = lcdir+'/conf/projection.xml'
# TileMatrixSet configuration
if options.tilematrixset_configuration:
    tilematrixset_configuration = options.tilematrixset_configuration
else:
    tilematrixset_configuration = lcdir+'/conf/tilematrixsets.xml'
# Archive configuration
if options.archive_configuration:
    archive_configuration = options.archive_configuration
else:
    archive_configuration = lcdir+'/conf/archive.xml'

# Sigevent URL.
sigevent_url = options.sigevent_url
  
print 'Using ' + lcdir + ' as $LCDIR.'

if no_xml:
    print "no_xml specified, getCapabilities and getTileService files will not be generated"
if no_cache:
    print "no_cache specified, cache configuration files will not be generated"
    restart = False
if no_xml and no_cache:
    print "no_xml and no_cache specified, nothing to do...exiting"
    exit()
if no_twms and no_wmts:
    print "no_twms and no_wmts specified, nothing to do...exiting"
    exit()
    
if configuration_time:
    if configuration_filename == None:
        print "A configuration file must be specified with --time"
        exit()
    else:
        print "Using time='" + configuration_time + "' for " + configuration_filename
        
# set location of tools
if os.path.isfile(os.path.abspath(lcdir)+'/bin/oe_create_cache_config'):
    depth = os.path.abspath(lcdir)+'/bin'
elif distutils.spawn.find_executable('oe_create_cache_config') != None:
    depth = distutils.spawn.find_executable('oe_create_cache_config').split('/oe_create_cache_config')[0]
else:
    depth = '/usr/bin' # default

# Read XML configuration files.

conf_files = []
wmts_endpoints = {}
twms_endpoints = {}

if not options.layer_config_filename:
    conf = subprocess.Popen('ls ' + configuration_directory + '/*.xml',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    for line in conf:
        conf_files.append(line.strip())
else:
    # use only the solo MRF when specified
    conf_files.append(configuration_filename)
    
print 'Configuration file(s):'
print conf_files
if conf_files==[]:
    mssg = 'No configuration files found.'
    log_sig_exit('ERROR', mssg, sigevent_url)
    
for conf in conf_files:
    
    try:
        # Open file.
        config_file=open(conf, 'r')
        print ('\nUsing config: ' + conf)
    except IOError:
        log_sig_err(str().join(['Cannot read configuration file: ', conf]), sigevent_url)
        continue
    else:
        dom = xml.dom.minidom.parse(config_file)
        
        #Required parameters
        try:
            identifier = get_dom_tag_value(dom, 'Identifier')
        except IndexError:
            log_sig_err('Required <Identifier> element is missing in ' + conf, sigevent_url)
            continue
        try:
            title = get_dom_tag_value(dom, 'Title')
        except IndexError:
            log_sig_err('Required <Title> element is missing in ' + conf, sigevent_url)
            continue
        try:
            compression = get_dom_tag_value(dom, 'Compression')
            compression = compression.upper()
            if compression == "JPG":
                compression = "JPEG"
            if compression == "PPNG":
                compression = "PNG"
            if compression == "TIFF":
                compression = "TIF"
            if compression not in ["JPEG", "PNG", "TIF"]:
                log_sig_err('<Compression> must be either JPEG, PNG, or TIF in ' + conf, sigevent_url)
                continue
        except IndexError:
            log_sig_err('Required <Compression> element is missing in ' + conf, sigevent_url)
            continue
        try:
            tilematrixset = get_dom_tag_value(dom, 'TileMatrixSet')
        except:
            log_sig_err('Required <TileMatrixSet> element is missing in ' + conf, sigevent_url)
            continue
        try:
            emptyTileSize = int(get_dom_tag_value(dom, 'EmptyTileSize'))
        except IndexError:
            try:
                emptyTileSize = ""
                emptyTile = get_dom_tag_value(dom, 'EmptyTile')
            except IndexError: # Required if EmptyTile is not specified
                log_sig_err('Required <EmptyTileSize> or <EmptyTile> element is missing in ' + conf, sigevent_url)
                continue
        try:
            fileNamePrefix = get_dom_tag_value(dom, 'FileNamePrefix')
        except IndexError:
            log_sig_err('Required <FileNamePrefix> element is missing in ' + conf, sigevent_url)
            continue
        try:
            environmentConfig = get_dom_tag_value(dom, 'EnvironmentConfig')
            try:
                environment = get_environment(environmentConfig)
            except Exception, e:
                log_sig_err(str(e), sigevent_url)
                continue
        except IndexError:
            log_sig_err('Required <EnvironmentConfig> element is missing in ' + conf, sigevent_url)
            continue
            
        cacheLocation_wmts = environment.cacheLocation_wmts
        cacheBasename_wmts = environment.cacheBasename_wmts
        cacheLocation_twms = environment.cacheLocation_twms
        cacheBasename_twms = environment.cacheBasename_twms
        cacheConfig = cacheLocation_wmts # default to WMTS cache location
        wmts_getCapabilities = environment.getCapabilities_wmts
        twms_getCapabilities = environment.getCapabilities_twms
        getTileService = environment.getTileService
        wmtsServiceUrl = environment.wmtsServiceUrl
        twmsServiceUrl = environment.twmsServiceUrl

        # Optional parameters
        try:
            tiledGroupName = get_dom_tag_value(dom, 'TiledGroupName')
        except:
            tiledGroupName = identifier + " tileset"
        try:
            abstract = get_dom_tag_value(dom, 'Abstract')
        except:
            abstract = identifier + " abstract"
        try:
            archiveLocation = get_dom_tag_value(dom, 'ArchiveLocation')
        except:
            archiveLocation = None
        try:
            static = dom.getElementsByTagName('ArchiveLocation')[0].attributes['static'].value.lower() in ['true']
        except:
            static = True
        try:
            year = dom.getElementsByTagName('ArchiveLocation')[0].attributes['year'].value.lower() in ['true']
        except:
            year = False
        try:
            subdaily = dom.getElementsByTagName('ArchiveLocation')[0].attributes['subdaily'].value.lower() in ['true']
        except:
            subdaily = False
        try:
            archive_root = get_archive(dom.getElementsByTagName('ArchiveLocation')[0].attributes['root'].value, archive_configuration)
        except:
            archive_root = ""
        archiveLocation = archive_root + archiveLocation
        try:
            headerFileName = get_dom_tag_value(dom, 'HeaderFileName')
        except:
            headerFileName = None
        try:
            dataFileLocation = get_dom_tag_value(dom, 'DataFileLocation')
        except:
            dataFileLocation = None
        try:
            indexFileLocation = get_dom_tag_value(dom, 'IndexFileLocation')
        except:
            indexFileLocation = None
        try:
            zIndexFileLocation = get_dom_tag_value(dom, 'ZIndexFileLocation')
        except:
            zIndexFileLocation = None
        try:
            projection = get_projection(get_dom_tag_value(dom, 'Projection'), projection_configuration, lcdir, tilematrixset_configuration)
        except IndexError:
            log_sig_err('Required <Projection> element is missing in ' + conf, sigevent_url)
            continue
        except Exception, e:
            log_sig_err(str(e), sigevent_url)
            continue
        try:
            colormap = get_dom_tag_value(dom, 'ColorMap')
        except:
            colormap = None
        try:
            emptyTile = get_dom_tag_value(dom, 'EmptyTile')
        except:
            emptyTile = None
        try:
            if emptyTile == None:
                emptyTileOffset = dom.getElementsByTagName('EmptyTileSize')[0].attributes['offset'].value
            else:
                emptyTileOffset = dom.getElementsByTagName('EmptyTile')[0].attributes['offset'].value
        except:
            emptyTileOffset = 0
            
        # Patterns
        patterns = []
        rest_patterns = []
        patternTags = dom.getElementsByTagName('Pattern')
        for pattern in patternTags:
            try:
                if pattern.attributes['type'].value == "WMTS-REST": # append WMTS REST patterns
                    rest_patterns.append(pattern.firstChild.data.strip())
                else: # assume TWMS key-value pair
                    patterns.append(pattern.firstChild.data.strip())
            except KeyError: # append if type does not exist
                patterns.append(pattern.firstChild.data.strip())

#         if len(patterns) == 0:
#             log_sig_err('No <Pattern> elements for TWMS found in ' + conf, sigevent_url)
#             continue
            
        # Time
        if configuration_time:
            times = configuration_time.split(',')
        else:  
            times = []  
            timeTags = dom.getElementsByTagName('Time')
            for time in timeTags:
                try:
                    times.append(time.firstChild.data.strip())
                except AttributeError:
                    times.append('')
                    
        # Set End Points
        if environment.wmts_dir != None:
            wmtsEndPoint = environment.wmts_dir
        else: # default projection dir
            wmtsEndPoint = lcdir + "/wmts/" + projection.id.replace(":","")
        if environment.twms_dir != None:
            twmsEndPoint = environment.twms_dir
        else:
            # default projection dir
            twmsEndPoint = lcdir + "/twms/" + projection.id.replace(":","")

        wmts_endpoints[wmtsEndPoint] = WMTSEndPoint(wmtsEndPoint, cacheLocation_wmts, cacheBasename_wmts, wmts_getCapabilities, projection)
        twms_endpoints[twmsEndPoint] = TWMSEndPoint(twmsEndPoint, cacheLocation_twms, cacheBasename_twms, twms_getCapabilities, getTileService, projection)
        
        # Close file.
        config_file.close()
     
    log_info_mssg('config: Identifier: ' + identifier)
    log_info_mssg('config: Title: ' + title)
    log_info_mssg('config: FileNamePrefix: ' + fileNamePrefix)
    log_info_mssg('config: TiledGroupName: ' + tiledGroupName)
    log_info_mssg('config: Compression: ' + compression)
    log_info_mssg('config: TileMatrixSet: ' + tilematrixset)
    if emptyTile:
        log_info_mssg('config: EmptyTile: ' + emptyTile)
    if str(emptyTileSize) != "":
        log_info_mssg('config: EmptyTileSize: ' + str(emptyTileSize))
    log_info_mssg('config: EmptyTileOffset: ' + str(emptyTileOffset))
    if headerFileName:
        log_info_mssg('config: HeaderFileName: ' + headerFileName)
    if archiveLocation:
        log_info_mssg('config: ArchiveLocation static=' + str(static) + ' year=' + str(year) + ' subdaily=' + str(subdaily) + ': ' + archiveLocation)
    if dataFileLocation:
        log_info_mssg('config: DataFileLocation: ' + dataFileLocation)
    if indexFileLocation:
        log_info_mssg('config: IndexFileLocation: ' + indexFileLocation)
    if zIndexFileLocation:
        log_info_mssg('config: ZIndexFileLocation: ' + zIndexFileLocation)
    if projection:
        log_info_mssg('config: Projection: ' + str(projection.id))
    if getTileService:
        log_info_mssg('config: GetTileServiceLocation: ' + str(getTileService))
    if wmts_getCapabilities:
        log_info_mssg('config: WMTS GetCapabilitiesLocation: ' + str(wmts_getCapabilities))
    if twms_getCapabilities:
        log_info_mssg('config: TWMS GetCapabilitiesLocation: ' + str(twms_getCapabilities))
    if cacheLocation_wmts:
        log_info_mssg('config: WMTS CacheLocation: ' + str(cacheLocation_wmts))
    if cacheLocation_twms:
        log_info_mssg('config: TWMS CacheLocation: ' + str(cacheLocation_twms))
    if cacheBasename_wmts:
        log_info_mssg('config: WMTS Basename: ' + str(cacheLocation_wmts))
    if cacheBasename_twms:
        log_info_mssg('config: TWMS Basename: ' + str(cacheLocation_twms))
    if wmtsEndPoint:
        log_info_mssg('config: WMTSEndPoint: ' + str(wmtsEndPoint))
    if twmsEndPoint:
        log_info_mssg('config: TWMSEndPoint: ' + str(twmsEndPoint))
    if colormap:
        log_info_mssg('config: ColorMap: ' + str(colormap))
    log_info_mssg('config: Patterns: ' + str(patterns))
    if len(rest_patterns) > 0:
        log_info_mssg('config: WMTS-REST Patterns: ' + str(rest_patterns))
    if len(times) > 0:
        log_info_mssg('config: Time: ' + str(times))
    
    # get MRF archetype

    if archiveLocation != None:
        archiveLocation = add_trailing_slash(archiveLocation)
        # check if absolute path or else use relative to cache location
        if archiveLocation[0] == '/':
            mrfLocation = archiveLocation
        else:
            mrfLocation = cacheConfig + archiveLocation
            archiveLocation = mrfLocation
    else: # use archive location relative to cache if not defined
        mrfLocation = add_trailing_slash(cacheConfig)
    if year == True:
        if archiveLocation != None:
            mrfLocation =  mrfLocation +'YYYY/'
        else:
            mrfLocation =  mrfLocation + fileNamePrefix +'/YYYY/'
    
    if static == True:
        mrf = mrfLocation + fileNamePrefix + '.mrf'
        if headerFileName == None:
            headerFileName = mrf
    else:
        if subdaily == True:
            mrf = mrfLocation + fileNamePrefix + 'TTTTTTTTTTTTT_.mrf'
        else:
            mrf = mrfLocation + fileNamePrefix + 'TTTTTTT_.mrf'
        if headerFileName == None:
            headerFileName = mrf
    
    if indexFileLocation == None:
        if archiveLocation != None and archiveLocation[0] == '/':
            # use absolute path of archive
            indexFileLocation = mrf.replace('.mrf','.idx')
        else:
            # use relative path to cache
            indexFileLocation = mrf.replace(cacheConfig,'').replace('.mrf','.idx')
        
    if dataFileLocation == None:
        if archiveLocation != None and archiveLocation[0] == '/':
            # use absolute path of archive
            dataFileLocation = mrf
        else:
            # use relative path to cache
            dataFileLocation = mrf.replace(cacheConfig,'')
        if compression.lower() in ['jpg', 'jpeg']:
            dataFileLocation = dataFileLocation.replace('.mrf','.pjg')
            mrf_format = 'image/jpeg'
        elif compression.lower() in ['tif', 'tiff']:
            dataFileLocation = dataFileLocation.replace('.mrf','.ptf')
            mrf_format = 'image/tiff'
        else:
            dataFileLocation = dataFileLocation.replace('.mrf','.ppg')
            mrf_format = 'image/png'

    if zIndexFileLocation == None:
        if archiveLocation != None and archiveLocation[0] == '/':
            # use absolute path of archive
            zIndexFileLocation = mrf
        else:
            # use relative path to cache
            zIndexFileLocation = mrf.replace(cacheConfig,'')
        zIndexFileLocation = zIndexFileLocation.replace('.mrf','.zdb')

    # Open MRF header if one has been supplied
    if os.path.isfile(headerFileName):
        log_info_mssg('MRF Archetype: ' + headerFileName)
        try:
            mrf_file = open(headerFileName, 'r')
        except IOError:
            log_sig_err(str().join(['Cannot read MRF header file: ', headerFileName]), sigevent_url)
            continue
        else:
            try:
                header_dom = xml.dom.minidom.parse(mrf_file)
            except:
                log_sig_err(str().join(['Bad MRF header file: ', headerFileName]), sigevent_url)
            else:
                header_file_present = True
    else:
        header_file_present = False
        log_info_mssg('No MRF Archetype supplied')    
    
    mrf_base = os.path.basename(headerFileName)
    
    # Create base MRF document
    mrf_impl = xml.dom.minidom.getDOMImplementation()
    mrf_dom = mrf_impl.createDocument(None, 'MRF_META', None)
    mrf_meta = mrf_dom.documentElement

    # Create <Raster> tag
    raster_node = mrf_dom.createElement('Raster')

    # Check if <Size> tag present and has all 3 required values (x,y,c)
    try:
        size_node = dom.getElementsByTagName('Size')[0]
    except:
        try:
            size_node = header_dom.getElementsByTagName('Size')[0]
        except:
            size_node = None
            log_sig_err("<Size> tag not present in layer config or MRF header file", sigevent_url)
    finally:
        if size_node != None:
            if not all(attr in size_node.attributes.keys() for attr in ('c','x','y')):
                log_sig_err("<Size> tag needs to have attributes x, y, and c", sigevent_url)
            else:
                raster_node.appendChild(size_node)
                bands = size_node.getAttribute('c')

    # Create compression node
    compression_node = mrf_dom.createElement('Compression')
    compression_text_node = mrf_dom.createTextNode(compression)
    compression_node.appendChild(compression_text_node)
    raster_node.appendChild(compression_node)

    # Check if <DataValues> tag is present and the NoData attribute is present
    try:
        datavalues_node = dom.getElementsByTagName('DataValues')[0]
    except:
        try:
            datavalues_node = header_dom.getElementsByTagName('DataValues')[0]
        except:
            datavalues_node = None
    finally:
        if datavalues_node is not None:    
            raster_node.appendChild(datavalues_node)

    # Check if the <Quality> tag is present and of a valid type
    try:
        quality_node = dom.getElementsByTagName('Quality')[0]
    except:
        try:
            quality_node = header_dom.getElementsByTagName('Quality')[0]
        except:
            quality_node = None
            # log_sig_err("<Quality> tag not present in layer config or MRF header file.", sigevent_url)
    finally:    
        if quality_node is not None:    
            if quality_node.firstChild.nodeValue >= 0 and quality_node.firstChild.nodeValue <= 100:
                log_sig_err("<Quality> tag must be an integer between 1 and 100", sigevent_url)
            else:
                raster_node.appendChild(quality_node)

    # Check if <PageSize> node is present and has c, x, and y attributes
    try:
        page_size_node = dom.getElementsByTagName('PageSize')[0]
    except:
        try:
            page_size_node = header_dom.getElementsByTagName('PageSize')[0]
        except:
            page_size_node = None
            log_sig_err("<PageSize> tag not present in layer config or MRF header file", sigevent_url)
    finally:
        if page_size_node is not None:
            if all (attr in page_size_node.attributes.keys() for attr in ('c','x','y')):
                raster_node.appendChild(page_size_node)
            else:
                log_sig_err("<PageSize> requires c, x, and y attributes", sigevent_url)

    # Add <Raster> tag to MRF
    mrf_meta.appendChild(raster_node)

    # Create <Rsets> 
    try:
        rsets_node = dom.getElementsByTagName('Rsets')[0]
    except:
        try:
            rsets_node = header_dom.getElementsByTagName('Rsets')[0]
        except:
            rsets_node = None
            log_sig_err("<Rsets> tag not present in layer config or MRF header file", sigevent_url)
    if rsets_node is not None:
        try:
            scale_attribute = rsets_node.getAttribute('scale')
        except:
            log_sig_err("Attribute 'scale' not present in <Rsets> tag", sigevent_url)    
        else:
            try:
                if scale_attribute:
                    if int(scale_attribute) != projection.tilematrixsets[tilematrixset].scale:
                        log_sig_err("Overview scales do not match - " + tilematrixset + ": " + str(str(projection.tilematrixsets[tilematrixset].scale)) + ", " + "Provided: " + scale_attribute, sigevent_url)
                        continue
                if projection.tilematrixsets[tilematrixset].levels > 1:
                    rsets_node.setAttribute('scale', str(projection.tilematrixsets[tilematrixset].scale))
            except KeyError:
                log_sig_err("Invalid TileMatrixSet " + tilematrixset + " for projection " + projection.id, sigevent_url)
                continue
        # Add data file locations
        dataFileNameElement = mrf_dom.createElement('DataFileName')
        dataFileNameElement.appendChild(mrf_dom.createTextNode(dataFileLocation))
        indexFileNameElement = mrf_dom.createElement('IndexFileName')
        indexFileNameElement.appendChild(mrf_dom.createTextNode(indexFileLocation))
        rsets_node.appendChild(dataFileNameElement)
        rsets_node.appendChild(indexFileNameElement)

    # Add index file name
    if size_node.hasAttribute('z'):
        z_index_node = mrf_dom.createElement('ZIndexFileName')
        z_index_text_node = mrf_dom.createTextNode(zIndexFileLocation)
        z_index_node.appendChild(z_index_text_node)
        rsets_node.appendChild(z_index_node)

    mrf_meta.appendChild(rsets_node)
    
    # Create GeoTags 
    geotag_node = mrf_dom.createElement('GeoTags')
    # Check for bounding box
    try:
        bounding_box_node = dom.getElementsByTagName('BoundingBox')[0]
    except:
        try:
            bounding_box_node = header_dom.getElementsByTagName('BoundingBox')[0]
        except:
            bounding_box_node = None
            log_sig_err("<BoundingBox> tag not present in layer config or MRF header file", sigevent_url)
    finally:
        if bounding_box_node is not None:
            if all (attr in bounding_box_node.attributes.keys() for attr in ('minx','miny','maxx','maxy')):
                geotag_node.appendChild(bounding_box_node)
            else:
                log_sig_err("<BoundingBox> requires minx, miny, maxx, and maxy attributes", sigevent_url)

    mrf_meta.appendChild(geotag_node)

    twms = mrf_dom.createElement('TWMS')
    levelsElement = mrf_dom.createElement('Levels')
    levelsElement.appendChild(mrf_dom.createTextNode(str(projection.tilematrixsets[tilematrixset].levels)))
    
    if emptyTile != None:
        # Generate empty tile and override size if colormap is used
        if colormap != None and skip_empty_tiles == False:
            pageSize = mrf_dom.getElementsByTagName('PageSize')[0]
            tileX = int(pageSize.getAttribute('x'))
            tileY = int(pageSize.getAttribute('y'))
            if environment.colormap_dir != None:
                colormap_path = environment.colormap_dir + colormap
            else:
                colormap_path = colormap
                message = "ColorMapLocation not defined for environment " + environmentConfig + " - Trying colormap path " + colormap_path
                log_sig_warn(message, sigevent_url)
            emptyTileSize = generate_empty_tile(colormap_path, emptyTile, tileX, tileY)
        else: # Override size if there is no colormap
            try:
                # Get file size
                print "\nReading empty tile file: " + emptyTile
                emptyTileSize = os.path.getsize(emptyTile)
                print "Empty tile size: " + str(emptyTileSize)
            except:
                mssg=str().join(['Cannot read empty tile:  ', emptyTile])
                log_sig_err(mssg, sigevent_url)
    
    emptyInfoElement = mrf_dom.createElement('EmptyInfo')
    emptyInfoElement.setAttribute('size', str(emptyTileSize))
    emptyInfoElement.setAttribute('offset', str(emptyTileOffset))
    twms.appendChild(levelsElement)
    twms.appendChild(emptyInfoElement)

# No longer used
#     if colormap:
#         metadataElement = mrf_dom.createElement('Metadata')
#         metadataElement.appendChild(mrf_dom.createTextNode(colormap))
#         twms.appendChild(twms.appendChild(metadataElement))
    
    # add default TWMS patterns
    twms_time_pattern = "request=GetMap&layers=%s&srs=%s&format=%s&styles=&time=[-0-9]*&width=512&height=512&bbox=[-,\.0-9+Ee]*" % (identifier, str(projection.id), mrf_format.replace("/","%2F"))
    twms_notime_pattern = "request=GetMap&layers=%s&srs=%s&format=%s&styles=&width=512&height=512&bbox=[-,\.0-9+Ee]*" % (identifier, str(projection.id), mrf_format.replace("/","%2F"))
    patterns.append(twms_time_pattern)
    patterns.append(twms_notime_pattern)

    patternElements = []
    for pattern in patterns:
        patternElements.append(mrf_dom.createElement('Pattern'))
        patternElements[-1].appendChild(mrf_dom.createCDATASection(pattern))
    
    for patternElement in patternElements:
        twms.appendChild(patternElement)
    
    # Time elements
    detected_times = []
    if static == False:
        timeElements = []
        for time in times:
            detected_times = detect_time(time, archiveLocation, fileNamePrefix, year)
            for detected_time in detected_times:
                timeElements.append(mrf_dom.createElement('Time'))
                timeElements[-1].appendChild(mrf_dom.createTextNode(detected_time))

        for timeElement in timeElements:
            twms.appendChild(timeElement)
                
    mrf_meta.appendChild(twms)
        
    if projection:
        projectionElement = mrf_dom.createElement('Projection')
        projectionElement.appendChild(mrf_dom.createCDATASection(projection.wkt))
        mrf_meta.appendChild(projectionElement)
    
    if not os.path.exists(twmsEndPoint):
        os.makedirs(twmsEndPoint)
    if not os.path.exists(wmtsEndPoint):
        os.makedirs(wmtsEndPoint)
        
    twms_mrf_filename = twmsEndPoint+'/'+mrf_base
    twms_mrf_file = open(twms_mrf_filename,'w+')

    formatted_xml = get_pretty_xml(mrf_dom)
    twms_mrf_file.write(formatted_xml)
    twms_mrf_file.seek(0)

    wmts_mrf_filename = wmtsEndPoint+'/'+mrf_base
    # check if file already exists and has same TileMatrixSet, if not then create another file
    if os.path.isfile(wmts_mrf_filename):
        wmts_mrf_file = open(wmts_mrf_filename,'r')
        if tilematrixset not in wmts_mrf_file.read():
            log_sig_warn(tilematrixset + " not found in existing " + wmts_mrf_filename + ". Creating new file for TileMatrixSet.", sigevent_url)
            wmts_mrf_filename = wmts_mrf_filename.split(".mrf")[0] + "_" + tilematrixset + ".mrf"
        wmts_mrf_file.close()
        
    wmts_mrf_file = open(wmts_mrf_filename,'w+')
    lines = twms_mrf_file.readlines()
    
    # change patterns for WMTS
    pattern_replaced = False
    try:
        wmts_pattern = "<![CDATA[SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=%s&STYLE=(default)?&TILEMATRIXSET=%s&TILEMATRIX=[0-9]*&TILEROW=[0-9]*&TILECOL=[0-9]*&FORMAT=%s]]>" % (identifier, tilematrixset, mrf_format.replace("/","%2F"))
    except KeyError:
        log_sig_exit('ERROR', 'TileMatrixSet ' + tilematrixset + ' not found for projection: ' + projection.id, sigevent_url)
    for line in lines:
        if '<Pattern>' in line:
            if pattern_replaced == False:
                patternline = line.split('Pattern')
                line = patternline[0] + "Pattern>" + wmts_pattern + "</Pattern" + patternline[-1]               
                pattern_replaced = True
            else:
                line = ''
        wmts_mrf_file.write(line)
    
    twms_mrf_file.close()
    wmts_mrf_file.seek(0)
    wmts_mrf_file.close()
    try:
        mrf_file.close()
    except:
        pass
    
    print '\n'+ twms_mrf_filename + ' configured successfully\n'
    print '\n'+ wmts_mrf_filename + ' configured successfully\n'
    
    # generate archive links if requested
    if links == True:
        if len(detected_times) > 0:
            print "Generating archive links for " + fileNamePrefix
            generate_links(detected_times, archiveLocation, fileNamePrefix, year, dataFileLocation)
        else:
            print fileNamePrefix + " is not a time varying layer" 

    # generate color map if requested
    legendUrl_vertical = ''
    legendUrl_horizontal = '' 
    if legend == True and colormap != None:
        legend_output = ''
        try:
            legend_output = environment.legend_dir + identifier
        except:
            message = "Legend directory has not been defined for environment with cache location: " + environment.cache
            log_sig_err(message, sigevent_url)
        if environment.colormap_dir != None:
            colormap_path = environment.colormap_dir + colormap
        else:
            colormap_path = colormap
            message = "ColorMapLocation not defined for environment " + environmentConfig + " - Trying colormap path " + colormap_path
            log_sig_warn(message, sigevent_url)
        try:
            if environment.legendUrl != None:
                if legend_output != '':
                    legendUrl_vertical = generate_legend(colormap_path, legend_output + '_V.svg', environment.legendUrl + identifier + '_V.svg', 'vertical')
                    legendUrl_horizontal = generate_legend(colormap_path, legend_output + '_H.svg', environment.legendUrl + identifier + '_H.svg', 'horizontal')
            else:
                message = "Legend URL has not been defined for environment with cache location: " + environment.cache
                log_sig_err(message, sigevent_url)
        except:
            message = "Error generating legend for " + identifier
            log_sig_err(message, sigevent_url)
            
# Modify service files
    

    #getCapabilities TWMS
    if no_twms == False and no_xml == False:
        try:
            # Copy and open base GetCapabilities.
            getCapabilities_file = twmsEndPoint+'/getCapabilities.xml'
            shutil.copyfile(lcdir+'/conf/getcapabilities_base_twms.xml', getCapabilities_file)
            getCapabilities_base=open(getCapabilities_file, 'r+')
        except IOError:
            mssg=str().join(['Cannot read getcapabilities_base_twms.xml file:  ', 
                             lcdir+'/conf/getcapabilities_base_twms.xml'])
            log_sig_exit('ERROR', mssg, sigevent_url)
        else:
            lines = getCapabilities_base.readlines()
            for idx in range(0, len(lines)):
                if '<SRS></SRS>' in lines[idx]:
                    lines[idx] =  lines[idx].replace('<SRS></SRS>', '<SRS>'+projection.id+'</SRS>')
                if '<CRS></CRS>' in lines[idx]:
                    lines[idx] =  lines[idx].replace('<CRS></CRS>', '<CRS>'+projection.id+'</CRS>')
                if 'OnlineResource' in lines[idx]:
                    spaces = lines[idx].index('<')
                    onlineResource = xml.dom.minidom.parseString(lines[idx]).getElementsByTagName('OnlineResource')[0]
                    onlineResource.attributes['xlink:href'] = twmsServiceUrl
                    lines[idx] = (' '*spaces) + onlineResource.toprettyxml(indent=" ")
            getCapabilities_base.seek(0)
            getCapabilities_base.truncate()
            getCapabilities_base.writelines(lines)
            getCapabilities_base.close()
    
        #getTileService
    if no_twms == False and no_xml == False:
        try:
            # Copy and open base GetTileService.
            getTileService_file = twmsEndPoint+'/getTileService.xml'
            shutil.copyfile(lcdir+'/conf/gettileservice_base.xml', getTileService_file)
            getTileService_base=open(getTileService_file, 'r+')
        except IOError:
            mssg=str().join(['Cannot read gettileservice_base.xml file:  ', 
                             lcdir+'/conf/gettileservice_base.xml'])
            log_sig_exit('ERROR', mssg, sigevent_url)
        else:
            lines = getTileService_base.readlines()
            for idx in range(0, len(lines)):
                if 'BoundingBox' in lines[idx]:
                    lines[idx] = lines[idx].replace("{minx}",projection.lowercorner[0]).replace("{miny}",projection.lowercorner[1]).replace("{maxx}",projection.uppercorner[0]).replace("{maxy}",projection.uppercorner[1])
                if 'OnlineResource' in lines[idx]:
                    spaces = lines[idx].index('<')
                    onlineResource = xml.dom.minidom.parseString(lines[idx]).getElementsByTagName('OnlineResource')[0]
                    onlineResource.attributes['xlink:href'] = twmsServiceUrl
                    lines[idx] = (' '*spaces) + onlineResource.toprettyxml(indent=" ")
            getTileService_base.seek(0)
            getTileService_base.truncate()
            getTileService_base.writelines(lines)
            getTileService_base.close()
    
    #getCapabilities WMTS modify Service URL
    if no_wmts == False and no_xml == False:
        try:
            # Copy and open base GetCapabilities.
            getCapabilities_file = wmtsEndPoint+'/getCapabilities.xml'
            shutil.copyfile(lcdir+'/conf/getcapabilities_base_wmts.xml', getCapabilities_file)
            getCapabilities_base=open(getCapabilities_file, 'r+')
        except IOError:
            mssg=str().join(['Cannot read getcapabilities_base_wmts.xml file:  ', 
                             lcdir+'/conf/getcapabilities_base_wmts.xml'])
            log_sig_exit('ERROR', mssg, sigevent_url)
        else:
            lines = getCapabilities_base.readlines()
            for idx in range(0, len(lines)):
                if '<ows:Get' in lines[idx]:
                    spaces = lines[idx].index('<')
                    getUrlLine = lines[idx].replace('ows:Get','Get xmlns:xlink="http://www.w3.org/1999/xlink"').replace('>','/>')
                    getUrl = xml.dom.minidom.parseString(getUrlLine).getElementsByTagName('Get')[0]
                    if '1.0.0/WMTSCapabilities.xml' in lines[idx]:
                        getUrl.attributes['xlink:href'] = wmtsServiceUrl + '1.0.0/WMTSCapabilities.xml'
                    elif 'wmts.cgi?' in lines[idx]:
                        getUrl.attributes['xlink:href'] = wmtsServiceUrl + 'wmts.cgi?'
                    else:
                        getUrl.attributes['xlink:href'] = wmtsServiceUrl
                    lines[idx] = (' '*spaces) + getUrl.toprettyxml(indent=" ").replace('Get','ows:Get').replace(' xmlns:xlink="http://www.w3.org/1999/xlink"','').replace('/>','>')
                if 'ServiceMetadataURL' in lines[idx]:
                    spaces = lines[idx].index('<')
                    serviceMetadataUrlLine = lines[idx].replace('ServiceMetadataURL','ServiceMetadataURL xmlns:xlink="http://www.w3.org/1999/xlink"')
                    serviceMetadataUrl = xml.dom.minidom.parseString(serviceMetadataUrlLine).getElementsByTagName('ServiceMetadataURL')[0]
                    serviceMetadataUrl.attributes['xlink:href'] = wmtsServiceUrl + '1.0.0/WMTSCapabilities.xml'
                    lines[idx] = (' '*spaces) + serviceMetadataUrl.toprettyxml(indent=" ").replace(' xmlns:xlink="http://www.w3.org/1999/xlink"','')
            getCapabilities_base.seek(0)
            getCapabilities_base.truncate()
            getCapabilities_base.writelines(lines)
            getCapabilities_base.close()   
            
        
    # create WMTS layer metadata for GetCapabilities
    if no_wmts == False:
        try:
            # Open layer XML file
            layer_xml=open(wmts_mrf_filename.replace('.mrf','.xml'), 'w+')
        except IOError:
            mssg=str().join(['Cannot read layer XML file:  ', 
                             wmts_mrf_filename.replace('.mrf','.xml')])
            log_sig_exit('ERROR', mssg, sigevent_url)
    
        wmts_layer_template = """<Layer>
            <ows:Title xml:lang=\"en\">$Title</ows:Title>
            $BoundingBox
            <ows:Identifier>$Identifier</ows:Identifier>
            <ows:Metadata xlink:type="simple" xlink:role="http://earthdata.nasa.gov/gibs/metadata-type/colormap" xlink:href="$ColorMap" xlink:title="GIBS Color Map: Data - RGB Mapping"/>
            <Style isDefault="true">
                <ows:Title xml:lang=\"en\">default</ows:Title>
                <ows:Identifier>default</ows:Identifier>
                $LegendURL_vertical
                $LegendURL_horizontal
            </Style>
            <Format>$Format</Format>
            <Dimension>
                <ows:Identifier>time</ows:Identifier>
                <UOM>ISO8601</UOM>
                <Default>$DefaultDate</Default>
                <Current>false</Current>
                <Value>$DateRange</Value>
            </Dimension>
            <TileMatrixSetLink>
                <TileMatrixSet>$TileMatrixSet</TileMatrixSet>
            </TileMatrixSetLink>
            <ResourceURL format="$Format" resourceType="tile" template="$WMTSServiceURL$Identifier/default/{Time}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.$FileType"/>
        </Layer>"""
    
        layer_output = ""
        lines = wmts_layer_template.splitlines(True)
        for line in lines:
            # replace lines in template
            if '<Layer>' in line:
                line = '         '+line
            if '</Layer>' in line:
                line = ' '+line+'\n'                
            if '$Title' in line:
                line = line.replace("$Title",title)
            if '$BoundingBox' in line:
                line = line.replace("$BoundingBox",projection.bbox_xml)
            if '$Identifier' in line:
                line = line.replace("$Identifier",identifier)
            if '$LegendURL_vertical' in line:
                line = line.replace("$LegendURL_vertical",legendUrl_vertical)
            if '$LegendURL_horizontal' in line:
                line = line.replace("$LegendURL_horizontal",legendUrl_horizontal)
            if '$ColorMap' in line:
                if colormap == None:
                    line = ''
                else:
                    if environment.colormapUrl != None:
                        colormapUrl = environment.colormapUrl + colormap
                    else:
                        colormapUrl = colormap
                        message = "ColorMapURL not defined for environment " + environmentConfig + " - Trying colormap URL " + colormapUrl
                        log_sig_warn(message, sigevent_url)
                    line = line.replace("$ColorMap",str(colormapUrl))
            if '$Format' in line:
                line = line.replace("$Format",mrf_format)
            if '$FileType' in line:
                line = line.replace("$FileType",mrf_format.split('/')[1])
            if '$WMTSServiceURL' in line:
                line = line.replace("$WMTSServiceURL",environment.wmtsServiceUrl)      
            if '$TileMatrixSet' in line:
                line = line.replace("$TileMatrixSet",tilematrixset)
                tilematrixset_line = line
            if static == True or len(timeElements)==0:
                if any(x in line for x in ['Dimension', '<ows:Identifier>time</ows:Identifier>', '<UOM>ISO8601</UOM>', '$DefaultDate', '<Current>false</Current>', '$DateRange']):
                    line = ''
            else:
                if '$DefaultDate' in line:
                    defaultDate = ''
                    for timeElement in timeElements:
                        defaultDate = timeElement.firstChild.data.strip().split('/')[1]
                    line = line.replace("$DefaultDate",defaultDate)
                if '$DateRange' in line:
                    line = line.replace("$DateRange",timeElements[0].firstChild.data.strip())
                    iterTime = iter(timeElements)
                    next(iterTime)
                    for timeElement in iterTime:
                        line = line + "             " + timeElement.toxml().replace('Time','Value')+"\n"
            # remove extra white space from lines
            line = line[3:]
            layer_output = layer_output + line
        layer_xml.writelines(layer_output)
        
        # special case, add additional tilematrixsets from existing file and then remove
        existing_layer_xml_filename = wmts_mrf_filename.replace('.mrf','.xml').replace("_"+tilematrixset,'')
        if tilematrixset in wmts_mrf_filename:
            try:
                # Open GetCapabilities.
                existing_layer_xml=open(existing_layer_xml_filename, 'r+')
                lines = existing_layer_xml.readlines()
                os.remove(existing_layer_xml_filename)
                for idx in range(0, len(lines)):
                    if '<TileMatrixSet>' in lines[idx]:
                        lines[idx] = lines[idx] + tilematrixset_line
                layer_xml.seek(0)
                layer_xml.writelines(lines)
                existing_layer_xml.close()
            except:
                mssg=str().join(['Cannot read existing layer XML file:  ', existing_layer_xml_filename])
                log_sig_err(mssg, sigevent_url)
        
        # close new file        
        layer_xml.close()

    # create TWMS layer metadata for GetCapabilities
    if no_twms == False:
        try:
            # Open layer XML file
            layer_xml=open(twms_mrf_filename.replace('.mrf','_gc.xml'), 'w+')
        except IOError:
            mssg=str().join(['Cannot read layer XML file:  ', 
                             twms_mrf_filename.replace('.mrf','_gc.xml')])
            log_sig_exit('ERROR', mssg, sigevent_url)
    
        twms_layer_template = """    <Layer queryable=\"0\">
      <Name>$Identifier</Name>
      <Title xml:lang=\"en\">$Title</Title>
      <Abstract xml:lang=\"en\">$Abstract</Abstract>
      <LatLonBoundingBox minx=\"$minx\" miny=\"$miny\" maxx=\"$maxx\" maxy=\"$maxy\"/>
      <Style>
        <Name>default</Name> <Title xml:lang=\"en\">(default) Default style</Title>
      </Style>
      <ScaleHint min=\"10\" max=\"100\"/> <MinScaleDenominator>100</MinScaleDenominator>
      </Layer>"""
    
        layer_output = ""
        lines = twms_layer_template.splitlines(True)
        for line in lines:
            # replace lines in template
            if '</Layer>' in line:
                line = ' '+line+'\n'  
            if '$Identifier' in line:
                line = line.replace("$Identifier",identifier)              
            if '$Title' in line:
                line = line.replace("$Title",title)
            if '$Abstract' in line:
                line = line.replace("$Abstract", abstract)
            if '$minx' in line:
                line = line.replace("$minx",projection.lowercorner[0])
            if '$miny' in line:
                line = line.replace("$miny",projection.lowercorner[1])
            if '$maxx' in line:
                line = line.replace("$maxx",projection.uppercorner[0])
            if '$maxy' in line:
                line = line.replace("$maxy",projection.uppercorner[1])
            layer_output = layer_output + line
        layer_xml.writelines(layer_output)
        layer_xml.close()
        
    # create TWMS layer metadata for GetTileService
    if no_twms == False:
        try:
            # Open layer XML file
            layer_xml=open(twms_mrf_filename.replace('.mrf','_gts.xml'), 'w+')
        except IOError:
            mssg=str().join(['Cannot read layer XML file:  ', 
                             twms_mrf_filename.replace('.mrf','_gts.xml')])
            log_sig_exit('ERROR', mssg, sigevent_url)
    
        twms_layer_template = """<TiledGroup>
    <Name>$TiledGroupName</Name>
    <Title xml:lang=\"en\">$Title</Title>
    <Abstract xml:lang=\"en\">$Abstract</Abstract>
    <Projection>$Projection</Projection>
    <Pad>0</Pad>
    <Bands>$Bands</Bands>
    <BoundingBox minx=\"$minx\" miny=\"$miny\" maxx=\"$maxx\" maxy=\"$maxy\" />
    <Key>\${time}</Key>
$Patterns</TiledGroup>"""
    
        layer_output = ""
        lines = twms_layer_template.splitlines(True)
        for line in lines:
            # replace lines in template 
            if '</TiledGroup>' in line:
                line = ' '+line+'\n'              
            if '$TiledGroupName' in line:
                line = line.replace("$TiledGroupName",tiledGroupName) 
            if '$Title' in line:
                line = line.replace("$Title",title)
            if '$Abstract' in line:
                line = line.replace("$Abstract",abstract)
            if '$Projection' in line:
                line = line.replace("$Projection",projection.wkt)
            if '$Bands' in line:
                line = line.replace("$Bands",bands)
            if '$minx' in line:
                line = line.replace("$minx",projection.lowercorner[0])
            if '$miny' in line:
                line = line.replace("$miny",projection.lowercorner[1])
            if '$maxx' in line:
                line = line.replace("$maxx",projection.uppercorner[0])
            if '$maxy' in line:
                line = line.replace("$maxy",projection.uppercorner[1])
            if '$Patterns' in line:
                patterns = ""
                cmd = depth + '/oe_create_cache_config -p ' + twms_mrf_filename
                try:
                    print '\nRunning command: ' + cmd
                    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    process.wait()
                    for output in process.stdout:
                        patterns = patterns + output
                except:
                    log_sig_err("Error running command " + cmd, sigevent_url)
                line = line.replace("$Patterns",patterns)
            layer_output = layer_output + line
        layer_xml.writelines(layer_output)
        layer_xml.close()                
        
    # Create mapfile (if specified by user)
    if create_mapfile == True:
        if environment.mapfileConfigBasename != None:
            mapfileConfigPrefix = environment.mapfileConfigLocation + environment.mapfileConfigBasename
        else:
            mapfileConfigPrefix = environment.mapfileConfigLocation + projection.id.replace(':','')
        mapfileLocation = add_trailing_slash(os.path.dirname(environment.mapfile))
        mapfileBasename = os.path.basename(environment.mapfile)

        try:
            os.makedirs(mapfileLocation)
        except OSError:
            if not os.path.isdir(mapfileLocation):
                raise Exception("Can't create Mapserver file directory: " + mapfileLocation)
                break
        try:
            with open(mapfileLocation + mapfileBasename,'a+') as mapfile:
                if len(mapfile.read()) == 0:
                    try:
                        with open(mapfileConfigPrefix + '.header', 'r') as header:
                            mapfile.write(header.read())
                            print "\nCreating mapfile: " + mapfileLocation + mapfileBasename
                    except IOError:
                        raise log_sig_err("Mapfile doesn't exist and configuration header " + mapfileConfigPrefix + '.header' + " not found. Writing mapfile layers without header.")
                else:
                    print "\nUpdating mapfile: " + mapfileLocation + mapfileBasename

                # Check for duplicates - run check over and over until current layer is wiped from existing mapfile
                layerInMapfile = True
                while layerInMapfile == True:
                    layerInMapfile = delete_mapfile_layer(mapfile,identifier)

                # Initialize validation values
                timeDirPattern = "%TIME%"      
                timeParamRegex = "'^[0-9]{7}$'" if not subdaily else "'^[0-9]{13}$'"
                yearDirPattern = "%PRODUCTYEAR%"
                yearDirRegex   = "'^[0-9]{4}$'"

                minx = projection.lowercorner[0]
                miny = projection.lowercorner[1]
                maxx = projection.uppercorner[0]
                maxy = projection.uppercorner[1]

                # Start writing at the last END tag in the file
                mapfile.seek(0)
                readPosition = 0
                for line in reversed(mapfile.readlines()):
                    readPosition += len(line)
                    if line.lower().strip() == "end":
                        mapfile.seek(-readPosition,2)
                        mapfile.truncate()
                        break
                    readPosition+=len(line)

                # Write Mapfile layer fields
                mapfile.write("\n")
                mapfile.write("LAYER\n")
                mapfile.write("\tNAME\t\"" + identifier + "\"\n")
                mapfile.write("\tTYPE\tRASTER\n")
                mapfile.write("\tSTATUS\tON\n")
                mapfile.write("\tVALIDATION\n")
                if not static:
                    mapfile.write("\t\tTIME\t\t\t" + timeParamRegex + "\n")
                if not static and year:
                    mapfile.write("\t\tPRODUCTYEAR\t\t" + yearDirRegex + "\n")
                mapfile.write("\tEND\n")
                mapfile.write("\tMETADATA\n")
                if not static:
                    mapfile.write("\t\t\"default_TIME\"\t\t\"" + "TTTTTTT" + ("TTTTTT" if subdaily else "") + "\"\n")
                if not static and year:
                    mapfile.write("\t\t\"default_PRODUCTYEAR\"\t\"" + "YYYY" + "\"\n")
                mapfile.write("\t\t\"wms_title\"\t\t\"" + identifier + "\"\n")
                mapfile.write("\t\t\"wms_extent\"\t\t\"" + minx + " " + miny + " " + maxx + " " + maxy + "\"\n")
                mapfile.write("\tEND\n")
                if not static and year:
                    mapfile.write("\tDATA\t\"" + archiveLocation + "/" + yearDirPattern + "/" + fileNamePrefix + timeDirPattern + "_.mrf\"\n")
                elif not static and not year:
                    mapfile.write("\tDATA\t\"" + archiveLocation + "/" + fileNamePrefix + timeDirPattern + "_.mrf\"\n")
                else:
                    mapfile.write("\tDATA\t\"" + archiveLocation + "/" + fileNamePrefix + ".mrf\"\n")
                mapfile.write("\tPROJECTION\n")
                mapfile.write("\t\t\"init=" + projection.id.lower() + "\"\n")
                mapfile.write("\tEND\n")
                mapfile.write("END\n")
                mapfile.write("END\n")

        except IOError:
            raise Exception("Can't open or create mapfile: " + mapfileLocation + mapfileBasename)

# run scripts

if no_twms == False:
    for key, twms_endpoint in twms_endpoints.iteritems():
        #twms
        print "\nRunning commands for endpoint: " + twms_endpoint.path
        cmd = depth + '/oe_create_cache_config -cbd '+ twms_endpoint.path + " " + twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.config'
        run_command(cmd, sigevent_url)
        cmd = depth + '/oe_create_cache_config -cxd '+ twms_endpoint.path + " " + twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.xml'
        run_command(cmd, sigevent_url)
        if no_cache == False:
            if twms_endpoint.cacheConfigLocation:
                print '\nCopying: ' + twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.config' + ' -> ' + twms_endpoint.cacheConfigLocation+'/' + twms_endpoint.cacheConfigBasename + '.config'
                shutil.copyfile(twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.config', twms_endpoint.cacheConfigLocation+'/' + twms_endpoint.cacheConfigBasename + '.config')
                print '\nCopying: ' + twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.xml' + ' -> ' + twms_endpoint.cacheConfigLocation+'/' + twms_endpoint.cacheConfigBasename + '.xml'
                shutil.copyfile(twms_endpoint.path+'/' + twms_endpoint.cacheConfigBasename + '.xml', twms_endpoint.cacheConfigLocation+'/' + twms_endpoint.cacheConfigBasename + '.xml')
        if no_xml == False:
            if twms_endpoint.getCapabilities:
                # Add layer metadata to getCapabilities
                layer_xml = ""
                for xml_file in sorted(os.listdir(twms_endpoint.path), key=lambda s: s.lower()):
                    if xml_file.endswith("_gc.xml") and xml_file != "getCapabilities.xml":
                        layer_xml = layer_xml + open(twms_endpoint.path+'/'+str(xml_file), 'r').read()
                getCapabilities_file = twms_endpoint.path+'/getCapabilities.xml'
                getCapabilities_base = open(getCapabilities_file, 'r+')
                gc_lines = getCapabilities_base.readlines()
                for idx in range(0, len(gc_lines)):
                    if "</Layer>" in gc_lines[idx]:
                        gc_lines[idx] = layer_xml + gc_lines[idx]
                        print '\nAdding layers to TWMS GetCapabilities'
                    getCapabilities_base.seek(0)
                    getCapabilities_base.truncate()
                    getCapabilities_base.writelines(gc_lines)        
                getCapabilities_base.close()
                
                print '\nCopying: ' + twms_endpoint.path+'/getCapabilities.xml' + ' -> ' + twms_endpoint.getCapabilities+'/getCapabilities.xml'
                shutil.copyfile(twms_endpoint.path+'/getCapabilities.xml', twms_endpoint.getCapabilities+'/getCapabilities.xml')
                
            if twms_endpoint.getTileService:
                # Add layer metadata to getTileService
                layer_xml = ""
                for xml_file in sorted(os.listdir(twms_endpoint.path), key=lambda s: s.lower()):
                    if xml_file.endswith("_gts.xml") and xml_file != "getTileService.xml":
                        layer_xml = layer_xml + open(twms_endpoint.path+'/'+str(xml_file), 'r').read()
                getTileService_file = twms_endpoint.path+'/getTileService.xml'
                getTileService_base = open(getTileService_file, 'r+')
                gc_lines = getTileService_base.readlines()
                for idx in range(0, len(gc_lines)):
                    if "</TiledPatterns>" in gc_lines[idx]:
                        gc_lines[idx] = layer_xml + gc_lines[idx]
                        print '\nAdding layers to TWMS GetTileService'
                    getTileService_base.seek(0)
                    getTileService_base.truncate()
                    getTileService_base.writelines(gc_lines)        
                getTileService_base.close()                
                print '\nCopying: ' + twms_endpoint.path+'/getTileService.xml' + ' -> ' + twms_endpoint.getTileService+'/getTileService.xml'
                shutil.copyfile(twms_endpoint.path+'/getTileService.xml', twms_endpoint.getTileService+'/getTileService.xml')

if no_wmts == False:
    for key, wmts_endpoint in wmts_endpoints.iteritems():
        #wmts
        print "\nRunning commands for endpoint: " + wmts_endpoint.path
        cmd = depth + '/oe_create_cache_config -cbd '+ wmts_endpoint.path + " " + wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.config'
        run_command(cmd, sigevent_url)
        cmd = depth + '/oe_create_cache_config -cxd '+ wmts_endpoint.path + " " + wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.xml'
        run_command(cmd, sigevent_url)
        if no_cache == False:
            if wmts_endpoint.cacheConfigLocation:
                print '\nCopying: ' + wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.config' + ' -> ' + wmts_endpoint.cacheConfigLocation+'/' + wmts_endpoint.cacheConfigBasename + '.config'
                shutil.copyfile(wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.config', wmts_endpoint.cacheConfigLocation+'/' + wmts_endpoint.cacheConfigBasename + '.config')
                print '\nCopying: ' + wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.xml' + ' -> ' + wmts_endpoint.cacheConfigLocation+'/' + wmts_endpoint.cacheConfigBasename + '.xml'
                shutil.copyfile(wmts_endpoint.path+'/' + wmts_endpoint.cacheConfigBasename + '.xml', wmts_endpoint.cacheConfigLocation+'/' + wmts_endpoint.cacheConfigBasename + '.xml')
        if no_xml == False:
            if wmts_endpoint.getCapabilities:
                # Add layer metadata to getCapabilities
                layer_xml = ""
                for xml_file in sorted(os.listdir(wmts_endpoint.path), key=lambda s: s.lower()):
                    if xml_file.endswith(".xml") and xml_file != "getCapabilities.xml" and (xml_file.startswith("cache")==False):
                        layer_xml = layer_xml + open(wmts_endpoint.path+'/'+str(xml_file), 'r').read()
                getCapabilities_file = wmts_endpoint.path+'/getCapabilities.xml'
                getCapabilities_base = open(getCapabilities_file, 'r+')
                gc_lines = getCapabilities_base.readlines()
                for idx in range(0, len(gc_lines)):
                    if "<Contents>" in gc_lines[idx]:
                        gc_lines[idx] = gc_lines[idx] + layer_xml
                        print '\nAdding layers to WMTS GetCapabilities'
                    if "</Contents>" in gc_lines[idx] and " </TileMatrixSet>" not in gc_lines[idx-1]:
                        gc_lines[idx] = wmts_endpoint.projection.tilematrixset_xml[2:] + '\n' + gc_lines[idx]
                        print "\nAdding TileMatrixSet to WMTS GetCapabilities"
                    getCapabilities_base.seek(0)
                    getCapabilities_base.truncate()
                    getCapabilities_base.writelines(gc_lines)        
                getCapabilities_base.close()
                
                print '\nCopying: ' + getCapabilities_file + ' -> ' + wmts_endpoint.getCapabilities+'/getCapabilities.xml'
                shutil.copyfile(getCapabilities_file, wmts_endpoint.getCapabilities+'/getCapabilities.xml')
                if not os.path.exists(wmts_endpoint.getCapabilities +'1.0.0/'):
                    os.makedirs(wmts_endpoint.getCapabilities +'1.0.0')
                print '\nCopying: ' + getCapabilities_file + ' -> ' + wmts_endpoint.getCapabilities + '/1.0.0/WMTSCapabilities.xml'
                shutil.copyfile(getCapabilities_file, wmts_endpoint.getCapabilities + '/1.0.0/WMTSCapabilities.xml')

print '\n*** Layers have been configured successfully ***'
if no_cache == False:
    print '\nThe Apache server must be restarted to reload the cache configurations\n'

if restart==True:
    cmd = 'sudo apachectl stop'
    try:
        run_command(cmd, sigevent_url)
    except Exception, e:
        log_sig_err(str(e), sigevent_url)
    cmd = 'sleep 3'
    run_command(cmd, sigevent_url)
    cmd = 'sudo apachectl start'
    try:
        run_command(cmd, sigevent_url)
    except Exception, e:
        log_sig_err(str(e), sigevent_url)
    print '\nThe Apache server was restarted successfully'

completion = "The OnEarth Layer Configurator completed "
if len(warnings) > 0:
    message = completion + "with warnings."
    print "Warnings:"
    for warning in warnings:
        print warning
if len(errors) > 0:
    message = completion + "with errors."
    print "\nErrors:"
    for error in errors:
        print error
if len(warnings) == 0 and len(errors) == 0:
    message = completion + "successully."
print ""
message = message + " " + ("Cache configurations created.", "No cache configurations.")[no_cache] + " " + ("Server XML created","No server XML")[no_xml] + "." + " " + ("Apache not restarted","Apache restarted")[restart] + "." + " " + ("Legends not generated","Legends generated")[legend] + "." + " " + ("Archive links not generated","Archive links generated")[links] + ". " + ("Mapfiles not configured","Mapfiles configured")[create_mapfile] + "." + " Warnings: " + str(len(warnings)) + ". Errors: " + str(len(errors)) + "." 

try:
    sigevent('INFO', asctime() + " " + message, sigevent_url)
except urllib2.URLError:
    print 'sigevent service is unavailable'
print 'Exiting oe_configure_layer.'

if len(errors) > 0:
    sys.exit(len(errors))
else:
    sys.exit(0)
    


