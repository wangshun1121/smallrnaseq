#!/usr/bin/env python

"""
    Module for smallrnaseq config
    Created Jan 2017
    Copyright (C) Damien Farrell

    This program is free software; you can redistribute it and/or
    modify it under the terms of the GNU General Public License
    as published by the Free Software Foundation; either version 3
    of the License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

from __future__ import absolute_import, print_function
import sys, os, string, time
import types, re, subprocess, glob, shutil
import pandas as pd
import configparser

path = os.path.dirname(os.path.abspath(__file__))
datadir = os.path.join(path, 'data')


baseoptions = {'base': [('filename',''),('path',''),('filetype','fastq'),
                    ('indexes',''),('index_path','indexes'),
                    ('output','smrna_results'),
                    ('aligner','bowtie'),
                    ('bowtie_params','-v 1 --best'),
                    ('ref_genome',''),('species','hsa'),
                    ('mirbase',0),('pad5',3),('pad3',5)
                    ]}

def write_default_config(conffile='default.conf', defaults={}):
    """Write a default config file"""

    if not os.path.exists(conffile):
        cp = create_config_parser_from_dict(defaults, ['base'])
        cp.write(open(conffile,'w'))
        print ('wrote config file %s' %conffile)
    return conffile

def create_config_parser_from_dict(data, sections, **kwargs):
    """Helper method to create a ConfigParser from a dict and/or keywords"""

    cp = configparser.ConfigParser()
    for s in sections:
        cp.add_section(s)
        if not data.has_key(s):
            continue
        for i in data[s]:
            name,val = i
            cp.set(s, name, val)
    #use kwargs to create specific settings in the appropriate section
    for s in cp.sections():
        opts = cp.options(s)
        for k in kwargs:
            if k in opts:
                cp.set(s, k, kwargs[k])
    return cp

def parse_config(conffile=None):
    """Parse a configparser file"""

    f = open(conffile,'r')
    cp = configparser.ConfigParser()
    try:
        cp.read(conffile)
    except Exception as e:
        print ('failed to read config file! check format')
        print ('Error returned:', e)
        return
    f.close()
    return cp

def get_options(cp):
    """Makes sure boolean opts are parsed"""

    options = cp._sections['base']
    for o in options:
        try:
            options[o] = cp.getboolean('base', o)
        except:
            pass
    return options

def print_options(options):
    for key in options:
        print (key, ':', options[key])
    print ()