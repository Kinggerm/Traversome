#!/usr/bin/env python

"""
Class objects to store Graph Alignments 
"""

import csv
import re
from loguru import logger
from traversome.Assembly import Assembly  # used here to validate type

CONVERT_STRAND = {"+": True, "-": False}
CIGAR_ALPHA_REG = "([MIDNSHPX=])"


class GAFRecord(object):
    """
    Multiple GAFRecord objects make up a GraphAlignRecords object.
    ref: http://www.liheng.org/downloads/rGFA-GAF.pdf
    """

    def __init__(self, record_line_split, parse_cigar=False):

        # store information
        self.query_name = record_line_split[0]
        self.query_len = int(record_line_split[1])  # q_len or q_aligned_len, not specified in GAF doc, can be tested
        self.q_start = int(record_line_split[2])
        self.q_end = int(record_line_split[3])
        self.q_strand = CONVERT_STRAND[record_line_split[4]]
        self.path_str = record_line_split[5]
        self.path = self.parse_gaf_path()
        self.p_len = int(record_line_split[6])
        self.p_start = int(record_line_split[7])  # start position on the path
        self.p_end = int(record_line_split[8])  # end position on the path
        self.p_align_len = self.p_end - self.p_start
        self.num_match = int(record_line_split[9])
        self.align_len = int(record_line_split[10])
        self.align_quality = int(record_line_split[11])
        self.optional_fields = {}

        # ...
        for flag_type_val in record_line_split[12:]:
            op_flag, op_type, op_val = flag_type_val.split(":")
            if op_type == "i":
                self.optional_fields[op_flag] = int(op_val)
            elif op_type == "Z":
                self.optional_fields[op_flag] = op_val
            elif op_type == "f":
                self.optional_fields[op_flag] = float(op_val)
        if parse_cigar and "cg" in self.optional_fields:
            self.cigar = self.split_cigar_str()
        else:
            self.cigar = None
        self.identity = self.optional_fields.get("id", self.num_match / float(self.align_len))

    def parse_gaf_path(self):
        path_list = []
        for segment in re.findall(r".[^\s><]*", self.path_str):
            # omit the coordinates using .split(":")[0]
            if segment[0] == ">":
                path_list.append((segment[1:].split(":")[0], True))
            elif segment[0] == "<":
                path_list.append((segment[1:].split(":")[0], False))
            else:
                path_list.append((segment.split(":")[0], True))
        return path_list

    def split_cigar_str(self):
        cigar_str = self.optional_fields['cg']
        cigar_split = re.split(CIGAR_ALPHA_REG, cigar_str)[:-1]  # empty end
        cigar_list = []
        for go_part in range(0, len(cigar_split), 2):
            cigar_list.append((int(cigar_split[go_part]), cigar_split[go_part + 1]))
        return cigar_list


class SPATSVRecord(object):
    """
    Multiple SPAligner SPATSVRecord objects also make up a GraphAlignRecords object.
    SPATSVRecord is generated by SPAligner, which seems weaker than GraphAligner but works in MacOS
    ref: https://github.com/ablab/spades/tree/aab988a9b4986906b38396da7233bb1ee02982f2/assembler/src/projects/spaligner
    """

    def __init__(self, record_line_split):
        # store information

        # name — sequence name
        # 0 — start position of alignment on sequence
        # 2491 — end position of alignment on sequence
        # 536 — start position of alignment on the first edge of the Path (here on edge with id=44)
        # 1142 — end position of alignment on the last edge of the Path (here on conjugate edge to edge with id=38)
        # 2491 — sequence length
        # 44+,24+,22+,1+,38- — Path of the alignment
        # 909,4,115,1,1142 — lengths of the alignment on each edge of the Path respectively (44+,24+,22+,1+,38-)
        # AGGTTGTTTTTTGTTTCTTCCGC... — sequence of alignment Path

        self.query_name = record_line_split[0]
        self.q_start = int(record_line_split[1])  # zero based
        self.q_end = int(record_line_split[2])
        self.p_start = int(record_line_split[3])  # self.p_end generated latter
        self.query_len = int(record_line_split[5])
        self.q_align_len = abs(self.q_start - self.q_end) + 1
        self.path_str = record_line_split[6]
        self.path = self.parse_spa_tsv_path()
        # self.path_align_lengths was not found in GAF but this can be used during trimming overlaps (see self.p_len)
        self.path_align_lengths = [int(_len_) for _len_ in record_line_split[7].split(",")]
        # self.path_seq was not found in GAF and not used for traversome
        # self.path_seq = record_line_split[8]
        self.q_strand = self.q_end >= self.q_start
        # self.p_len was not provided. For GAF, self.p_len will be used during trimming.
        # self.p_len = None
        self.p_align_len = sum(self.path_align_lengths)
        self.p_end = self.p_start + self.p_align_len

        # SPAligner does not provide self.align_len, use the larger one to approximate this value
        self.align_len = max(self.p_align_len, self.q_align_len)

        # SPAligner does not provide following info, may use other approaches to generate if necessary
        # self.num_match = None
        # self.identity = None
        # self.align_quality = None
        # self.optional_fields = {}
        # self.cigar = None

    def parse_spa_tsv_path(self):
        path_list = []
        for v_str in self.path_str.split(","):
            path_list.append((v_str[:-1], CONVERT_STRAND[v_str[-1]]))
        return path_list


# TODO parallelize parsing
class GraphAlignRecords(object):
    """
    Stores GraphAlign records...
 
    Parameters
    ----------
    alignment_file (str):
        path to an alignment file.
    alignment_format (str):
        format of the alignment file, must be GAF or SPA-TSV
    parse_cigar (bool):
        parsing CIGARs allows for ... default=False.
    min_aligned_path_len (int):
        ...
    """

    def __init__(
            self,
            alignment_file,
            alignment_format="GAF",
            parse_cigar=False,
            min_aligned_path_len=0,
            min_align_len=0,
            min_identity=0.,
            trim_overlap_with_graph=False,
            assembly_graph=None):

        # store params to self
        self.alignment_file = alignment_file
        assert alignment_format in ("GAF", "SPA-TSV"), "Unsupported format {}!".format(alignment_format)  # currently
        self.alignment_format = alignment_format
        self.parse_cigar = parse_cigar
        self.min_align_len = min_align_len
        self.min_aligned_path_len = min_aligned_path_len
        self.min_identity = min_identity
        self.trim_overlap_with_graph = trim_overlap_with_graph
        self.assembly_graph = assembly_graph

        # destination for parsed results
        self.records = []

        # run the parsing function
        logger.info("Parsing alignment ({})".format(self.alignment_format))
        self.parse_alignment_file()

    def parse_alignment_file(self, n_proc=1):
        if n_proc == 1:
            self.parse_alignment_file_single()
        else:
            pass

    def parse_alignment_file_single(self):
        """

        """
        if self.alignment_format == "GAF":
            # store a list of GAFRecord objects made for each line in GAF file.
            with open(self.alignment_file) as input_f:
                for line_split in csv.reader(input_f, delimiter="\t"):
                    gaf = GAFRecord(line_split, parse_cigar=self.parse_cigar)
                    self.records.append(gaf)
        elif self.alignment_format == "SPA-TSV":
            # store a list of SPAligner SPATSVRecord objects made for each line in TSV file.
            with open(self.alignment_file) as input_f:
                for line_split in csv.reader(input_f, delimiter="\t"):
                    # skip those alignment with several non-overlapping subpaths
                    if "," in line_split[1]:
                        continue
                    tsv = SPATSVRecord(line_split)
                    self.records.append(tsv)
        else:
            raise Exception("unsupported format!")

        # filtering records based on min length
        if self.min_aligned_path_len:
            go_r = 0
            while go_r < len(self.records):
                if self.records[go_r].p_align_len < self.min_aligned_path_len:
                    del self.records[go_r]
                else:
                    go_r += 1

        # filtering records based on min length
        if self.min_align_len > self.min_aligned_path_len:
            go_r = 0
            while go_r < len(self.records):
                if self.records[go_r].align_len < self.min_align_len:
                    del self.records[go_r]
                else:
                    go_r += 1

        # filtering GAF records by min identity
        if self.alignment_format == "GAF" and self.min_identity:
            go_r = 0
            while go_r < len(self.records):
                if self.records[go_r].identity < self.min_identity:
                    del self.records[go_r]
                else:
                    go_r += 1

        # filtering records by overlap requirement
        if self.trim_overlap_with_graph:

            # check that assembly_graph is an Assembly class object
            check1 = isinstance(self.assembly_graph, Assembly)
            check2 = self.assembly_graph.overlap()

            # iterate over ... and do ...
            if check1 and check2:
                this_overlap = self.assembly_graph.overlap()
                go_r = 0

                if self.alignment_format == "GAF":
                    while go_r < len(self.records):
                        gaf_record = self.records[go_r]
                        if len(gaf_record.path) > 1:
                            head_v = gaf_record.path[0][0]
                            tail_v = gaf_record.path[-1][0]
                            # if head_v or tail_v does not appear in the graph, delete current record
                            if head_v in self.assembly_graph.vertex_info and tail_v in self.assembly_graph.vertex_info:
                                # if path did not reach out the overlap region between the terminal vertex and
                                # the neighboring internal vertex, the terminal vertex should be trimmed from the path
                                head_vertex_len = self.assembly_graph.vertex_info[head_v].len
                                tail_vertex_len = self.assembly_graph.vertex_info[tail_v].len
                                if head_vertex_len - gaf_record.p_start <= this_overlap:
                                    del gaf_record.path[0]
                                if tail_vertex_len - (gaf_record.p_len - gaf_record.p_end - 1) <= this_overlap:
                                    del gaf_record.path[-1]
                                if not gaf_record.path:
                                    del self.records[go_r]
                                else:
                                    go_r += 1
                            else:
                                del self.records[go_r]
                        else:
                            go_r += 1
                else:
                    while go_r < len(self.records):
                        spa_tsv_record = self.records[go_r]
                        if len(spa_tsv_record.path) > 1:
                            head_v = spa_tsv_record.path[0][0]
                            # if head_v does not appear in the graph, delete current record
                            if head_v in self.assembly_graph.vertex_info:
                                # if path did not reach out the overlap region between the terminal vertex and
                                # the neighboring internal vertex, the terminal vertex should be trimmed from the path
                                head_vertex_len = self.assembly_graph.vertex_info[head_v].len
                                if head_vertex_len - spa_tsv_record.p_start <= this_overlap:
                                    del spa_tsv_record.path[0]
                                if spa_tsv_record.path_align_lengths[-1] <= this_overlap:
                                    del spa_tsv_record.path[-1]
                                if not spa_tsv_record.path:
                                    del self.records[go_r]
                                else:
                                    go_r += 1
                            else:
                                del self.records[go_r]
                        else:
                            go_r += 1

        else:
            logger.warning("assembly graph not available, overlaps untrimmed")

    def __iter__(self):
        for record in self.records:
            yield record
