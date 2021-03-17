from flask import session
from application import app
import sys
import pickle
import primer3
import pandas as pd
import numpy as np 
import random
import subprocess
import time
import math
import re
import requests 
import os.path
import multiprocessing 
from multiprocessing.pool import Pool
from os import path

# define Python user-defined exceptions
class Error(Exception):
    """Base class for other exceptions"""
    pass


class PrimerNotFound(Error):
    """Raised when primer set is unable to be found"""
    pass
 
def BRED_to_fasta(ID, phage, edit_type, substrate, primer):
    f = open('output/{}_{}_{}.fasta'.format(phage, edit_type, ID), 'w')

    f.writelines(["> substrate \n",
                substrate,
                "\n\n",
                "> forward primer, tm:{}C, primer3 heterodimer:{} deltaG, primer3 hairpin:{} deltaG \n".format(primer["tm f"], primer["hetero f dg"], primer["hairpin f"]),
                primer["primer f"],
                "\n\n",
                "> reverse primer, tm:{}C, primer3 hairpin:{} deltaG \n".format(primer["tm r"], primer["hairpin r"]),
                primer["primer r"],
                "\n\n",
                "> control primer, tm:{}C, primer3 heterodimer:{} deltaG, primer3 hairpin score:{} deltaG \n".format(primer["tm c"], primer["hetero c dg"], primer["hairpin c"]),
                primer["primer c"],
                "\n\n",
                "> experiment primer, tm:{}C, primer3 heterodimer:{} deltaG, primer3 hairpin score:{} deltaG \n".format(primer["tm e"], primer["hetero e dg"], primer["hairpin e"]),
                primer["primer e"]
                ])
    f.close()


#################################
#### DOWNLOAD PHAGESDB DATA #####
#################################
def download_all_fastas():
    """Download all fasta from phagesDB"""
    if not path.isfile("data/fasta_files/ZygoTaiga.fasta"):
        proc = subprocess.check_call("mkdir -p data/fasta_files", shell=True)

        url = "https://phagesdb.org/media/Actinobacteriophages-All.fasta"
        r = requests.get(url, allow_redirects=True)

        if r.status_code == 404:
            return "unable to find multifasta"

        # split fasta
        phage_fastas = str(r.content).split(">")

        # iterate through and download
        for fasta in phage_fastas:
            fasta = ">" + fasta
            if len(fasta)>1000:
                    phage_name = str(fasta).split('\\n',1)[0].split(" ")[2].replace(",", "")
                    f = open('data/fasta_files/{}.fasta'.format(phage_name), 'w')
                    f.writelines(fasta.replace("\\n"," \n"))
                    f.close()

def download_phage_metadata():
    """Download sequenced phage metadata from phagesDB"""
    if not path.isfile("data/phage_metadata.csv"):
        url = "https://phagesdb.org/data/?set=seq&type=full"

        r = requests.get(url, allow_redirects=True)

        if r.status_code == 404:
            return "unable to find multifasta"
        
        lines = str(r.content).split("\\n")
        lines = [l.split("\\t") for l in lines]
        df = pd.DataFrame(columns = lines[0], data = lines[1:])

        # rename to fit with research code
        df.rename(columns={'b\'Phage Name':'phage',
                            'Temperate?':'temperate',
                            'Cluster':'cluster',
                            'Subcluster':'subcluster',
                            'Morphotype':'morphotype',
                            'Host':'host',
                            'Genome Length(bp)':'genome length',
                            'GC%':'gcpercent',
                            'Phamerated?':'is phamerated',
                            'Annotation Status':'is annotated'
                        }, inplace = True)
        
        # only retrieve specific columns
        df = df[['phage','temperate','cluster','subcluster','morphotype','host','genome length','is annotated','is phamerated','gcpercent']]
    
        # set types
        df = df.astype({'phage':'str',
                    'temperate':'bool',
                    'cluster':'str',
                    'subcluster':'str',
                    'morphotype':'str',
                    'host':'str',
                    'genome length':'float',
                    'is annotated':'bool',
                    'is phamerated':'bool',
                    'gcpercent':'float'})

        # export to csv
        df.to_csv("data/phage_metadata.csv", index=False)

def download_phage_genes(phage):
    query_url = "https://phagesdb.org/api/genesbyphage/{}/".format(phage)

    try:
        if not path.isfile("data/genes_by_phage/{}_genes.csv".format(phage)):
            response = requests.get(url = query_url).json()['results']
            df = pd.DataFrame(response)

            a_file = open("static_data/conversion_table.pkl", "rb")
            conversion_table = pickle.load(a_file)
            df["phage"] = df["PhageID"].apply(lambda x: x['PhageID'])
            df["gene number"] = df['GeneID'].apply(lambda x: x.split("_")[-1])
            df["pham"] = df['phams'].apply(lambda x: x[0])
            df["Notes"] = df["Notes"].apply(lambda x: str(x).lower()[2:-1])
            df["function"] = df["Notes"].apply(lambda x: conversion_table[x] if x in conversion_table.keys() else "NKF")

            df.rename(columns={'GeneID':'gene ID',
                                'translation':'translation',
                                'Orientation':'orientation',
                                'Start':'start',
                                'Stop':'stop',
                                'Notes':'uncleaned function'
                                }, inplace = True)
                                
            df = df[['gene ID','pham','function','translation','orientation','phage','gene number','start','stop','uncleaned function']]
            df.to_csv("data/genes_by_phage/{}_genes.csv".format(phage))
            return df
        else:
            return pd.read_csv("data/genes_by_phage/{}_genes.csv".format(phage))
    except: # if phage has no genes df then edit the metadata csv and return empty DF
        phage_df = pd.read_csv("data/phage_metadata.csv")
        phage_df[phage_df["phage"]!=phage].to_csv("data/phage_metadata.csv")
        return pd.DataFrame(columns=['gene ID','pham','function','translation','orientation','phage','gene number','start','stop','uncleaned function'])

def download_all_phage_genes():
    """Download list of phage genes for each phage that is sequenced in phagesDB"""

    if not path.isfile("data/cleaned_gene_list.csv"):

        meta_file_path = "data/phage_metadata.csv"
        if not path.isfile(meta_file_path):
            download_phage_metadata()
        phage_df = pd.read_csv(meta_file_path)
        phages = phage_df["phage"].unique()

        proc = subprocess.check_call("mkdir -p data/genes_by_phage", shell=True)

        with Pool(multiprocessing.cpu_count()-2) as p:  # to check multiprocessing.cpu_count()
            output_dfs = p.map(download_phage_genes, phages)

        all_phages_genes_df = pd.concat(output_dfs)
        all_phages_genes_df.to_csv("data/cleaned_gene_list.csv")

def download_phage_fasta(phage):
    """ Download phage fasta from phagesDB """
    url = "https://phagesdb.org/media/fastas/{}.fasta".format(phage)
    r = requests.get(url, allow_redirects=True)
    if r.status_code == 404:
        return "unable to find phage"
    open('data/fasta_files/{}.fasta'.format(phage), 'wb').write(r.content)
    return ""

def fasta_to_DNA(phage):
    """ Extract DNA into string form from a fasta file """
    file_path = 'data/fasta_files/{}.fasta'.format(phage)

    if not path.isfile(file_path):
        out = download_phage_fasta(phage)
        if len(out) > 0:
            return out

    f = open(file_path, "r")
    DNA = ''.join(f.read().split("\n")[1:]).replace(" ","")
    return DNA

def eGFP_DNA():
    """ Extract EGFP DNA into string form from a fasta file """
    file_path = 'static_data/eGFP.fasta'
    f = open(file_path, "r")
    DNA = ''.join(f.read().split("\n")[1:]).replace(" ","")
    return DNA



####################################
#### Generate Synteny Networks #####
####################################



##############################
#### BRED ASSISTANT CODE #####
##############################

def collect_gene_info(phage, gp_num):
    """ Collect gene info using phagesdb API """
    file_path = "data/genes_by_phage/{}_genes.csv".format(phage)

    if not path.isfile(file_path):
        genes_df = download_phage_genes(phage)
    else:
        genes_df = pd.read_csv(file_path)

    # is gene number is not in list 
    if genes_df.empty:
        return ""

    # extract gene info
    target_gene_df = genes_df[genes_df["gene number"] == gp_num]

    # is gene number is not in list 
    if target_gene_df.empty:
        return genes_df.shape[0]
    
    return target_gene_df.iloc[0].to_dict()

def collect_phage_info(phage):
    """ Collect phage info from metadata file """
    phage_df = pd.read_csv("data/phage_metadata.csv")
    target = phage_df[phage_df["phage"]==phage]

    if target.empty:
        return ""

    return target.iloc[0].to_dict()


def primer3_calculate_hairpin(seq):
    return primer3.calcHairpin(seq).dg

def primer3_calculate_tm(seq):
    tm = primer3.calcTm(seq)
    return tm if isinstance(tm, float) else None

def primer3_calculate_heterodimer(seq1, seq2):
    return primer3.calcHeterodimer(seq1, seq2).dg

def find_start_position(primer, DNA, orientation):
    if orientation == "F":
        start = DNA.find(primer)
    elif orientation == "R":
        start = DNA.find(reverse(complement(primer))) + len(primer)
    return start + 1

def find_primers(DNA, edited_DNA, bp_position_start, bp_position_stop, edit_type, template_DNA = "", melting_temp = 60, primer_length = 20):
    """ Finds forward, middle, reverse primers given DNA sequence 
    
    Insertion Primers:
        - FORWARD upstream of start bp
        - REVERSE downstream of stop bp
        - EXPERIMENTAL of region unique to insertion DNA

    Swap Primers:
        - FORWARD upstream of start bp
        - REVERSE downstream of stop bp
        - EXPERIMENTAL of region unique to insertion DNA

    Deletion Primers:
        - FORWARD upstream of start bp
        - REVERSE downstream of stop bp
        - EXPERIMENTAL of region spanning across deleted region
                ie sequene is 123456789 we want to delete 56 then a EXPERIMENTAL primer could be 3479
    """
    possible_primers = find_possible_primers(DNA, edited_DNA, bp_position_start, bp_position_stop, edit_type, template_DNA)
    possible_primers["hairpin"] = possible_primers["primer_seq"].apply(primer3_calculate_hairpin)
    possible_primers["tm"] = possible_primers["primer_seq"].apply(primer3_calculate_tm)
    possible_primers.dropna(subset=["tm","hairpin"], inplace=True)
    # set hairpin to zero, below zero indicates binding
    possible_primers = possible_primers[possible_primers["hairpin"]>=-1000]

    # sort by target melting temp
    possible_primers = possible_primers.sort_values(by=["tm"]).reset_index(drop=True)

    max_tm_range = 0.1

    primer_sets = pd.DataFrame(columns=["primer f","primer r","primer e","primer c", "tm f", "tm r", "tm c", "tm e", "min heterodimer", "mean tm", "tm range", "min hairpin"])

    while primer_sets.empty:
        for index, row in possible_primers.iterrows(): 
            current_tm = row["tm"]
            primers_in_range = possible_primers.iloc[index:][abs(possible_primers.iloc[index:]["tm"]-current_tm) < max_tm_range]
            if len(primers_in_range["primer"].unique()) == 4: # all needed primers
                for _, f_row in primers_in_range[primers_in_range["primer"]=="f"].iterrows():
                    for _, r_row in primers_in_range[primers_in_range["primer"]=="r"].iterrows():
                        for _, c_row in primers_in_range[primers_in_range["primer"]=="c"].iterrows():
                            for _, e_row in primers_in_range[primers_in_range["primer"]=="e"].iterrows():
                                # temperature calculations
                                mean_tm = (f_row["tm"]+r_row["tm"]+c_row["tm"]+e_row["tm"])/4
                                min_tm = min([f_row["tm"],r_row["tm"],c_row["tm"],e_row["tm"]])
                                max_tm = max([f_row["tm"],r_row["tm"],c_row["tm"],e_row["tm"]])

                                # primer compatibilty (heterodimer score)
                                dg_f = primer3_calculate_heterodimer(f_row["primer_seq"], r_row["primer_seq"])
                                dg_c = primer3_calculate_heterodimer(c_row["primer_seq"], r_row["primer_seq"])
                                dg_e = primer3_calculate_heterodimer(e_row["primer_seq"], r_row["primer_seq"])
                                min_heterodimer = min([dg_f, dg_c, dg_e])

                                # min hairpin
                                min_hairpin = min([f_row["hairpin"], r_row["hairpin"], c_row["hairpin"], e_row["hairpin"]])
                                
                                primer_sets = primer_sets.append({  "primer f": f_row["primer_seq"],
                                                                    "primer r": r_row["primer_seq"],
                                                                    "primer c": c_row["primer_seq"],
                                                                    "primer e": e_row["primer_seq"],
                                                                    "tm f": round(f_row["tm"],2),
                                                                    "tm r": round(r_row["tm"],2),
                                                                    "tm c": round(c_row["tm"],2),
                                                                    "tm e": round(e_row["tm"],2),
                                                                    "hetero f dg": round(dg_f,2),
                                                                    "hetero c dg": round(dg_c,2),
                                                                    "hetero e dg": round(dg_e,2),
                                                                    "hairpin f": round(f_row["hairpin"],2),
                                                                    "hairpin r": round(r_row["hairpin"],2),
                                                                    "hairpin c": round(c_row["hairpin"],2),
                                                                    "hairpin e": round(e_row["hairpin"],2),
                                                                    "min heterodimer": round(min_heterodimer/1000,1), # sign change and rounding are for final sort
                                                                    "mean tm": mean_tm,
                                                                    "diff tm target": round(abs(melting_temp-mean_tm),1),
                                                                    "tm range": round(max_tm-min_tm, 1),
                                                                    "min hairpin":min_hairpin}, ignore_index=True)
        max_tm_range += 0.1
        if max_tm_range > 1:
            return primer_sets

    primer_sets.drop_duplicates(inplace=True)

    # confirm starts in each primer
    primer_sets["f start"] = primer_sets["primer f"].apply(find_start_position, args=(DNA,"F"))
    primer_sets["f edited start"] = primer_sets["primer f"].apply(find_start_position, args=(edited_DNA,"F"))

    primer_sets["r start"] = primer_sets["primer r"].apply(find_start_position, args=(DNA,"R"))
    primer_sets["r edited start"] = primer_sets["primer r"].apply(find_start_position, args=(edited_DNA,"R"))

    primer_sets["c start"] = primer_sets["primer c"].apply(find_start_position, args=(DNA,"F"))
    primer_sets["c edited start"] = primer_sets["primer c"].apply(find_start_position, args=(edited_DNA,"F")) # this should be zero becuase it doesn't bind!

    primer_sets["e start"] = primer_sets["primer e"].apply(find_start_position, args=(DNA,"F"))
    primer_sets["e edited start"] = primer_sets["primer e"].apply(find_start_position, args=(edited_DNA,"F"))  # this should be zero becuase it doesn't bind!

    return primer_sets.sort_values(by = ["tm range","min heterodimer", "diff tm target"], ascending=[True, False, True]).reset_index(drop=True)


def all_possible_subsets(seq, primer_length, primer_type):
    """ Takes sequence and find all possible string subsets of primer_length
    """
    return pd.DataFrame(np.array([[seq[i:i+primer_length], primer_type] for i in range(len(seq)-primer_length+1)]), columns=['primer_seq','primer'])

def find_possible_primers(DNA, edited_DNA, bp_position_start, bp_position_stop, edit_type, template_DNA, primer_length = 20, search_size = 200, testing = False):
    """ Finds region to extract primers from then get ever possible subset
    """
    arm_length = primer_length-2
    start_index = bp_position_start-1
    stop_index = bp_position_stop-1 
    if edit_type == "replacement": # insertion
        # possible forward primers
        forward_region = DNA[start_index-primer_length-search_size:start_index-primer_length]
        f_df = all_possible_subsets(forward_region, primer_length, "f")
        # possible reverse primers
        if testing:
            reverse_region = DNA[stop_index+primer_length:stop_index+primer_length+search_size]
        else:    
            reverse_region = reverse(complement(DNA[stop_index+primer_length:stop_index+primer_length+search_size]))
        r_df = all_possible_subsets(reverse_region, primer_length, "r")

        # possible control primers
        control_region = DNA[start_index-arm_length:stop_index+arm_length+1]
        if len(control_region)>search_size:
            control_region = control_region[:search_size]
        c_df = all_possible_subsets(control_region, primer_length, "c")

        # possible experimental primers
        experimental_region = edited_DNA[start_index-arm_length:start_index+len(template_DNA)+arm_length]
        if len(experimental_region)>search_size:
            experimental_region = experimental_region[:search_size]
        e_df = all_possible_subsets(experimental_region, primer_length, "e")

    elif edit_type == "insertion":
        # possible forward primers
        forward_region = DNA[start_index-primer_length-search_size:start_index-primer_length]
        f_df = all_possible_subsets(forward_region, primer_length, "f")

        # possible reverse primers
        if testing:
            reverse_region = DNA[stop_index+primer_length:stop_index+primer_length+search_size]
        else:    
            reverse_region = reverse(complement(DNA[stop_index+primer_length:stop_index+primer_length+search_size]))

        r_df = all_possible_subsets(reverse_region, primer_length, "r")

        # possible control primers
        control_region = DNA[start_index-arm_length:stop_index+arm_length]
        c_df = all_possible_subsets(control_region, primer_length, "c")

        # possible experimental primers
        experimental_region = edited_DNA[start_index:start_index+len(template_DNA)]
        if len(experimental_region)>search_size:
            experimental_region = experimental_region[:search_size]
        e_df = all_possible_subsets(experimental_region, primer_length, "e")

    elif  edit_type == "deletion": # deletion
        # possible forward primers
        forward_region = DNA[start_index-primer_length-search_size:start_index-primer_length]
        f_df = all_possible_subsets(forward_region, primer_length, "f")
        
        # possible reverse primers
        if testing:
            reverse_region = DNA[stop_index+primer_length:stop_index+primer_length+search_size]
        else:    
            reverse_region = reverse(complement(DNA[stop_index+primer_length:stop_index+primer_length+search_size]))
        r_df = all_possible_subsets(reverse_region, primer_length, "r")

        # possible control primers
        control_region = DNA[start_index-arm_length:stop_index+arm_length]
        if len(control_region)>search_size:
            control_region = control_region[:search_size]
        c_df = all_possible_subsets(control_region, primer_length, "c")
        # possible experimental primers
        experimental_region = edited_DNA[start_index-arm_length:start_index+arm_length]
        e_df = all_possible_subsets(experimental_region, primer_length, "e")
    
    possible_primers = pd.concat([f_df, r_df, c_df, e_df])

    possible_primers.drop_duplicates(subset=["primer_seq"], keep=False, inplace=True)
    # check for duplicate strands
    if not possible_primers["primer_seq"].is_unique:
        raise TypeError

    return possible_primers

    

def find_primer(DNA, region, is_experiment = False):
    """ Greedy search to find unique primer to minimize hairpin score and homodimer"""
    # https://libnano.github.io/primer3-py/quickstart.html#calcHairpin


def find_amplicon(DNA, forward_primer, reverse_primer):
    """ Using primers find amplicon DNA 
    
        ex. 
            params
                DNA = ATGGAGGGGCGATG
                forward_primer = TGG
                reverse_primer = ATC
            return 
                AGGGGC
                
    """

    # find primer F location
    F_start_bp = DNA.find(forward_primer)+1
    F_stop_bp = F_start_bp + len(forward_primer)

    # find primer R location
    R_stop_bp = DNA.find(reverse(complement(reverse_primer)))+1
    R_start_bp = R_stop_bp + len(reverse_primer)

    if F_start_bp == 0 or R_stop_bp == 0: # primers are not found in DNA
        raise PrimerNotFound

    amplicon = DNA[F_stop_bp-1:R_stop_bp-1]

    return amplicon

def find_editing_substrate(DNA, bp_position_start, bp_position_stop, template_DNA = None, homo_length = app.config["HOMOLOGOUS_LENGTH"]):
    """ Find DNA sequence for editing substrate this includes homologous arms
    
    Insertion:
        ex.
            params
                DNA = abcdefghi
                bp_position_start = 4
                bp_position_stop = 4
                template_DNA = xyz

            return
                abcdxyzefghi

    Swap:
        ex. 
            params
                DNA = abcdefghi
                bp_position_start = 4
                bp_position_stop = 6
                template_DNA = xyz

            return
                bcxyzgh

    Deletion:
        ex. 
            params
                DNA = abcdefghi
                bp_position_start = 4
                bp_position_stop = 6
                template_DNA = ""

            return
                bcgh

    """
    template_DNA = ("" if template_DNA == None else template_DNA)
    if bp_position_stop == bp_position_start: # for insertion
        homo_pre = DNA[bp_position_start-homo_length:bp_position_start]
        homo_post = DNA[bp_position_stop:bp_position_stop+homo_length]
        edited_DNA = DNA[:bp_position_start] + template_DNA + DNA[bp_position_stop:]
    else: # for swap or deletion
        homo_pre = DNA[bp_position_start-homo_length-1:bp_position_start-1]
        homo_post = DNA[bp_position_stop:bp_position_stop+homo_length]
        edited_DNA = DNA[:bp_position_start-1] + template_DNA + DNA[bp_position_stop:]

    substrate = homo_pre + template_DNA + homo_post

    return substrate, edited_DNA

def complement(seq):
    comp_table = {"A":"T", "T":"A", "C":"G", "G":"C"}

    comp_seq = ""
    for bp in seq:
        comp_seq += comp_table[bp]
    return comp_seq
    
def reverse(seq):
    return seq[::-1]