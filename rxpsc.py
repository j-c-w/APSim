import argparse
import csv
import logging
import math
import shutil
import sys
import os
import time
import automata.FST.sjss as sjss
import automata as atma
import automata.FST.options as options
import automata.HDL.hdl_generator as hd_gen
import automata.FST.group_compiler as gc
import automata.FST.compilation_statistics as compilation_statistics
import automata.FST.generator.generate_python as generate_python
import automata.FST.passes.pass_list as pass_list

sys.setrecursionlimit(25000)

def extract_file_groups(file_groups, file_input=False, excluding_files=set()):
    assert file_groups is not None
    if file_input:
        assert file_groups not in excluding_files
        file_groups = [file_groups]
    else:
        file_groups = [os.path.join(file_groups, f) for f in os.listdir(file_groups) if os.path.isfile(os.path.join(file_groups, f))]
        for i in range(len(file_groups) - 1, -1, -1):
            if file_groups[i] in excluding_files:
                print "Not including file ", file_groups[i]
                del file_groups[i]

    return file_groups

def extract_automata_components(file_groups, opts):
    automata_components = []

    index = 0
    for file in file_groups:
        if not file.endswith('.anml'):
            continue
        if opts.print_file_info:
            print "Group Index: ", index, "comes from file", file
            index += 1

        automatas = atma.parse_anml_file(file)
        # Need to remove ors to avoid 'special elements' that
        # prevent us from getting the connected components.
        automatas.remove_ors()
        automata_components.append(automatas.get_connected_components_as_automatas())
    return automata_components

def dump_machines(machines, folder, options, selected_indexes=None):
    if not os.path.exists(folder):
        os.makedirs(folder)

    if options.backend == 'python':
        # Generate python simulators:
        print "Generating Python Outputs"
        for i in range(len(machines)):
            conversion = machines[i]
            conversion_path = folder + '/' + str(i) + '/'
            if not os.path.exists(conversion_path):
                os.makedirs(conversion_path)
            for j in range(len(conversion)):
                if selected_indexes is not None:
                    selected_index = selected_indexes[i]
                else:
                    selected_index = None
                cc_group = conversion[j]
                generate_python.write_simulators_for(cc_group, conversion_path + 'machine_' + str(j), selected_indexes=selected_index)
    else:
        assert False # needs to be implemented for new backends.


def clone_automata_components(components):
    new_components = []
    for group in components:
        new_group = []
        for comp in group:
            if comp is None:
                new_group.append(None)
            else:
                new_group.append(comp.clone())
        new_components.append(new_group)
    return new_components


def compute_initial_state_count(automata_components):
    initial_state_count = 0
    for comp in automata_components:
        for cc in comp:
            initial_state_count += len(cc.nodes)
    return initial_state_count


# Given an input file of expressions we wish to accelerate,
# build a set of accelerators for them that can either
# use symbol-only-reconfiguration or input-stream translation
# to achieve more accelerators.
# Input is a set of regexes, output is a set of accelerators
# and conversions (as specified by the flags).
# This tries to create as few accelerators as possible,
# but it is not hard to duplicate certain accelerators
# that have a lot of coverage if there is more space on the FPGA.
def build_accelerators_for(anml_file, options):
    groups = extract_file_groups(anml_file, file_input=True)
    extracted_components = extract_automata_components(groups, options)
    
    # not supported for this accelerator building. --- I expect that they
    # would help for stateless translation approaches.
    assert not options.use_prefix_splitting
    assert not options.use_prefix_merging

    automata_components = gc.wrap_automata(extracted_components, options)
    accelerators, mapping = gc.build_accelerators_for(automata_components, options)

    print "Number of accelerators is ", len(accelerators)
    print "Number of patterns was ", len(automata_components[0])
    if options.print_algebras:
        print "Derived accelerators are:"
        for accelerator in accelerators:
            print accelerator.algebra

    # Print the counters e.g.  with failure reasons.
    print_compile_counters(options)


# This function is designed to take in a single ANML file,
# and assume that every automata in that ANML file is independent.
# Then, it assumes that /one/ regexp from that file is not implemented,
# and the others all are.  It tries to compile the unimplemented
# regexp to the implemented ones.
def run_addition_experiment_anml_zoo(anml_file, options, number_experiments=None):
    groups = extract_file_groups(anml_file, file_input=True)
    extracted_components = extract_automata_components(groups, options)
    # Compute the prefix split for this file --- we'll remove 
    # any splits that were calculated using the experimental
    # automata later.  It's a bit expensive (and unnessecary)
    # to calculate it later.
    print len(extracted_components[0])
    prefix_extracted_components = gc.wrap_automata(clone_automata_components(extracted_components), options)
    print len(prefix_extracted_components[0])
    if options.use_prefix_splitting:
        existing_components = pass_list.ComputeAlgebras.execute(prefix_extracted_components, options)
        print len(existing_components[0])
        split_components = pass_list.PrefixSplit.execute(existing_components, options)
        print len(split_components[0])

    # Should be the case because we expect there to have only
    # been one file.
    assert len(extracted_components) == 1
    experiment_count = 0

    print "ANMLZoo Experiment Mode: Automata Extracted, running experiments!"

    for i in range(0, len(extracted_components[0])):
        if number_experiments is not None and experiment_count > number_experiments:
            print "Completed all requested experiments! (", number_experiments, ")"
            break
        experiment_count += 1

        # Needs to re-cloned every time because the underlying
        # functions change it.
        automata_components = clone_automata_components(split_components)

        # Get the automata we are adding out, but note that
        # we obviously can't just test if we can compile
        # to an accelerator that already has that automata(!)
        # so delete it :)
        add_test_automata = gc.wrap_automata([[extracted_components[0][i]]], options)

        # Go through and delete any prefixes that were extracted
        # just for this automata.  Also delete this automata.
        for j in range(len(automata_components[0]) - 1, -1, -1):
            if automata_components[0][j] is None:
                continue
            if j == i:
                automata_components[0][j] = None
            else:
                # Check if this is a prefix extracted just for this
                # automata (and one other).
                if len(automata_components[0][j].supported_automata) == 2 and \
                        (0, i) in automata_components[0][j].supported_automata:
                    automata_components[0][j] = None


        add_to_check(add_test_automata, automata_components, options)

        print "ANMLZoo Experiment Mode: Experiment complete, trying next one!"


# This function takes every automata in the add_from files,
# and computes whether it /individually/ could be added to
# a set of accelerators specified in the add_to set of files.
def run_addition_experiment(add_from, add_to, options):
    if not os.path.isfile(add_from):
        print "In addition experiments, the rxps you are adding from must be a file"
        print add_from, " is not a file"
        return
    if not os.path.isdir(add_to):
        print "In addition experiments, the rxps yuo are adding to must be a folder with sub-files"
        print add_to, "is a not a folder"
        print "(We deduplicate internally so the file you are adding from can be in the add to folder)"
        return

    from_file_groups = extract_file_groups(add_from, file_input=True)
    to_file_groups = extract_file_groups(add_to, excluding_files=from_file_groups)

    automata_components_from = extract_automata_components(from_file_groups, options)
    automata_components_to = extract_automata_components(to_file_groups, options)

    automata_components_to = gc.wrap_automata(automata_components_to, options)
    if options.use_prefix_splitting:
        automata_components_to = pass_list.ComputeAlgebras.execute(automata_components_to, options)
        automata_components_to = pass_list.PrefixSplit.execute(automata_components_to, options)

    print "Trying to convert ", len(automata_components_from[0]), "automata"

    # Run each individual experiment:
    for i in range(len(automata_components_from)):
        for j in range(len(automata_components_from[i])):
            # The to components need to be recloned every time, since the underlying
            # functions change it (doh)
            print "Checking..."
            from_group = gc.wrap_automata([[automata_components_from[i][j]]], options)
            add_to_check(from_group, clone_automata_components(automata_components_to), options)
    print "Finished experiment run!"


# This function takes automata to add, and automata to add_to,
# where we assume that add_to is already on an accelerator.
# We treat the 'add_from' group as we would any normal group ---
# that is that elements do not have to be run at the same time
# unless they come from the same folder/file, in which case
# the do have to be run at the same time.
def add_to(add_from, add_to, options):
    from_file_groups = extract_file_groups(add_from)
    to_file_groups = extract_file_groups(add_to)

    automata_components_from = extract_automata_components(from_file_groups, options)
    automata_components_to = extract_automata_components(to_file_groups, options)

    add_to_check(automata_components_from, automata_components_to, options)


dump_index = 0
def add_to_check(automata_components_from, automata_components_to, options):
    if options.time:
        start_time = time.time()
    # Only support one group at a time right now.
    assert len(automata_components_from) == 1
    conversions = gc.compile_to_existing(automata_components_from, automata_components_to, options)

    if options.time:
        print "TIMING: Time taken ", time.time() - start_time

    # Check that all the conversions are individually not none.
    failed = False
    for conv in conversions:
        if conv is None:
            failed = True

    if options.compression_stats or options.print_regex_injection_stats:
        if failed:
            print "COMPRESSION RESULT: Failed to convert regexes to the existing automata"
        else:
            print "COMPRESSION RESULT: Converted regexes to the existing automata!"

    # Also dump the backend output if that is requested.
    if not failed and options.backend != 'none':
        global dump_index
        folder = options.output_folder + '/generated_' + str(dump_index)
        original_folder = options.output_folder + '/original_' + str(dump_index)

        dump_index += 1
        # For the conversions, select the translators where
        # they exist --- note that since we assume every expression
        # in is part of the same group, we know that there will
        # be at most one translator per conversion.
        selected_indexes = []
        for conversion in conversions:
            for ccgroup in conversion:
                assert len(ccgroup.translators) == 1
                assert ccgroup.translators[0] is not None
            # Enable the first translator.
            selected_indexes.append(set([1]))

        dump_machines(conversions, folder, options, selected_indexes=selected_indexes)

        original_machines = [[gc.CCGroup(m.automata, None)] for m in automata_components_from[0]]
        dump_machines(original_machines, original_folder, options)


def compress(file_groups, file_input=False, options=None):
    start_time = time.time()
    file_groups = extract_file_groups(file_groups, file_input)
    print "Extracting ", len(file_groups), " groups"
    # Output is: HDL file with the important automata
    # selected + table programming.

    automata_components = extract_automata_components(file_groups, options)

    # State count of unoptimized regexes.
    initial_state_count = compute_initial_state_count(automata_components)

    assignments = gc.compile(automata_components, options)

    if assignments is None:
        print "Compilation finished --- Assignments was None, probably due to a command line flag not asking for the entire compilation"
        return

    if options.compression_stats:
        self_compiles = len(assignments)
        other_compiles = 0
        nodes_required = 0
        nodes_saved_by_sst = 0
        for assignment in assignments:
            other_compiles += len(assignment.translators)
            nodes_required += len(assignment.physical_automata.nodes)
            for supported_automata in assignment.supported_automata:
                nodes_saved_by_sst += len(supported_automata.nodes)
        # Don't print the results of the comparison if we are doing --compile-only (which skips the comparisons)
        if not options.compile_only:
            print "COMPILATION STATISTICS: self compiles = ", self_compiles
            print "COMPILATION STATISTICS: other compiles = ", other_compiles
            print "COMPILATION STATISTICS: reduction in regexes (from translation) = ", other_compiles - self_compiles
            # The underlying hardware accelerator nodes
            # are double counted since it is also in the 'supported'
            # list.
            print "COMPILATION STATISTICS: total states required = ", nodes_required
            print "COMPLIATION STATISTICS: total states saved = ", initial_state_count - nodes_required
            print "COMPILATION STATISTICS: total states saved by translation = ", nodes_saved_by_sst - nodes_required

        print "COMPILATION STATISTICS: unifications = ", compilation_statistics.unification_successes
        print "COMPILATION STATISTICS: Of those,  ", compilation_statistics.exact_same_compilations, " were equal"
        print "Tried to cross compile ", compilation_statistics.executed_comparisons, "regexes to each other"
        print "Successfully  compiled", compilation_statistics.algebras_compiled, "algebras"
        print "Avoided ", compilation_statistics.cutoff_comparisons, "detailed comparison attempts with heuristics"
        print "Of the algebras ", compilation_statistics.failed_algebra_computations, " failed (likely) due to incompleteness of current implementation"

    print_compile_counters(options)

    if options.time:
        print "Time taken was", time.time() - start_time


def print_compile_counters(options):
    print_unification_statistics(options)
    print_leq_failure_reasons(options)


def print_unification_statistics(options):
    if options.print_unification_statistics:
        print "Single state completeness fails", compilation_statistics.ssu_complete_mapping_failed
        print "Single state correctness fails", compilation_statistics.ssu_correct_mapping_failed
        print "Single state structural modifications unification failed", compilation_statistics.ssu_additions_failed
        print "Single state disable edges failed", compilation_statistics.ssu_disable_edges_failed
        print "Single state disable symbols failed", compilation_statistics.ssu_disable_symbols_failed
        print "Single state structural additon completeness fail", compilation_statistics.ssu_addition_completeness_fail
        print "Single state disable addition symbols failed", compilation_statistics.ssu_addition_correctness_fail
        print "Single state addition failures due to homogeneity preservation", compilation_statistics.ssu_structural_addition_homogeneity_fail
        print "Single state comparisons avoided with heuristics", compilation_statistics.ssu_heuristic_fail
        print "Single state successes", compilation_statistics.ssu_success

def print_leq_failure_reasons(options):
    if options.print_leq_failure_reasons:
        prefix = "LEQ Failure Reason:"
        print prefix, "Recursion Depth Exceeded", compilation_statistics.recursion_depth_exceeded
        print prefix, "Single Arm to Branch not Found", compilation_statistics.single_arm_to_branch_not_found
        print prefix, "Branch to Single Arm not Possible", compilation_statistics.branch_to_single_arm_not_possible
        print prefix, "Const to Non-Const", compilation_statistics.const_to_non_const
        print prefix, "Product to Product Failed", compilation_statistics.product_to_product_failed
        print prefix, "Sum Failed", compilation_statistics.sum_failure
        print prefix, "Branch to Branch Failure", compilation_statistics.branch_to_branch_failure
        print prefix, "Types differ", compilation_statistics.types_differ
        print prefix, "Accept to non-accept", compilation_statistics.accept_to_non_accept
        print prefix, "Const to Sum", compilation_statistics.const_to_sum_failed
        print prefix, "Sum to Sum", compilation_statistics.sum_to_const_failed

        print prefix, "Can't Insert Branch over node modifier/complex branch", compilation_statistics.no_branch_over_node_mmodifiers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    compress_parser = subparsers.add_parser('compress', help="Given a set of groups of regexes, try to statically compress the whole group as much as possible")
    compress_parser.set_defaults(mode='compress')
    compress_parser.add_argument('anml_file_groups')
    compress_parser.add_argument('-f', default=False, action='store_true', dest='file_input', help='Use a file as input rather than a folder.')


    addition_parser = subparsers.add_parser('addition', help="Given a set of implemented regular expressions, and a regular expression to add to the implemented set, try to add the regex using a translator")
    addition_parser.set_defaults(mode='addition')
    addition_parser.add_argument('addition_file', help="File with the automata to be added")
    addition_parser.add_argument('accelerator_file', help='File with the automata currently accelerated (in different groups)')

    addition_experiment_parser = subparsers.add_parser('addition-experiment', help='Given a regex file, try converting every regex in that file to the other groups /individually/. ')
    addition_experiment_parser.set_defaults(mode='addition-experiment')
    addition_experiment_parser.add_argument('addition_file', help='File with the automatas to be test-added')
    addition_experiment_parser.add_argument('accelerator_file', help='File with the automata currently accelerated (in different groups)')

    addition_experiment_anml_zoo_parser = subparsers.add_parser('addition-experiment-anml-zoo', help='Given an ANMLZoo ANML file, try converting every regex in that file, assuming that every other one in that file has been fixed in hardware')
    addition_experiment_anml_zoo_parser.set_defaults(mode='addition-experiment-anml-zoo')
    addition_experiment_anml_zoo_parser.add_argument('anml_file')
    addition_experiment_anml_zoo_parser.add_argument('--experiments', help="How many experiments to run (at max?) by default runs all", default=None, type=int, dest='number_experiments')

    build_accelerators_parser = subparsers.add_parser('build-accelerators', help="Given an ANML file, compute the smallest set of accelerators that can accelerate all the entries in that file, using some multiplexing mode (e.g.  symbol-only-reconfiguration  or input-stream translation)")
    build_accelerators_parser.set_defaults(mode='build-accelerators')
    build_accelerators_parser.add_argument('anml_file')

    options.add_to_parser(compress_parser)
    options.add_to_parser(addition_parser)
    options.add_to_parser(addition_experiment_parser)
    options.add_to_parser(addition_experiment_anml_zoo_parser)
    options.add_to_parser(build_accelerators_parser)

    args = parser.parse_args()
    opts = options.create_from_args(args)

    if args.mode == 'compress':
        compress(args.anml_file_groups, args.file_input, opts)
    elif args.mode == 'addition':
        add_to(args.addition_file, args.accelerator_file, opts)
    elif args.mode == 'addition-experiment-anml-zoo':
        run_addition_experiment_anml_zoo(args.anml_file, opts, number_experiments=args.number_experiments)
    elif args.mode == 'build-accelerators':
        build_accelerators_for(args.anml_file, opts)
    else:
        run_addition_experiment(args.addition_file, args.accelerator_file, opts)
