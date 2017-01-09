#!/usr/bin/env python

"""
    methods for differential expression analysis
    Created Dec 2016
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
import sys, os, string, types, re, csv
import shutil, glob
import itertools
import subprocess
import numpy as np
import pandas as pd

def get_columns_by_label(labels, samplecol, filters=[], querystr=None):
    """Get sample columns according to a condition from a set of labels
    Args:
        labels: dataframe matching sample labels to conditions/factors
        samplecol: name of column holding sample/file names
        filters: tuples containing column/.value pairs to filter on
        querystr: optional string instead of tuple filters
        (see pandas.DataFrame.query documentation)
    """

    if querystr == None:
        q=[]
        for f in filters:
            if type(f[1]) is str:
                s = "%s=='%s'" %(f[0],f[1])
            else:
                s = "%s==%s" %(f[0],f[1])
            q.append(s)
        querystr = ' & '.join(q)
    print (querystr)
    x = labels.query(querystr)
    cols = x[samplecol]
    return list(cols)

def run_edgeR(countsfile=None, data=None, cutoff=1.5):
    """Run edgeR from R script"""

    if data is not None:
        countsfile = 'de_counts.csv'
        data = data.to_csv(countsfile)
    path = os.path.dirname(os.path.abspath(__file__)) #path to module
    descript = os.path.join(path, 'DEanalysis.R')
    cmd = 'Rscript %s %s' %(descript, countsfile)
    result = subprocess.check_output(cmd, shell=True, executable='/bin/bash')
    print (result)
    #read result back in
    de = pd.read_csv('de_output.csv')
    de.rename(columns={'Unnamed: 0':'name'}, inplace=True)
    de = de[(de.FDR<0.05) & ((de.logFC>cutoff) | (de.logFC<-cutoff))]
    return de

def runEdgeRGLM(countsfile, cutoff=1.5):
    """Run edgeR from R script"""

    cmd = 'Rscript ~/python/sandbox/mirnaseq/GLMDEanalysis.R %s' %countsfile
    print (cmd)
    result = subprocess.check_output(cmd, shell=True, executable='/bin/bash')
    print (result)
    #read result back in
    #de = pd.read_csv('de_output.csv')
    #de.rename(columns={'Unnamed: 0':'name'}, inplace=True)
    #de = de[(de.FDR<0.05) & ((de.logFC>cutoff) | (de.logFC<-cutoff))]
    return

def rpyEdgeR(data, groups, sizes, genes):
    """Run edgeR analysis - from http://bcbio.wordpress.com/ """

    import rpy2.robjects as robjects
    import rpy2.robjects.numpy2ri
    rpy2.robjects.numpy2ri.activate()
    robjects.r('''library(edgeR)''')
    params = {'group' : groups, 'lib.size' : sizes}
    print (params)
    d = robjects.r.DGEList(counts=data, **params)
    print (d)
    robjects.r.calcNormFactors(d)
    robjects.r.estimateCommonDisp(d)
    robjects.r.estimateTagwiseDisp(d)
    robjects.r.exactTest(d)

    #ms = robjects.r.deDGE(dgelist, doPoisson=True)
    #tags = robjects.r.topTags(ms, pair=groups, n=len(genes))
    indexes = [int(t) - 1 for t in tags.rownames()]
    pvals = list(tags.r['adj.P.Val'][0])
    return
