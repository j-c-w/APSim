import automata as atma
import sjss
import algebra
import time
import unifier
import generate_fst
import compilation_statistics
import simple_graph
import FST
import automata.FST.simulator.simulate_automata as simulator
try:
    from guppy import hpy
except:
    # Fails using pypy because the module
    # is not supported --- only used for memory
    # footprint debugging anyway
    pass


def compile(from_atma, to_atma, options):
    # Compare the shape of the autmata.  If the aren't roughly
    # the same shape, compiling won't work very well.
    depth_eqn_from = compute_depth_equation(from_atma, options)
    depth_eqn_to = compute_depth_equation(to_atma, options)

    if not depth_eqn_from:
        return None

    if not depth_eqn_to:
        return None

    if options.print_algebras:
        print "Compiling from ", depth_eqn_from
        print "Compiling to ", depth_eqn_to

    return compile_from_algebras(depth_eqn_from, from_atma, depth_eqn_to, to_atma, options)


def prefix_unify(from_alg, from_atma, symbol_lookup_from, to_alg, to_atma, symbol_lookup_to, options, can_end_in_accept=False):
    if not options.use_inline_unification_heuristics:
        symbol_lookup_from = None
        symbol_lookup_to = None

    prefix, post_to, post_from, unification = algebra.prefix_unify(to_alg, symbol_lookup_to, from_alg, symbol_lookup_from, options, can_end_in_accept=can_end_in_accept)

    if unification is None:
        return None, from_alg, to_alg, None, generate_fst.GenerationFailureReason("Structural Failure")
    else:
        result, failure_reason = generate_fst.generate(unification, to_atma, from_atma, options)
        if result is None:
            # in the case of unification failure, we need to return the original algebras,
            # not the ones that have been spuriously broken up.
            return None, from_alg, to_alg, None, generate_fst.GenerationFailureReason("Unification Failure")

        if result:
            compilation_statistics.unification_successes += 1

            if options.verify:
                prefix_fst = algebra.full_graph_for(prefix, symbol_lookup_to)

                # Need to show that both automata are the same
                # under this particular prefix split.  Note
                # that we can skip if either tail is empty, that
                # just means the whole automata got used up.
                if post_from is not None:
                    postfix_fst_from = algebra.full_graph_for(post_from, symbol_lookup_from)
                    if len(postfix_fst_from.edges) == 0:
                        print "Got a zero-length postfix!"
                        print post_from
                        print postfix_fst_from
                        assert False

                    verify_prefix_fst(prefix_fst, postfix_fst_from, from_atma, result, options)

                if post_to is not None:
                    postfix_fst_to = algebra.full_graph_for(post_to, symbol_lookup_to)
                    if len(postfix_fst_to.edges) == 0:
                        print "Got a zero-length postfix!"
                        print post_to
                        print type(post_to)
                        print post_to.type()
                        print postfix_fst_to
                        assert False
                    verify_prefix_fst(prefix_fst, postfix_fst_to, to_atma, result, options, prefix_and_postfix_come_from_same_automata=True)
        return prefix, post_from, post_to, result, failure_reason


def compare(eqn_from, eqn_to):
    return algebra.leq(eqn_from, eqn_to)


def compile_from_algebras(eqn_from, automata_from, eqn_to, automata_to, options):
    # These optional lookup tables are a violation of the
    # two-phase separation for unification --- they do a small
    # amount of character-unification in the structural
    # unification phase to help keep the length of the unifier
    # lists down, by removing obviously impossible unifiers
    # sooner rather than later.
    if options.use_inline_unification_heuristics:
        lookup_table_from = automata_from.symbol_lookup
        lookup_table_to = automata_to.symbol_lookup
    else:
        lookup_table_from = None
        lookup_table_to = None

    if options.leq_mode == 'Match':
        unification = algebra.leq_unify(eqn_from, eqn_to, options, from_symbols_lookup=lookup_table_from, to_symbols_lookup=lookup_table_to)
    elif options.leq_mode == 'Merge':
        unification = algebra.leq_merge(eqn_from, eqn_to, options)
    else:
        # Unknown unification type
        assert False

    if unification is None:
        return None, generate_fst.GenerationFailureReason("Structural Failure")
    else:
        # Use the unification to generate an FST if possible.
        result, failure_reason = generate_fst.generate(unification, automata_to, automata_from, options)
        if result:
            # Debugging issues with which accelerator is which.
            # for option in result.modifications.all_modifications():
            #     for edge in option.edges_after:
            #         assert edge in simple_graph.fromatma(automata_to).edges
            compilation_statistics.unification_successes += 1

            if options.verify:
                verify_fst(automata_to, automata_from, result, options)
        return result, failure_reason


def read_verification_inputs(options):
    with open(options.verify, 'r') as f:
        for input in f.readlines():
            input = input[:-1] # Delete the newline at the end of each input.
            yield input


def verify_prefix_fst(prefix, postfix, original, prefix_translator, options, prefix_and_postfix_come_from_same_automata=False):
    assert options.target == 'single-state'

    for input in read_verification_inputs(options):
        if prefix_and_postfix_come_from_same_automata:
            # Don't translate --- this is the original automata, just
            # with an intermediate accept now!
            translated = input
        else:
            translated = prefix_translator.apply(input)

        # Note that we have to specially modify the accelerator
        # to take states with no exit point as accepts due
        # to the chaining issue (i.e. that we envision the
        # prefix and postfix as connected with different
        # input streams, but we don't realize that).
        prefix_accepts = simulator.accepts(prefix, translated)
        postfix_accepts = simulator.accepts(postfix, input)

        original_accepts = simulator.accepts(original, input)

        print "For input ", input
        print "Original answer is", original_accepts
        print "Translated stream is ", translated
        print "prefix accepts is", prefix_accepts
        print "postfix accepts is", postfix_accepts

        if original_accepts:
            if not (prefix_accepts and postfix_accepts):
                print prefix
                print postfix
                print original
                print prefix_translator
                assert False


# Ensure that the expected outputs are the same as the
# post-translation results.
def verify_fst(accelerator, automata, translator, options):
    # Don't verify automata that require structural modification,
    # a lot more work is needed before an 'actual' FST for
    # those automata is generated.
    if translator.has_structural_additions():
        return None

    # Don't currently support verification for other targets.
    assert options.target == 'single-state'
    for input in read_verification_inputs(options):
        original = simulator.accepts(simple_graph.fromatma(automata), input)
        translated_input = translator.apply(input)
        accelerated = simulator.accepts(simple_graph.fromatma(accelerator), translated_input)

        print "For input ", input
        print "Original answer is", original
        print "Translated stream is ", translated_input
        print "Accelerated answer is", accelerated

        if options.correct_mapping:
            assert original == accelerated
        else: # In overapproximation mode
            if original:
                assert accelerated


depth_equation_computation_index = 0
def compute_depth_equation(atma, options, dump_output=False):
    # Get the nodes, edges, starting and accepting states.
    # Convert them to straight up integers to make everything
    # else faster.
    if dump_output:
        print "Generating from :" + str(atma.nodes)
        print "and: " + str(atma.edges)
        print "with start: " + str(atma.start)
        print "and end: " + str(atma.accepting_state)
    if options.dump_nodes_and_edges:
        global depth_equation_computation_index

        dump_draw_function(options.dump_nodes_and_edges, depth_equation_computation_index, atma.nodes, atma.edges)

        depth_equation_computation_index += 1

    if len(atma.nodes) > options.graph_size_threshold:
        print "Graph is too large for current implementation --- skipping"
        print "Graph is ", len(atma.nodes), "and limit is ", options.graph_size_threshold, "nodes"
        print "Increase with --graph-size-limit <N>"
        compilation_statistics.graph_too_big += 1
        return None
 
    start_time = time.time()
    if options.skip_on_fail:
        try:
            alg = algebra.generate(atma.nodes, atma.edges, atma.start_state, atma.accepting_states, options)
        except Exception as e:
            if options.dump_failing_nodes_and_edges:
                dump_draw_function(options.dump_failing_nodes_and_edges, compilation_statistics.failed_algebra_computations, atma.nodes, atma.edges)
            compilation_statistics.failed_algebra_computations += 1
            print "Compilation of algebra failed!"
            print "Error was:"
            print e
            return None
    else:
        alg = algebra.generate(atma.nodes, atma.edges, atma.start_state, atma.accepting_states, options)
    end = time.time()
    if dump_output:
        print "Time taken is " + str(end - start_time)
        if alg.size() > 1000:
            print "Ommitting Algebra --- very long"
            print "(Size was) " + str(alg.size())
        else:
            print "Generated Algebra: " + str(alg)

    return alg

# Create a function to visualize this graph in graphviz.
def dump_draw_function(filename, automata_number, nodes, edges):
    with open(filename, 'a') as f:
        f.write("nodes" + str(automata_number) + " = " + str(nodes) + "\n")
        f.write("edges" + str(automata_number) + " = " + str(edges) + "\n")
        f.write("""
def draw_{num}(fname):
    import automata.FST.debug as debug
    res = debug.to_graphviz(nodes{num}, edges{num})
    with open(fname, 'w') as f:
        f.write(res)
""".format(num=automata_number))
