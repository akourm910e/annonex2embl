#!/usr/bin/env python2.7

''' Main operations in annonex2embl '''

#####################
# IMPORT OPERATIONS #
#####################

from Bio import SeqIO
#from Bio.Alphabet import generic_dna
#from Bio.Seq import Seq
from Bio import SeqFeature
from collections import OrderedDict
from copy import copy

# Add specific directory to sys.path in order to import its modules
# NOTE: THIS RELATIVE IMPORTING IS AMATEURISH.
# NOTE: COULD THE FOLLOWING IMPORT BE REPLACED WITH 'import annonex2embl'?
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'annonex2embl'))

import MyExceptions as ME
import CheckingOps as CkOps
import DegappingOps as DgOps
import GenerationOps as GnOps
import GlobalVariables as GlobVars
import ParsingOps as PrOps
import IOOps as IOOps

###############
# AUTHOR INFO #
###############

__author__ = 'Michael Gruenstaeudl <m.gruenstaeudl@fu-berlin.de>'
__copyright__ = 'Copyright (C) 2016-2017 Michael Gruenstaeudl'
__info__ = 'nex2embl'
__version__ = '2017.02.01.1800'

#############
# DEBUGGING #
#############

import pdb
#pdb.set_trace()

###########
# CLASSES #
###########

#############
# FUNCTIONS #
#############

def annonex2embl(path_to_nex,
                 path_to_csv,
                 descr_DEline,
                 email_addr,
                 path_to_outfile,
                 
                 tax_check='False',
                 checklist_mode='False',
                 checklist_type=None,
                 linemask='False',
                 topology='linear',
                 tax_division='PLN',
                 uniq_seqid_col='isolate',
                 transl_table='11',
                 seq_version='1'):

########################################################################

# 0. MAKE SPECIFIC VARIABLES BOOLEAN
    from distutils.util import strtobool
    taxcheck_bool = strtobool(tax_check)
    checklist_bool = strtobool(checklist_mode)
    linemask_bool = strtobool(linemask)

########################################################################

# 1. OPEN OUTFILE
    outp_handle = open(path_to_outfile, 'a')

########################################################################

# 2. PARSE DATA FROM .NEX-FILE
    try:
        charsets_global, alignm_global = IOOps.Inp().\
            parse_nexus_file(path_to_nex)
    except ME.MyException as e:
        sys.exit('%s annonex2embl ERROR: %s' % ('\n', e))

########################################################################

# 3. PARSE DATA FROM .CSV-FILE
    try:
        raw_qualifiers = IOOps.Inp().parse_csv_file(path_to_csv)
    except ME.MyException as e:
        sys.exit('%s annonex2embl ERROR: %s' % ('\n', e))

########################################################################

# 4. CHECK QUALIFIERS
# 4. Perform quality checks on qualifiers
    try:
        CkOps.QualifierCheck(raw_qualifiers, uniq_seqid_col).\
            quality_of_qualifiers()
    except ME.MyException as e:
        sys.exit('%s annonex2embl ERROR: %s' % ('\n', e))
# 4.2. Remove qualifiers without content (i.e. empty qualifiers)
    nonempty_qualifiers = CkOps.QualifierCheck.\
        _rm_empty_qual(raw_qualifiers)
# 4.3. Enforce that all qualifier values consist of ASCII characters
    filtered_qualifiers = CkOps.QualifierCheck.\
        _enforce_ASCII(nonempty_qualifiers)

########################################################################

# 5. PARSE OUT FEATURE KEY, OBTAIN OFFICIAL GENE NAME AND GENE PRODUCT 
    charset_dict = {}
    for charset_name in charsets_global.keys():
        try:
            charset_sym, charset_type, charset_product = PrOps.\
                ParseCharsetName(charset_name, email_addr).parse()
        except ME.MyException as e:
            sys.exit('%s annonex2embl ERROR: %s' % ('\n', e))
        
        charset_dict[charset_name] = (charset_sym, charset_type,
            charset_product)

########################################################################

# 6. GENERATING SEQ_RECORDS BY LOOPING THROUGH EACH SEQUENCE OF THE ALIGNMENT
#    Work off the sequences alphabetically.
    sorted_seqnames = sorted(alignm_global.keys())
    for counter, seq_name in enumerate(sorted_seqnames):
        #TFLs generate safe copies of charset and alignment for every
        #loop iteration
        charsets_withgaps = copy(charsets_global)
        alignm = copy(alignm_global)
        
####################################

# 6.1. SELECT CURRENT SEQUENCES AND CURRENT QUALIFIERS
        current_seq = alignm[seq_name]
        current_quals = [d for d in filtered_qualifiers\
            if d[uniq_seqid_col] == seq_name][0]

####################################

# 6.2. GENERATE THE BASIC SEQ_RECORD (I.E., WITHOUT FEATURES)

# 6.2.1. Generate the basic SeqRecord
        seq_record = GnOps.GenerateSeqRecord().base_record(
            current_seq, current_quals, uniq_seqid_col, seq_version, 
            descr_DEline, topology, tax_division)

####################################

# 6.3. CLEAN UP THE SEQUENCE OF THE SEQ_RECORD (i.e., remove leading or 
#      trailing ambiguities, remove gaps), but maintain correct 
#      annotations.
#      Note 1: This clean-up has to occur before (!) the SeqFeature 
#      'source' is generated, as the source feature provides info on 
#      the full sequence length.
#      Note 2: Charsets are identical across all sequences.

# 6.3.1. Replace question marks in DNA sequence with 'N'
        seq_record.seq._data = seq_record.seq._data.replace('?', 'N')
        # TFL generates a safe copy of sequence to work on
        seq_withgaps = copy(seq_record.seq)

# 6.3.2. Remove leading ambiguities while maintaining 
#        correct annotations
        seq_noleadambigs, charsets_noleadambigs = DgOps.\
            RmAmbigsButMaintainAnno().rm_leadambig(seq_withgaps, 'N', \
            charsets_withgaps)

# 6.3.3. Remove trailing ambiguities while maintaining 
#        correct annotations
        seq_notrailambigs, charsets_notrailambigs = DgOps.\
            RmAmbigsButMaintainAnno().rm_trailambig(seq_noleadambigs, \
            'N', charsets_noleadambigs)

# 6.3.4. (FUTURE) Give note that leading or trailing ambiguities were 
#        removed; for future association with of fuzzy ends
#        if seq_noltambigs != seq_record.seq:
#            ltambigs_removed = True

# 6.3.5. Degap the sequence while maintaining correct annotations
        seq_nogaps, charsets_degapped = DgOps.\
            DegapButMaintainAnno(seq_notrailambigs, '-', \
            charsets_notrailambigs).degap()
        # TFL assigns the deambiged and degapped sequence back
        seq_record.seq = seq_nogaps

####################################

# 6.4. GENERATE SEQFEATURE 'SOURCE' AND TEST TAXON NAME AGAINST 
#      NCBI TAXONOMY

# 6.4.1. Generate SeqFeature 'source' and append to features list
        charset_names = charsets_degapped.keys()
        source_feature = GnOps.GenerateSeqFeature().\
            source_feat(len(seq_record), current_quals, charset_names, 
            transl_table)
        seq_record.features.append(source_feature)

####################################

# 6.5. VALIDATE TAXON NAME

# 6.5.1. Test taxon name against NCBI taxonomy; if not listed, adjust
#        taxon name and append ecotype info
        if taxcheck_bool:
            seq_record = PrOps.ConfirmAdjustTaxonName().go(seq_record, 
                email_addr)

####################################

# 6.6. POPULATE THE FEATURE KEYS WITH THE CHARSET INFORMATION
#      Note: Each charset represents a dictionary that must be added in 
#      full to the list "SeqRecord.features"
        for charset_name, charset_range in charsets_degapped.items():

# 6.6.1. Convert charset_range into Location Object
            location_object = GnOps.GenerateFeatLoc().make_location(charset_range)

# 6.6.2. Assign a gene product to a gene name
            charset_sym, charset_type, charset_product = charset_dict[charset_name]

# 6.6.3. Generate a regular SeqFeature and append to seq_record.features
#        Note: The position indices for the stop codon are truncated in 
#              this step.
            seq_feature = GnOps.GenerateSeqFeature().regular_feat(charset_sym,
                charset_type, location_object, charset_product)
            seq_record.features.append(seq_feature)

####################################

# 6.7. SORT ALL SEQ_RECORD.FEATURES EXCEPT THE FIRST ONE (WHICH 
#      CONSTITUTES THE SOURCE FEATURE) BY THEIR RELATIVE START 
#      POSITIONS
        sorted_features = sorted(seq_record.features[1:],
            key=lambda x: x.location.start.position)
        seq_record.features = [seq_record.features[0]] + sorted_features

####################################

# 6.8. TRANSLATE AND CHECK QUALITY OF TRANSLATION
        removal_list = []
        for indx, feature in enumerate(seq_record.features):
            # Check if feature is a coding region
            if feature.type == 'CDS' or feature.type == 'gene':
                try:
                    feature = CkOps.TranslCheck().\
                        transl_and_quality_of_transl(seq_record, 
                        feature, transl_table)
                except ME.MyException as e:
                    print('%s annonex2embl WARNING: %s Feature `%s` '\
                        '(type: `%s`) of sequence `%s` is not saved to '\
                        'output.' % ('\n', e, feature.id, feature.type,
                        seq_record.id))
                    removal_list.append(indx)
        # TFL removes the objects in reverse order, as each removal
        # shifts the indices of subsequent objects to the left
        for indx in sorted(removal_list, reverse=True):
            seq_record.features.pop(indx)

####################################

# 6.9. INTRODUCE FUZZY ENDS
        for feature in seq_record.features:
            # Check if feature is a coding region
            if feature.type == 'CDS' or feature.type == 'gene':
                # Note: Don't use "feature.extract(seq_record.seq)" in TFL,
                #       as stop codon was truncated from feature under 
                #       Step 6.5.3.
                coding_seq = ''.join([seq_record.seq[i] for i in charset_range])
                if not coding_seq.startswith(GlobVars.nex2ena_start_codon):
                    feature.location = GnOps.GenerateFeatLoc(
                        ).make_start_fuzzy(feature.location)
                if all([not coding_seq.endswith(c) for c in GlobVars.nex2ena_stop_codons]):
                    feature.location = GnOps.GenerateFeatLoc(
                        ).make_end_fuzzy(feature.location)
# (FUTURE) Also introduce fuzzy ends when leading or trailing Ns were removed

####################################

# 6.10. DECISION OF WHICH OUTPUT FORMAT TO EMPLOY
        if checklist_bool:
            if checklist_type == 'trnK_matK':
                IOOps.ENAchecklist().matK_trnK(seq_record, counter,
                    outp_handle)
            else:
                sys.exit('%s annonex2embl ERROR: Checklist type `%s` \
                    not recognized.' % ('\n', checklist_type))
        else:
            IOOps.Outp().write_EntryUpload(seq_record, outp_handle,
                linemask_bool)

########################################################################

# 7. CLOSE OUTFILE
    outp_handle.close()
