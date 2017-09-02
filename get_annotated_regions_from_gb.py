#! /usr/bin/env python

import os
import time
import sys
from Bio import SeqIO, SeqFeature
import os
from optparse import OptionParser


# Copyright(C) 2017 Jianjun Jin


def get_options():
    usage = "Usage: get_gene_igs.py gb_files -o out_dir"
    parser = OptionParser(usage=usage)
    parser.add_option("-o", dest="out_put",
                      help="Output.")
    parser.add_option("-t", dest="gene_types", default="CDS,tRNA,rRNA",
                      help="Annotation type taken as gene. Default: CDS,tRNA,rRNA")
    parser.add_option("--separate-copy", dest="one_copy", default=True, action="store_false",
                      help="By default, only keep the first one if there are several regions with the same name.")
    parser.add_option("--copy-mode", dest="copy_mode", default="longest",
                      help="first or longest (default).")
    parser.add_option("--separate-exon", dest="combine_exon", default=True, action="store_false",
                      help="By default, combining exons.")
    parser.add_option("--ignore-format-error", dest="ignore_format_error", default=False, action="store_true",
                      help="Skip the Error: key \"gene\" not found in annotation. Not suggested.")
    options, argv = parser.parse_args()
    if not options.out_put:
        parser.print_help()
        sys.exit()
    if options.copy_mode not in {"longest", "first"}:
        parser.print_help()
        sys.exit()
    return options, argv


translator = str.maketrans("ATGCRMYKHBDVatgcrmykhbdv", "TACGYKRMDVHBtacgykrmdvhb")


def complementary_seq(input_seq):
    return str.translate(input_seq, translator)[::-1]


def parse_bio_gb_locations(location_feature):
    if type(location_feature) == SeqFeature.CompoundLocation:
        return [parse_bio_gb_locations(location)[0] for location in location_feature.parts]
    elif type(location_feature) == SeqFeature.FeatureLocation:
        return [(int(location_feature.start), int(location_feature.end), location_feature.strand)]
    else:
        raise ValueError(str(type(location_feature)))


def embed_in(candidate_small, candidate_large):
    small_start, small_end = candidate_small
    large_start, large_end = candidate_large
    # both circular
    if small_start >= small_end and large_start >= large_end:
        return small_end <= large_end
    elif small_start >= small_end:
        return False
    elif large_start >= large_end:
        return True
    else:
        return small_end <= large_end


def get_seqs(seq_record, accepted_types, ignore_format_error=False):
    original_seq = str(seq_record.seq)

    def get_seq_with_gb_loc(in_location):
        in_start, in_end, in_strand = in_location
        if in_start >= in_end:
            in_seq = original_seq[in_start:] + original_seq[:in_end]
        else:
            in_seq = original_seq[in_start: in_end]
        if in_strand == 1:
            return in_seq
        else:
            return complementary_seq(in_seq)
    gene_regions = []
    name_counter = {}
    taken_loc = set()
    for feature in seq_record.features:
        if feature.type in accepted_types:
            if "gene" in feature.qualifiers:
                locations = parse_bio_gb_locations(feature.location)
                this_name = [feature.qualifiers["gene"][0], "", ""]
                if this_name[0] not in name_counter:
                    name_counter[this_name[0]] = 1
                else:
                    name_counter[this_name[0]] += 1
                    this_name[1] = "__copy" + str(name_counter[this_name[0]])
                if len(locations) > 1:
                    for i, loc in enumerate(locations):
                        this_name[2] = "__exon" + str(i + 1)
                        if loc not in taken_loc:
                            gene_regions.append([tuple(this_name)] + list(loc) + [get_seq_with_gb_loc(loc)])
                            taken_loc.add(loc)
                else:
                    gene_regions.append([tuple(this_name)] + list(locations[0]) + [get_seq_with_gb_loc(locations[0])])
            elif not ignore_format_error:
                sys.stdout.write("Key \"gene\" not found in annotation:\n")
                sys.stdout.write(str(feature))
                sys.stdout.write("\nUse \"--ignore-format-error\" to ignore this error. Not suggested.\n")
                raise NotImplementedError
    gene_regions.sort(key=lambda x: (x[1], -x[2], x[0]))
    intergenic_regions = []
    end_of_last_region = 0
    if len(gene_regions) == 1:
        if gene_regions[0][1] == gene_regions[0][2]:
            pass
        else:
            anchor1 = [gene_regions[0][0][0], gene_regions[0][0][2], "(-)" if gene_regions[0][3] == 1 else "(+)"]
            anchor2 = [gene_regions[0][0][0], gene_regions[0][0][2], "(+)" if gene_regions[0][3] == 1 else "(-)"]
            this_name = sorted([tuple(anchor1), tuple(anchor2)]) + [""]
            if tuple(this_name[:2]) not in name_counter:
                name_counter[tuple(this_name[:2])] = 1
            else:
                name_counter[tuple(this_name[:2])] += 1
                this_name[2] = "__copy" + str(name_counter[tuple(this_name[:2])])
            this_loc = [gene_regions[0][2], gene_regions[0][1], 1*int(2*((anchor1 <= anchor2) - 0.5))]
            intergenic_regions.append([tuple(this_name)] + this_loc + [get_seq_with_gb_loc(this_loc)])
    elif len(gene_regions) > 1:
        first_region = gene_regions[0]
        circular_regions = [in_region for in_region in gene_regions if in_region[1] >= in_region[2]]
        if circular_regions:
            last_region = sorted(circular_regions, key=lambda x: (-x[2], x[1], x[0]))[0]
            end_of_last_region = last_region[2]
        else:
            last_region = gene_regions[-1]
        # if both of the terminal annotations across the ends (circular), they apparently overlapped
        if first_region[1] >= first_region[2] and last_region[1] >= last_region[2]:
            pass
        # elif embedded
        elif first_region[1] >= first_region[2]:
            pass
        elif last_region[1] >= last_region[2]:
            if last_region[2] >= first_region[1]:
                pass
            else:
                anchor1 = [last_region[0][0], last_region[0][2], "(-)" if last_region[3] == 1 else "(+)"]
                anchor2 = [first_region[0][0], first_region[0][2], "(+)" if first_region[3] == 1 else "(-)"]
                this_name = sorted([tuple(anchor1), tuple(anchor2)]) + [""]
                if tuple(this_name[:2]) not in name_counter:
                    name_counter[tuple(this_name[:2])] = 1
                else:
                    name_counter[tuple(this_name[:2])] += 1
                    this_name[2] = "__copy" + str(name_counter[tuple(this_name[:2])])
                this_loc = [last_region[2], first_region[1], 1*int(2*((anchor1 <= anchor2) - 0.5))]
                intergenic_regions.append([tuple(this_name)] + this_loc + [get_seq_with_gb_loc(this_loc)])
        else:
            anchor1 = [last_region[0][0], last_region[0][2], "(-)" if last_region[3] == 1 else "(+)"]
            anchor2 = [first_region[0][0], first_region[0][2], "(+)" if first_region[3] == 1 else "(-)"]
            this_name = sorted([tuple(anchor1), tuple(anchor2)]) + [""]
            if tuple(this_name[:2]) not in name_counter:
                name_counter[tuple(this_name[:2])] = 1
            else:
                name_counter[tuple(this_name[:2])] += 1
                this_name[2] = "__copy" + str(name_counter[tuple(this_name[:2])])
            this_loc = [last_region[2], first_region[1], 1 * int(2 * ((anchor1 <= anchor2) - 0.5))]
            intergenic_regions.append([tuple(this_name)] + this_loc + [get_seq_with_gb_loc(this_loc)])
    go2 = 0
    while go2 < len(gene_regions) - 1:
        go_add = 1
        while go2 + go_add < len(gene_regions) and embed_in(gene_regions[go2 + go_add][1:3], gene_regions[go2][1:3]):
            go_add += 1
        if go2 + go_add == len(gene_regions):
            break
        this_region, next_region = gene_regions[go2], gene_regions[go2 + go_add]
        if this_region[1] >= this_region[2] and next_region[1] >= next_region[2]:
            pass
        elif this_region[2] < next_region[1] and end_of_last_region < next_region[1]:
            anchor1 = [this_region[0][0], this_region[0][2], "(-)" if this_region[3] == 1 else "(+)"]
            anchor2 = [next_region[0][0], next_region[0][2], "(+)" if next_region[3] == 1 else "(-)"]
            this_loc = [this_region[2], next_region[1], 1 * int(2 * ((anchor1 <= anchor2) - 0.5))]
            this_name = sorted([tuple(anchor1), tuple(anchor2)]) + [""]
            if tuple(this_name[:2]) not in name_counter:
                name_counter[tuple(this_name[:2])] = 1
            else:
                name_counter[tuple(this_name[:2])] += 1
                this_name[2] = "__copy" + str(name_counter[tuple(this_name[:2])])
            intergenic_regions.append([tuple(this_name)] + this_loc + [get_seq_with_gb_loc(this_loc)])
        go2 += go_add
    return gene_regions, intergenic_regions


def write_fasta(out_file, seq_dict):
    names = sorted(list(seq_dict))
    with open(out_file, "w") as out_put_handler:
        for name in names:
            out_put_handler.write(">" + name + "\n" + seq_dict[name] + "\n\n")


def main():
    time0 = time.time()

    options, argv = get_options()
    os.mkdir(options.out_put)
    gene_dir = os.path.join(options.out_put, "gene")
    os.mkdir(gene_dir)
    intergenic_dir = os.path.join(options.out_put, "intergene")
    os.mkdir(intergenic_dir)

    types = set()
    for this_t in options.gene_types.split(","):
        types.add(this_t)
        types.add(this_t.capitalize())
        types.add(this_t.lower())
        types.add(this_t.upper())

    out_gene_dict = {}
    out_intergenic_dict = {}
    for this_gb in argv:
        if os.path.exists(this_gb):
            gb_base_name = os.path.basename(this_gb).replace(".gb", "").replace(".genbank", "")
            this_records = list(SeqIO.parse(this_gb, "genbank"))
            for seq_record in this_records:
                gene_regions, intergenic_regions = get_seqs(seq_record, types, options.ignore_format_error)
                for region_name, start, end, strand, this_seq in gene_regions:
                    if region_name not in out_gene_dict:
                        out_gene_dict[region_name] = {}
                    out_gene_dict[region_name][gb_base_name] = this_seq
                for region_name, start, end, strand, this_seq in intergenic_regions:
                    if region_name not in out_intergenic_dict:
                        out_intergenic_dict[region_name] = {}
                    out_intergenic_dict[region_name][gb_base_name] = this_seq
    #
    if options.one_copy:
        go_to = 0
        sorted_region_names = sorted(list(out_gene_dict), key=lambda x: (x[0], x[2], x[1]))
        while go_to < len(sorted_region_names):
            region_name = sorted_region_names[go_to]
            go_plus = 1
            # if bool(sorted_region_names[go_to + go_plus][1]) == True, multiple copies exist.
            while go_to + go_plus < len(sorted_region_names):
                next_region_name = sorted_region_names[go_to + go_plus]
                if (next_region_name[0], next_region_name[2]) != (region_name[0], region_name[2]):
                    if sorted_region_names[go_to + go_plus][1]:
                        sys.stdout.write("Warning: cannot find " + "".join([next_region_name[0], next_region_name[2]]) +
                                         " while there's " + "".join(next_region_name) + "\n")
                    break
                else:
                    go_plus += 1
            if go_plus > 1:
                for gb_name in out_gene_dict[region_name]:
                    this_seqs = []
                    for go_candidate in range(go_to, go_to + go_plus):
                        if gb_name in out_gene_dict[sorted_region_names[go_candidate]]:
                            this_seqs.append(out_gene_dict[sorted_region_names[go_candidate]][gb_name])
                    if len(set(this_seqs)) > 1:
                        sys.stdout.write("Warning: distinct copies of " + "".join(region_name) + " in " + gb_name + "\n")
                    if options.copy_mode == "longest":
                        out_gene_dict[region_name][gb_name] = sorted(this_seqs, key=lambda x: -len(x))[0]
                for go_del in range(go_to + 1, go_to + go_plus):
                    del out_gene_dict[sorted_region_names[go_del]]
            go_to += go_plus
            # if "__copy" in region_name:
            #     # check identical
            #     for gb_name in out_gene_dict[region_name]:
            #         original_region_name = region_name.split("__")
            #         original_region_name = "__".join(original_region_name[:1] + original_region_name[2:])
            #         if original_region_name not in out_gene_dict:
            #             sys.stdout.write("Warning: distinct copies of "
            #                              + original_region_name + " in " + gb_name + "\n")
            #         elif out_gene_dict[region_name][gb_name] != out_gene_dict[original_region_name][gb_name]:
            #             sys.stdout.write("Warning: distinct copies of "
            #                              + original_region_name + " in " + gb_name + "\n")
            #     del out_gene_dict[region_name]
            # go_to += 1
        go_to = 0
        sorted_inter_names = sorted(list(out_intergenic_dict), key=lambda x: x[:2])
        while go_to < len(sorted_inter_names):
            inter_name = sorted_inter_names[go_to]
            go_plus = 1
            while go_to + go_plus < len(sorted_inter_names):
                next_inter = sorted_inter_names[go_to + go_plus]
                if inter_name[:2] != next_inter[:2]:
                    if sorted_inter_names[go_to + go_plus][2]:
                        sys.stdout.write("Warning: cannot find " + "".join(inter_name[0]) + "--" +
                                         "".join(inter_name[1]) + " while there's " + "".join(next_inter[0]) +
                                         "--" + "".join(next_inter[1]) + "\n")
                    break
                else:
                    go_plus += 1
            if go_plus > 1:
                for gb_name in out_intergenic_dict[inter_name]:
                    this_seqs = []
                    for go_candidate in range(go_to, go_to + go_plus):
                        if gb_name in out_intergenic_dict[sorted_inter_names[go_candidate]]:
                            this_seqs.append(out_intergenic_dict[sorted_inter_names[go_candidate]][gb_name])
                    if len(set(this_seqs)) > 1:
                        sys.stdout.write("Warning: distinct copies of " + "".join(inter_name[0]) + "--" +
                                         "".join(inter_name[1]) + " in " + gb_name + "\n")
                    if options.copy_mode == "longest":
                        out_intergenic_dict[inter_name][gb_name] = sorted(this_seqs, key=lambda x: -len(x))[0]
                for go_del in range(go_to + 1, go_to + go_plus):
                    del out_intergenic_dict[sorted_inter_names[go_del]]
            go_to += go_plus

        # for region_name in list(out_intergenic_dict):
        #     if set(["__copy" in x for x in region_name.split("--")]) == {True}:
        #         del out_intergenic_dict[region_name]
    if options.combine_exon:
        regions_with_exon = [x for x in list(out_gene_dict) if x[2]]
        region_dict = {}
        for region_name in regions_with_exon:
            region_set_name = region_name[:2]
            exon_num = int(region_name[2].replace("__exon", ""))
            if region_set_name not in region_dict:
                region_dict[region_set_name] = []
            region_dict[region_set_name].append(exon_num)
        for region_set_name in region_dict:
            region_dict[region_set_name].sort()
            seq_names = set()
            for exon_num in region_dict[region_set_name]:
                for gb_name in out_gene_dict[tuple(list(region_set_name) + ["__exon" + str(exon_num)])]:
                    seq_names.add(gb_name)
            new_name = tuple(list(region_set_name) + [""])
            if new_name not in out_gene_dict:
                out_gene_dict[new_name] = {}
            for gb_name in seq_names:
                out_gene_dict[new_name][gb_name] = ""
                for exon_num in region_dict[region_set_name]:
                    out_gene_dict[new_name][gb_name] += \
                        out_gene_dict[tuple(list(region_set_name) + ["__exon" + str(exon_num)])].get(gb_name, "")
            for exon_num in region_dict[region_set_name]:
                del out_gene_dict[tuple(list(region_set_name) + ["__exon" + str(exon_num)])]

    for region_name in out_gene_dict:
        write_fasta(os.path.join(gene_dir, "".join(region_name).replace(" ", "_"))+".fasta",
                    out_gene_dict[region_name])
    for region_name in out_intergenic_dict:
        write_fasta(os.path.join(intergenic_dir, "--".join(["".join(x) for x in region_name[:2]]).replace(" ", "_"))
                    + ".fasta", out_intergenic_dict[region_name])

    sys.stdout.write("Time cost: "+str(time.time() - time0) + "\n")

if __name__ == '__main__':
    sys.stdout.write("By jinjianjun@mail.kib.ac.cn 2017\n")
    main()
