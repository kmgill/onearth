#!/bin/env python

# Copyright (c) 2002-2014, California Institute of Technology.
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
# oe_generate_legend.py
# The OnEarth Legend Generator.
#
#
# Global Imagery Browse Services
# NASA Jet Propulsion Laboratory
# 2014

import sys
import urllib
import xml.dom.minidom
from optparse import OptionParser
from matplotlib import pyplot
import matplotlib as mpl

toolName = "oe_generate_legend.py"
versionNumber = "v0.4"


class ColorMap:
    """ColorMap metadata"""
    
    def __init__(self, units, colormap_entries):
        self.units = units
        self.colormap_entries = colormap_entries
        
    def __repr__(self):
        if self.units != None:
            xml = '<ColorMap units="%s">' % (self.units)
        else:
            xml = '<ColorMap>'
        for colormap_entry in self.colormap_entries:
            xml = xml + '\n    ' + colormap_entry.__repr__()
        xml = xml + '\n</ColorMap>'
        return xml

    def __str__(self):
        return self.__repr__().encode(sys.stdout.encoding)


class ColorMapEntry:
    """ColorMapEntry values within a ColorMap"""
    
    def __init__(self, red, green, blue, transparent, source_value, value, label):
        self.red = int(red)
        self.green = int(green)
        self.blue = int(blue)
        self.transparent = transparent
        self.source_value = source_value
        self.value = value
        self.label = label
        self.color = [float(red)/255.0,float(green)/255.0,float(blue)/255.0]
        
    def __repr__(self):
        return '<ColorMapEntry rgb="%d,%d,%d" transparent="%s" sourceValue="%s" value="%s" label="%s"/>' % (self.red, self.green, self.blue, self.transparent, self.source_value, self.value, self.label)
    
    def __str__(self):
        return self.__repr__().encode(sys.stdout.encoding)
    

def parse_colormap(colormap_location):
    
    try:    
        print "Reading color map:", colormap_location
        colormap_file = open(colormap_location,'r')
        dom = xml.dom.minidom.parse(colormap_file)
        colormap_file.close()
    except IOError:
        print "Accessing URL", colormap_location
        dom = xml.dom.minidom.parse(urllib.urlopen(colormap_location))
        
    colormap_element = dom.getElementsByTagName("ColorMap")[0]
    try:
        units = colormap_element.attributes['units'].value
    except KeyError:
        units = None
    print "ColorMap units:", units
    
    colormap_entries = []
    colormapentry_elements = colormap_element.getElementsByTagName("ColorMapEntry")
    for colormapentry in colormapentry_elements:
        rgb = colormapentry.attributes['rgb'].value
        red, green, blue = rgb.split(',')
        value = colormapentry.attributes['value'].value
        try:
            transparent = True if colormapentry.attributes['transparent'].value.lower() == 'true' else False
        except KeyError:
            transparent = False
        try:
            source_value = colormapentry.attributes['sourceValue'].value
        except KeyError:
            source_value = value
        try:
            label = colormapentry.attributes['label'].value
        except KeyError:
            label = value
        
        colormap_entries.append(ColorMapEntry(red, green , blue, transparent, source_value, value, label))
    
    colormap = ColorMap(units, colormap_entries)
    print colormap
    
    return colormap


def generate_legend(colormap, output):
    
    fig = pyplot.figure(figsize=(3,1))
    ax = fig.add_axes([0.05, 0.60, 0.9, 0.15])
    
    bounds = []
    colors = []
    for colormap_entry in colormap.colormap_entries:
        bounds.append(float(colormap_entry.value.split(',')[0].replace('[','')))
        colors.append(colormap_entry.color)

    cmap = mpl.colors.ListedColormap(colors)
    
    norm = mpl.colors.BoundaryNorm(bounds, cmap.N)
    cb = mpl.colorbar.ColorbarBase(ax, cmap=cmap,
                                   norm=norm,
                                   orientation='horizontal')
    cb.set_label(colormap.units)
    
    fig.savefig(output, transparent=True, format='svg')

    print output + " generated successfully"
    

#-------------------------------------------------------------------------------

print toolName + ' ' + versionNumber + '\n'

usageText = toolName + " --colormap [file] --output [file]"

# Define command line options and args.
parser=OptionParser(usage=usageText, version=versionNumber)
parser.add_option('-c', '--colormap',
                  action='store', type='string', dest='colormap',
                  help='Full path or URL of colormap filename.')
parser.add_option('-o', '--output',
                  action='store', type='string', dest='output',
                  help='The full path of the output SVG file')
parser.add_option('-u', '--sigevent_url',
                  action='store', type='string', dest='sigevent_url',
                  default=
                  'http://localhost:8100/sigevent/events/create',
                  help='Default:  http://localhost:8100/sigevent/events/create')

# read command line args
(options, args) = parser.parse_args()

if options.colormap:
    colormap_location = options.colormap
else:
    print "colormap file must be specified...exiting"
    exit()
if options.output:
    output_location = options.output
else:
    print "output file must be specified...exiting"
    exit()
    
# parse colormap
try:
    colormap = parse_colormap(colormap_location)
except IOError,e:
    print str(e)
    exit()

# generate legend
try:
    generate_legend(colormap, output_location)
except IOError,e:
    print str(e)
    exit()