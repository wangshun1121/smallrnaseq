#!/usr/bin/env python

"""
    Novel miRNA prediction
    Created Feb 2017
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
import sys, os, string, types
import shutil, glob, collections
import itertools
from itertools import islice
import numpy as np
import pandas as pd
from . import base, utils

path = os.path.dirname(os.path.abspath(__file__))
datadir = os.path.join(path, 'data')
CLASSIFIER = None

def get_triplets(seq, struct):
    """triplet elements"""

    tr=['(((', '((.', '(..', '(.(', '.((', '.(.', '..(' , '...']
    nuc = ['A','G','T','C']
    d={}
    for i in nuc:
        for j in tr:
            d[i+j]=0
    struct=struct.replace(')','(')
    l = len(seq)-len(seq)%3
    for i in range(0,l,3):
        n = seq[i+1]+struct[i:i+3]
        if n in d:
            d[n]+=1
    return d

def get_biggest_stem(bg):
    biggest_stem = (-1, 'x')
    for s in bg.stem_iterator():
        if bg.stem_length(s) > biggest_stem[0]:
            biggest_stem = (bg.stem_length(s), s)
    return biggest_stem

def get_stem_pairs(bg):
    pairs=[]
    for s in bg.stem_iterator():
        for p in bg.stem_bp_iterator(s):
            pairs.append( (bg.seq[p[0]-1],bg.seq[p[1]-1]) )
    return pairs

def get_stem_matches(bg):
    """Find rna stem mismatches"""

    pairs = get_stem_pairs(bg)
    wc = {'G':'C','C':'G','T':'A','A':'T'}
    matches = [True if i[1]==wc[i[0]] else False for i in pairs]
    return matches

def build_rna_features(seq, mature=None):
    """Get features for mirna sequence"""

    from Bio.SeqUtils import GC
    import forgi.graph.bulge_graph as cgb

    struct,sc = utils.rnafold(seq)

    feats = {}
    #feats['reads'] = reads.reads.sum()
    feats['length'] = len(seq)
    feats['mfe'] = round(sc/len(seq),3)
    #print seq
    #print struct

    bg = cgb.BulgeGraph()
    bg.from_dotbracket(struct)
    bg.seq = seq
    try:
        h0seq = bg.get_define_seq_str('h0')[0]
        feats['loops'] = len(list(bg.hloop_iterator()))
        feats['loop_length'] = bg.get_bulge_dimensions('h0')[0]
    except:
        h0seq=''
        feats['loops'] = 0
        feats['loop_length'] = 0
    feats['loop_gc']= GC(h0seq)
    feats['stem_length'] = len(get_stem_pairs(bg))
    feats['longest_stem'] = get_biggest_stem(bg)[0]
    bulges = [bg.get_bulge_dimensions(i) for i in bg.iloop_iterator()]
    feats['bulges'] = len(bulges)
    try:
        feats['longest_bulge'] =  max(max(zip(*bulges)))
    except:
        feats['longest_bulge'] = 0
    bulgematches = [True if i[0]==i[1] else False for i in bulges]
    feats['bulges_symmetric'] = bulgematches.count(True)
    feats['bulges_asymmetric'] = bulgematches.count(False)
    sm = get_stem_matches(bg)
    feats['stem_mismatches'] = sm.count(False)

    if mature == None:
        #mature should be given - place holder for code to guess it later
        start = np.random.randint(1,len(sm)-20)
        end = start+22
    else:
        start = utils.find_subseq(seq, mature)
        end = start+len(mature)
        #print start, end
    feats['mature_mismatches'] = sm[start:end].count(False)

    tr = get_triplets(seq, struct)
    feats.update(tr)
    return feats

def get_star(seq, mature, struct=None):
    """Estimate the star sequence from a given mature and precursor."""

    import forgi.graph.bulge_graph as cgb
    start = utils.find_subseq(seq, mature)+1
    end = start + len(mature)
    if struct == None:
        struct,sc = utils.rnafold(seq)
    bg = cgb.BulgeGraph()
    bg.from_dotbracket(struct)
    bg.seq = seq
    stempairs = []
    for s in bg.sorted_stem_iterator():
        stempairs.extend( list(bg.stem_bp_iterator(s)) )
    m = zip(*stempairs)
    stem1 = list(m[0])
    stem2 = list(m[1])
    matidx = range(start, end)
    #print stem1
    #print start, end
    #is mature on 5' or 3' end?
    if start < max(stem1):
        print ('5p')
        matidx = [i for i in matidx if i in stem1]
        staridx = [i[1] for i in stempairs if i[0] in matidx]
        gaps = [abs(t-s) for s, t in zip(staridx, staridx[1:])]
        for i in range(len(gaps)):
            if gaps[i]>3 and i>=len(gaps)-5:
                staridx = staridx[:i+1]
        offset = len(matidx)-len(staridx)+2
        starseq = seq[staridx[-1]:staridx[0]+offset]
    else:
        print ('3p')
        matidx = [i for i in matidx if i in stem2]
        staridx = [i[0] for i in stempairs if i[1] in matidx]
        offset = len(matidx)-len(staridx)+2
        #print matidx
        #print staridx
        starseq = seq[staridx[0]+offset:staridx[-1]]

    #print matidx
    #print staridx
    #print mature
    #print starseq
    return starseq

def get_positives(species='hsa'):
    """Get known mirbase hairpins for training precursor classifier. """

    reload(base)
    mirs = base.get_mirbase(species)
    feats=[]
    for i,row in mirs.iterrows():
        f = build_rna_features(row.precursor, row.mature1_seq)
        f['seq'] = row.precursor
        f['mature'] = row.mature1_seq
        f['star'] = row.mature2_seq
        feats.append(f)

    result = pd.DataFrame(feats)
    result.to_csv('known_mirna_features.csv', index=False)
    return result

def get_negatives():
    """negative pseudo mirna set"""

    cds = utils.fasta_to_dataframe('../genomes/human/Homo_sapiens.GRCh38.cds.all.fa')
    cds = cds.drop_duplicates('sequence')
    cds = cds[cds.sequence.str.len()>50]

    def split_seqs(r):
        #maxlen = int(np.random.normal(81,17))
        maxlen = int(np.random.gamma(9.5,9))
        #print len(r.sequence), maxlen
        s = [r.sequence[ind:ind+maxlen] for ind in range(0, len(r.sequence), maxlen)]
        return pd.Series(s)

    seqs = cds[:2000].apply(split_seqs,1).stack().reset_index(drop=True)
    seqs = seqs[seqs.str.len()>50]
    seqs = seqs[-seqs.str.contains('N')]
    result=[]
    for seq in seqs:
        ms = int(np.random.randint(2,5))
        f = build_rna_features(seq, mature=seq[ms:ms+22])
        f['seq'] = seq
        result.append(f)
    result = pd.DataFrame(result)
    result = result[(result.loops==1) & (result.mfe*result.length<=-15) & (result.stem_length>18)]
    result.to_csv('negative_mirna_features.csv', index=False)
    return result

def get_training_data(known=None, neg=None):
    """Get training data for classifier
        Args:
            known: known precursor data, a dataframe
            neg: negatives
        Returns:
            a dataframe with all features and a set of true/false values
    """

    if known is None:
        known = pd.read_csv(os.path.join(datadir, 'training_positives.csv'))
        #known = get_positives()
    if neg is None:
        neg = pd.read_csv(os.path.join(datadir, 'training_negatives.csv'))
    print (len(known), len(neg))
    known['target'] = 1
    neg['target'] = 0
    data = pd.concat([known,neg]).reset_index(drop=True)
    data = data.sample(frac=1)
    y = data.target
    data = data.drop('target',1)
    X = data.select_dtypes(['float','int'])
    #X = sklearn.preprocessing.scale(X)
    return X, y

def precursor_classifier(known=None, neg=None, kind='classifier'):
    """Get a miRNA precursor classifier using given training data.
       Args:
        X: numpy array/dataframe with features
        y: true/false values matching feature rows, 1's and 0's
        kind: use 'classifier' or 'regressor' random forest
       Returns:
        random forest classifier fitted to X,y
    """

    X, y = get_training_data(known, neg)
    from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor)
    if kind == 'classifier':
        rf = RandomForestClassifier()
    else:
        rf = RandomForestRegressor()
    #print ('fitting..')
    rf.fit(X,y)
    return rf

def test_classifier(known=None, neg=None):

    from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor)
    X, y = get_training_data(known, neg)
    rf = RandomForestClassifier()
    rf.fit(X,y)
    from sklearn.model_selection import train_test_split,cross_val_score
    #X_train, X_test, y_train, y_test = train_test_split(X, y, train_size=0.4)
    #rf = RandomForestRegressor()
    scores = cross_val_score(rf, X, y, cv=5, scoring='roc_auc')
    print (scores)
    #print sklearn.metrics.classification_report(y_test, y_score)
    names = X.columns
    importances = rf.feature_importances_
    indices = np.argsort(importances)[::-1]
    print ('feature ranking:')
    for f in range(X.shape[1])[:10]:
        print("%d. %s (%f)" % (f + 1, names[indices[f]], importances[indices[f]]))
    '''a = neg[:2000].drop('target',1)
    a['score'] = score_features(a, rf)
    b = known[:2000].drop('target',1)
    b['score'] = score_features(b, rf)
    x = a.score.value_counts().sort_index()
    y = b.score.value_counts().sort_index()
    res = pd.DataFrame({'neg':x,'pos':y})
    res.plot(kind='bar')
    '''
    return

def score_features(data, rf):
    """Score a set of features"""

    X = data.select_dtypes(['float','int'])
    #data['score'] = rf.predict(X)
    return rf.predict(X)

def build_cluster_trees(alnmt, cluster_distance=10, min_size=2, key='read_id'):
    """Build cluster tree of reads from a dataframe of locations e.g from
        a set of aligned reads from a sam file.
    Args:
        cluster_distance: Distance in basepairs for two reads to be in the same cluster;
       for instance 20 would group all reads with 20bp of each other
        min_size: Number of reads necessary for a group to be considered a cluster;
       2 returns all groups with 2 or more overlapping reads
    Returns:
        dict of ClusterTrees per chromosome
    """

    import collections
    from bx.intervals.cluster import ClusterTree
    cluster_trees = collections.defaultdict(lambda:
            ClusterTree(cluster_distance, min_size))
    for i, row in alnmt.iterrows():
        chrom = row['name']
        #print chrom, row.read_id, row.start, row.end
        cluster_trees[chrom].insert(row.start, row.end, row[key])
    return dict(cluster_trees)

def get_read_clusters(reads):
    """Get clusters of reads from a dataframe with alignment fields
      i.e. from a sam file"""

    #get clusters of reads and store by read_id
    clustertrees = build_cluster_trees(reads, cluster_distance=10, min_size=2)
    reads.set_index('read_id',inplace=True)

    groups = []
    i=1
    for chrom, cltree in clustertrees.items():
        #print (chrom)
        for start, end, ids in cltree.getregions():
            #print (start, end, ids)
            c = reads.ix[ids].copy()
            c['cl_start'] = start
            c['cl_end'] = end
            c['cluster'] = i
            groups.append(c)
            #print (c)
            i+=1
    df = pd.concat(groups)
    return df

def find_precursor(ref_fasta, cluster, cluster2=None, step=5, score_cutoff=1):
    """Find the most likely precursor from a genomic sequence and
       one or two mapped read clusters.
       Args:
           ref_fasta: genomic reference sequence
           cluster: reads in a cluster, a dataframe
           cluster2: a pair to the first cluster, optional
           step: increment for extending precursors
           score_cutoff: if using non-classifier, optional
       Returns:
           the top precursor
    """

    rf = CLASSIFIER
    if rf == None:
        print ('no classifier defined, set novel.CLASSIFIER variable')
        return
    x = cluster.iloc[0]
    maturecounts = reads1 = cluster.reads.sum()
    mature = x.seq
    star = None
    starcounts = 0
    #dtermine mature/star if two clusters present
    if cluster2 is not None:
        reads2 = cluster2.reads.sum()
        y = cluster2.iloc[0]
        if reads2>reads1:
            mature = y.seq
            maturecounts = reads2
            star = x.seq
            starcount = reads1

    print (mature, star, maturecounts, starcounts)
    #check mature for non templated additions?

    chrom = x['name']
    strand = x.strand
    loop = 15
    N = []
    #generate candidate precursors
    for i in range(1,45,step):
        #5' side
        start5 = x.start - i
        end5 = x.start + 2 * len(x.seq)-1 + loop + i
        coords = [chrom,start5,end5,strand]
        prseq = utils.sequence_from_coords(ref_fasta, coords)
        if prseq == None:
            continue
        N.append({'precursor':prseq, 'chrom':chrom,'start':start5,'end':end5,
                  'mature':x.seq,'strand':strand})
        #3' side
        start3 = x.start - (loop + len(x.seq) + i)
        end3 = x.end + i
        coords = [chrom,start3,end3,strand]
        prseq = utils.sequence_from_coords(ref_fasta, coords)
        if prseq == None:
            continue
        N.append({'precursor':prseq, 'chrom':chrom,'start':start3,'end':end3,
                  'mature':x.seq,'strand':strand})
    if len(N) == 0:
        return
    N = pd.DataFrame(N)
    #print (len(N))
    N['mature_reads'] = maturecounts
    N['star_reads'] = starcounts
    if cluster2 is not None:
        N['star'] = cluster2.iloc[0].seq
        #'check star for non templated additions?

    f = N.apply(lambda x: pd.Series(build_rna_features(x.precursor, x.mature)), 1)

    if CLASSIFIER == None:
        rf = get_default_classifier()
    N['score'] = score_features(f, rf)
    N['mfe'] = f.mfe
    #filter by feature
    N = N[(f.loops==1) & (f.stem_length>18) & (f.mfe*f.length<-15)]
    N = N[N.score>=score_cutoff]
    #print N
    N = N.sort_values('mfe')
    if len(N)>0:
        found = N.iloc[0]
        return found
    else:
        return

def find_mirnas(reads, ref_fasta, score_cutoff=.9):
    """Find novel miRNAs in reference mapped reads. Assumes we have already
        mapped to known miRNAs.
        Args:
            reads: unique aligned reads with counts in a dataframe
            ref_fasta: reference genome fasta file
            rf: precursor classifier, optional
    """

    global CLASSIFIER
    if CLASSIFIER == None:
        print ('getting default classifier')
        CLASSIFIER = precursor_classifier(kind='regressor')

    reads = reads[(reads.length<=25) & (reads.length>=18)]
    df = get_read_clusters(reads)
    clusts = df.groupby(['name','cluster','cl_start','cl_end','strand'])\
                            .agg({'reads':np.sum,'length':np.max})\
                            .reset_index()\
                            .rename(columns={'cl_start':'start','cl_end':'end'})
    print ('%s read clusters in %s unique reads' %(len(clusts),len(df)))

    #find pairs of read clusters - likely to be mature/star sequences
    clustpairs = build_cluster_trees(clusts, 120, min_size=2, key='cluster')

    def get_pairs(r):
        #get ids for corresponding pairs
        id = r.cluster
        pairs = clustpairs[r['name']].getregions()
        if len(pairs)>0 and id in pairs[0][2]:
            x = pairs[0][2]
            return x[0]
        return

    def get_coords(r):
        return r['chrom']+':'+str(r.start)+'..'+str(r.end)+':'+r.strand

    clusts['pair'] = clusts.apply(get_pairs, 1)
    print (clusts)

    n1 = []
    pairs = clusts.groupby('pair')
    print ('%s paired clusters found' %len(pairs.groups))
    for i,r in pairs:
        a,b = list(r.cluster)
        c1 = df[df.cluster==a]
        c2 = df[df.cluster==b]
        p = find_precursor(ref_fasta, c1, c2, step=7)
        if p is None:
            print ('no precursor predicted')
            continue
        n1.append(p)
    n1 = pd.DataFrame(n1)
    print
    n2 = []
    #guess precursors for single clusters
    singleclusts = clusts[clusts.pair.isnull()]
    print ()
    print ('checking %s single clusters' %len(singleclusts))
    for i,r in singleclusts.iterrows():
        c = df[df.cluster==r.cluster]
        p = find_precursor(ref_fasta, c, step=7, score_cutoff=score_cutoff)
        #print p
        if p is None:
            print ('no precursor predicted')
            continue
        #estimate star sequence
        p['star'] = get_star(p.precursor, p.mature)
        n2.append(p)
    n2 = pd.DataFrame(n2)

    novel = pd.concat([n1,n2])
    if len(novel) == 0:
        print ('no mirnas found!')
        return
    #get seed seq and mirbase matches
    novel['seed'] = novel.apply(lambda x: x.mature[2:8], 1)
    #get coords column
    novel['coords'] = novel.apply(get_coords,1)

    print ('found %s novel mirnas' %len(novel))
    return novel
