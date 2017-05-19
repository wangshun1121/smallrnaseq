#!/usr/bin/env python

"""
    smallrnaseq implementation of command line functionality
    Created November 2016
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
import sys, os, string, types, shutil, time
import glob
import pandas as pd
from smallrnaseq import config, base, analysis, utils, aligners, novel, plotting, de

class WorkFlow(object):
    """Class for implementing a rna/mirna workflow from a set of options"""
    def __init__(self, opts):
        for i in opts:
            self.__dict__[i] = opts[i]
        self.libraries = self.libraries.split(',')
        if '' in self.libraries:
            self.libraries.remove('')
        return

    def setup(self):
        """Setup main parameters"""

        if self.filenames != '':
            self.files = self.filenames.split(',')
        elif self.path != '':
            self.files = glob.glob(os.path.join(self.path,'*.fastq'))
            if len(self.files) == 0:
                print ('no fastq files found')
                return False
        else:
            print ('you should provide at least one file or folder')
            return False
        self.files = [str(f) for f in self.files]
        aligners.BOWTIE_INDEXES = aligners.SUBREAD_INDEXES = self.index_path
        if self.default_params != '':
            aligners.set_params(self.aligner, self.default_params)
        if not os.path.exists(self.index_path):
            print ('no such folder for indexes')
            return False
        if not os.path.exists(self.output):
            os.mkdir(self.output)
        #make sample ids to replace filenames
        if self.add_labels == True:
            #names = base.get_base_names(self.files)
            self.labels = base.assign_sample_ids(self.files,
                                  outfile=os.path.join(self.output, 'sample_labels.csv'))
        else:
            self.labels = None
        if self.ref_fasta != None:
            if not os.path.exists(self.ref_fasta):
                print ('WARNING ref fasta %s not found' %self.ref_fasta)
            self.ref_name = os.path.splitext(os.path.basename(self.ref_fasta))[0]
        else:
            self.ref_name = None
        self.get_aligner_params()
        self.temp_path = os.path.join(self.output,'temp')
        self.remove_output()
        print ('found %s input files' %len(self.files))
        return True

    def check_index(self, name):
        """check if an index present"""

        fname = os.path.join(self.index_path, name+'*.ebwt')
        print (fname)
        x = (glob.glob(fname))
        if len(x) == 0:
            return False
        else:
            return True

    def run(self):
        """Execute the workflow"""

        if self.mirna == 1:
            self.map_mirnas()
        else:
            self.map_libraries()
        if self.features != '':
            self.map_genomic_features()
        print ('intermediate files saved to %s' %self.temp_path)
        return

    def remove_output(self):
        """Remove previous output files"""

        if self.overwrite == True:
            print ('removing temp folder')
            if os.path.exists(self.temp_path):
                shutil.rmtree(self.temp_path)
        for ext in ['*.csv','*.png','*.html','*.fa']:
            utils.remove_files(self.output, ext)
        return

    def get_aligner_params(self):
        """Get aligner parameters from current options"""

        ap = self.aligner_params = {}
        for i in self.libraries:
            n=i.lower()
            if hasattr(self, n):
                ap[i] = self.__dict__[n]
        n = self.ref_name
        if n != None and hasattr(self, n):
            ap[n] = self.__dict__[n]
        #print (self.aligner_params)
        return

    def map_libraries(self):
        """Map to arbitrary rna sequence libraries"""

        out = self.output
        libraries = self.libraries
        if libraries == '' or len(libraries) == 0:
            print ('no libraries to map to')
            return

        #map to provided libraries
        print ('mapping to these libraries: %s' %libraries)
        res, counts = base.map_rnas(self.files, libraries, self.temp_path,
                                    aligner=self.aligner,
                                    samplelabels=self.labels,
                                    params=self.aligner_params)
        if res is None:
            print ('empty data returned. did alignments run?')
            return
        print ('results saved to rna_counts.csv')
        res.to_csv( os.path.join(out, 'rna_found.csv'),index=False)
        counts.to_csv( os.path.join(out, 'rna_counts.csv'), index=False )
        plot_results(res, out)
        return

    def map_mirnas(self):
        """Map miRNAs using mirbase with isomir counts and do novel prediction
           if a reference genome and index is provided"""

        out = self.output
        libraries = self.libraries
        temp = self.temp_path
        ref_name = self.ref_name
        mat_name = 'mirbase-%s' %self.species
        self.aligner_params[mat_name] = self.mirna_params

        if self.check_index(ref_name) == False:
            print ('no index for reference genome')
            ref_name = ''

        print ('mapping miRNAs..')
        res, counts = base.map_mirbase(self.files, outpath=temp, indexes=libraries,
                                       species=self.species, ref_genome=ref_name,
                                       pad5=self.pad5, pad3=self.pad3, aligner=self.aligner,
                                       samplelabels=self.labels,
                                       params=self.aligner_params)

        #seperate out mature counts and save
        matcounts = counts[counts.ref==mat_name]
        res.to_csv( os.path.join(out, 'results.csv'),index=False )
        res = res[res.ref!=ref_name]
        matcounts.to_csv( os.path.join(out, 'mirbase_mature_counts.csv'), index=False,
                            float_format='%.1f' )
        counts.to_csv( os.path.join(out, 'all_counts.csv'), index=False )
        plot_results(res, out)

        #isomir counting
        print ()
        print ('counting isomirs..')
        iso, isocounts = base.map_isomirs(self.files, temp, self.species,
                                          samplelabels=self.labels)
        isocounts.to_csv( os.path.join(out, 'isomir_counts.csv'), index=False, float_format='%.1f')

        #novel prediction
        if self.ref_fasta == '' or not os.path.exists(self.ref_fasta):
            print ('no reference genome file, skipping novel mirna step')
        elif ref_name == None:
            print ('no index for ref genome, required for novel mirna step')
        elif check_viennarna() == False:
            print ('Vienna RNA package not installed')
            print ('see https://www.tbi.univie.ac.at/RNA/')
        else:
            print ()
            print ('predicting novel mirnas..')
            start = time.time()
            #change map_rnas so it can use remaining files from previous run....?

            allreads = utils.combine_aligned_reads(temp, idx=ref_name)
            new,cl = novel.find_mirnas(allreads, self.ref_fasta, species=self.species,
                                       score_cutoff=float(self.score_cutoff),
                                       read_cutoff=int(self.read_cutoff))
            if self.strict == True:
                new = new[new.mature_check=='ok']
                print ('filtered %s' %len(new))
            if new is None or len(new) == 0:
                print ('could not find any novel mirnas at this score cutoff')
                return
            new.to_csv(os.path.join(out,'novel_mirna.csv'), index=False)

            #pad mature novel and write to fasta for counting
            novpad = base.get_mature_padded(new, idkey='mature_id', seqkey='mature')
            novpad = novpad.drop_duplicates('name')
            utils.dataframe_to_fasta(novpad,os.path.join(out,'novel.fa'),
                                     seqkey='sequence', idkey='name')
            novel.create_report(new, cl, self.species, outfile=os.path.join(out, 'novel.html'))

            #now count novel mirnas for all samples
            build_indexes(os.path.join(out,'novel.fa'), self.index_path)
            r,nc = base.map_rnas(self.files, ['novel'], self.temp_path,
                                 aligner=self.aligner,
                                 samplelabels=self.labels)
            nc.to_csv( os.path.join(out, 'novel_mirna_counts.csv'), index=False )
            end = round(time.time()-start,1)
            print ('took %s seconds' %str(end))
        return

    def map_genomic_features(self):
        """Map to a single set of features with a reference genome, requires we
           use ensembl gtf with biotype for best results"""

        out = self.output
        temp = self.temp_path
        ref_name = self.ref_name
        features = self.features
        if ref_name in self.aligner_params:
            params = self.aligner_params[ref_name]
        else:
            params = ''
        if ref_name == '':
            print ('you need to provide a reference genome')
            return

        print ()
        print ('found features files %s' %features)
        print ('mapping to reference genome')
        res = base.map_genome_features(self.files, ref_name, features,
                                       outpath=temp, aligner=self.aligner,
                                       aligner_params=params)
        counts = base.pivot_count_data(res, idxcols=['name','gene_name','gene_biotype'])
        res.to_csv( os.path.join(out, 'features_found.csv'), index=False )
        counts.to_csv( os.path.join(out, 'feature_counts.csv'), index=False)
        print ('results saved to feature_counts.csv')
        plot_feature_results(res, out)
        return

def check_viennarna():
    try:
        import RNA
        return True
    except ImportError as e:
        return False

def plot_results(res, path):
    """Some results plots"""

    if res is None or len(res) == 0:
        return
    counts = base.pivot_count_data(res, idxcols=['name','ref'])
    x = base.get_fractions_mapped(res)
    print (x)
    fig = plotting.plot_fractions(x)
    fig.savefig(os.path.join(path,'libraries_mapped.png'))
    fig = plotting.plot_sample_counts(counts)
    fig.savefig(os.path.join(path,'total_per_sample.png'))
    fig = plotting.plot_read_count_dists(counts)
    fig.savefig(os.path.join(path,'top_mapped.png'))
    scols,ncols = base.get_column_names(counts)
    for l,df in counts.groupby('ref'):
        if 'mirbase' in l:
            fig = plotting.plot_read_count_dists(df)
            fig.savefig(os.path.join(path,'top_%s.png' %l))
    #if len(scols)>1:
    #    fig = plotting.expression_clustermap(counts)
    #    fig.savefig(os.path.join(path,'expr_map.png'))
    return

def plot_feature_results(res, path):
    """plot results from feature counting"""

    if res is None or len(res) == 0:
        return
    counts = base.pivot_count_data(res, idxcols=['name','gene_name','gene_biotype'])
    x = base.get_fractions_mapped(res, by=['gene_biotype','label'])
    print (x)
    fig = plotting.plot_fractions(x)
    fig.savefig(os.path.join(path,'features_mapped.png'))
    fig = plotting.plot_sample_counts(counts)
    fig.savefig(os.path.join(path,'total_features_per_sample.png'))
    fig = plotting.plot_read_count_dists(counts)
    fig.savefig(os.path.join(path,'top_feature_counts.png'))
    return

def build_indexes(filename, path):
    aligners.build_bowtie_index(filename, path)
    #aligners.build_subread_index(filename, path)
    return

def diff_expression(opts):
    """Diff expression workflow"""

    path = opts['output']
    labelsfile = opts['sample_labels']
    countsfile = opts['count_file']
    for f in [labelsfile,countsfile]:
        if not os.path.exists(f) or f == '':
            print ('no such file %s!' %f)
            print_help()
            return
    labels = pd.read_csv(labelsfile, sep=opts['sep'])
    counts = pd.read_csv(countsfile)

    #define sample/factor cols and conditions for de
    samplecol = opts['sample_col']
    factorcol = opts['factors_col']
    conds = opts['conditions'].split(',')
    print (conds)
    #get the samples needed for the required conditions we want to compare
    data = de.get_factor_samples(counts,
                                 labels, [(factorcol,conds[0]),(factorcol,conds[1])],
                                 samplecol=samplecol, index='name')
    #print (data[:4])
    res = de.run_edgeR(data=data, cutoff=1.5)
    res.to_csv(os.path.join(path,'de_genes.csv'))
    print (res)
    names = res.name

    #plot these genes with seaborn
    xorder=conds
    m = de.melt_samples(counts, labels, names, samplecol=samplecol)
    g = base.sns.factorplot('age_s','read count', data=m, col='name', kind="point",
                            s=10, lw=1, col_wrap=4, size=4, aspect=1.2,
                            legend_out=True,sharey=False, order=xorder)
    g.savefig(os.path.join(path,'de_genes.png'))
    return

def print_help():
    """generic help message"""

    print ('to run a workflow use smallrnaseq -c <config> -r')
    print ('see https://github.com/dmnfarrell/smallrnaseq/wiki')
    print ('for further information')
    return

def run_test():
    """Run mirna test with test files"""

    print ('running miRNA counting test')
    indpath = 'testing/indexes'
    aligners.BOWTIE_INDEXES = indpath
    if not os.path.exists(indpath):
        os.makedirs(indpath)
    lib1 = os.path.join(base.datadir, 'bosTau8-tRNAs.fa')
    aligners.build_bowtie_index(lib1, path=indpath)
    f1 = os.path.join(base.datadir, 'bovine_plasma_sample.fastq')
    f2 = os.path.join(base.datadir, 'bovine_serum_sample.fastq')
    path = os.path.join('testing', 'ncrna_map')
    res,counts = base.map_mirbase(files=[f1,f2], overwrite=True, outpath=path,
                                  #indexes=['bosTau8-tRNA'],
                                  aligner='bowtie', species='bta')
    print (counts[:10])
    return

def main():
    """Run the application from outside the module - used for
       deploying as frozen app"""

    import sys, os
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config",
                        help="config file to use", metavar="FILE")
    parser.add_option("-r", "--run", dest="run",  action="store_true",
                        default=False, help="run smallrna mapping")
    parser.add_option("-b", "--build", dest="build",
                        help="build an index for given file", metavar="FILE")
    parser.add_option("-f", "--infile", dest="infile",
                        help="input file", metavar="FILE")
    parser.add_option("-l", "--collapse", dest="collapse", action="store_true",
                        default=False, help="collapse reads in input file")
    parser.add_option("-a", "--trim", dest="trim",  type='string',
                        help="trim given adapter in input file")
    parser.add_option("-d", "--de", dest="de",  action="store_true",
                        default=False, help="run DE analysis")
    parser.add_option("-t", "--tests", dest="tests",  action="store_true",
                        default=False, help="run tests")
    opts, remainder = parser.parse_args()

    if opts.infile != None:
        if opts.trim != None:
            utils.trim_adapters(opts.infile, adapters=opts.trim, outfile='cut.fastq')
        if opts.collapse == True:
            base.collapse_reads(opts.infile)
    elif opts.build != None:
        build_indexes(opts.build, 'indexes')
    elif opts.config != None and os.path.exists(opts.config):

        cp = config.parse_config(opts.config)
        options = config.get_options(cp)
        options = config.check_options(options)
        print ('using the following options:')
        print ('----------------------------')
        config.print_options(options)
        W = WorkFlow(options)
        st = W.setup()
        if opts.run == True:
            if st == True:
                W.run()
            else:
                print ('check your config file')
        elif opts.de == True:
            diff_expression(options)
        else:
            print_help()
    elif opts.tests == True:
        run_test()
    else:
        if opts.config != None:
            conffile = opts.config
        else:
            print ('No config file provided.')
            conffile = 'default.conf'
        config.write_default_config(conffile, defaults=config.baseoptions)
        print_help()
        return

if __name__ == '__main__':
    main()
