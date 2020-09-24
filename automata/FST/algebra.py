# Get the algebtra terms
from terms import *
import sjss
import itertools
from unifier import *
import compilation_statistics
try:
    from guppy import hpy
except:
    # Fails using pypy because the module
    # is not supported --- only used for memory
    # footprint debugging anyway
    pass

ALG_DEBUG = True
LEQ_DEBUG = False
# This should probably be enabled for most things, it
# drastically helps avoid exponential blowup for non-SJSS
# graphs.
CACHE_ENABLED = True

# How many permutations should we explore when trying to
# find branch equality?
PERMUTATION_THRESHOLD = 10000

class AlgebraGenerationException(Exception):
    pass

def generate(nodes, edges, start, accept_states, options):
    # Clear the results cache for 'generate_internal'
    clean_caches()

    branches = sjss.compute_branches(nodes, edges, start)
    loops = sjss.compute_loops(nodes, edges, start)
    end_states = sjss.compute_end_states(nodes, edges)

    result = generate_internal(nodes, edges, start, accept_states, end_states, branches, loops, options)
    result = result.normalize()

    compilation_statistics.algebras_compiled += 1

    return result


def clean_caches():
    global results_cache
    global computed_algebras

    results_cache = {}
    computed_algebras = {}


# See the reasoning about caches.  Hopefully this approximation
# of argument equality doesn't cause any super hard to track
# down bugs.
def unique_cache_index_for(edges, start):
    edges = tuple(edges)
    return hash(hash(start) + hash(edges))


# This is a results cache.  In theory, for a truly SJSS
# automata, this isn't needed --- the following function won't
# recurse with arguments that is has already been called with.
# However, in practice, there are structures that result in
# exponential blowup of algebra size wrt. automata size.
# If we converted to SJSS, we would face the brunt of this
# cost, so we don't do that.
# This conversion algorithm handles those case correctly,
# but to avoid an exponential number of calls, we cache
# partial results.
# This is obviously best cleared after running this.
# There are two types of cache, the 'computed_algebras'
# cache, which caches results /within/ a single invocation
# of generate_internal, and 'results_cache', which
# caches recursive results.
computed_algebras = {}
results_cache = {}
hits = 0
node_cache_hits = 0
recursions = 0
def generate_internal(nodes, edges, start, accept_states, end_states, branches_analysis, loops_analysis, options):
    global computed_algebras
    global node_cache_hits

    if CACHE_ENABLED:
        unique_cache_index = unique_cache_index_for(edges, start)
        if unique_cache_index in results_cache:
            global hits
            hits += 1
            return results_cache[unique_cache_index]

    output_lookup = sjss.generate_output_lookup(nodes, edges)
    if ALG_DEBUG:
        global recursions
        recursions += 1
        print("Recursions:")
        print(recursions)
        print("Results cache has: " + str(len(results_cache)) + " entries")
        print("(Hits: " + str(hits))
        print("Branches:")
        print(branches_analysis)
        print("Loops:")
        print(loops_analysis)
        print("End states:")
        print(end_states)

    # Now, go through each branch, and figure out
    # what should happen after it.  This is a DFS.
    nodes_list = [start]
    branch_lookup = generate_branches_by_start_lookup(branches_analysis)
    algebra = None
    algebra_stack = [[Const(0, [])]]
    # This keeps track of the node that each stack element represents.
    algebra_stack_nodes = [None]
    algebra_stack_counts = [1]
    seen = None

    while len(nodes_list) != 0:
        node = nodes_list[0]
        nodes_list = nodes_list[1:]
        try_to_compress = False

        occurances = 0
        for future_node in nodes_list:
            if node == future_node:
                occurances += 1
        if occurances > 10:
            # We are looping somehow --- I think this is a problem
            # if the graph has not been fully SJSS-ified.
            # Not really sure how this happens --- or why it
            # seems to sometimes happen on valid graphs.
            # It could be that this is exponential, and does
            # actually resolve.
            raise AlgebraGenerationException("Graph is not properly preprocessed (or there was a bug) --- Algebra generation in a loop. (detected based on future node-visiting instructions)")
        occurances = 0
        for past_node in algebra_stack_nodes:
            if node == past_node:
                occurances += 1
        if occurances > 20:
            raise AlgebraGenerationException("Graphs is not properly preprocessed (or there was a bug) ---  Algebra generation in a loop (detected based on stack history)")
            # Note:  We now have a case where it is not
            # exponential -- in this case, it is clear
            # that the graph was not SJSS-ified.  Implementing
            # a pass to solve that should solve the problem,
            # although it is not a priority, as a small minority
            # of graphs are not SJSS.

        if CACHE_ENABLED and node in computed_algebras:
            # Set the top of stack to this node
            # and try to compress
            algebra = computed_algebras[node]
            if options.algebra_size_threshold and algebra.size() > options.algebra_size_threshold:
                raise AlgebraGenerationException("The algebra we returned from the cache was too big (see --algebra-size-threshold flag)")

            current_tail = algebra_stack[-1][algebra_stack_counts[-1] - 1]
            algebra_stack[-1][algebra_stack_counts[-1] - 1] = Sum([current_tail, algebra]).normalize()

            try_to_compress = True


            if ALG_DEBUG:
                node_cache_hits += 1
                print "Hit cache for node " + str(node)
                print "Found result " + str(algebra)
        else:
            # Check if we already have a cached result
            # for 'node'
            if ALG_DEBUG:
                print("For node " + str(node))
                print("Algebra stack is: ")
                # This is too big to print for some things.
                # print([[str(i) for i in x] for x in algebra_stack])
                print("Algebra stack indexes are:")
                print(algebra_stack_counts)
                print("Node stack is: ")
                print(algebra_stack_nodes)
                print("Node cache hits so far is:")
                print(node_cache_hits)
                print("Current Algebra is:")
                algebra = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                print(algebra)

            branches_starting_here = branch_lookup[node]

            ends = []
            loops_from_this_node = []
            non_loops_from_this_node = []
            for branch in branches_starting_here:
                # Add the nodes to consider to the nodes list.
                end = branch[-1]

                if isloopstart(branch, loops_analysis):
                    # This is a loop, do not push
                    loops_from_this_node.append(branch)
                elif end != branch[0]:
                    ends.append(end)
                    non_loops_from_this_node.append(branch)
            nodes_list = ends[::-1] + nodes_list
            # If this node has loops, then we need to deal with those.
            if len(loops_from_this_node) > 0:
                # This is a loop.  We only handle loops that
                # have start and end equivalence, transformations
                # to this type of automata are handled in the sjss
                # pass.
                # We need to compute the algebra of the loop, then
                # put it in a product.

                # Get the loop that the branch is part of.
                if ALG_DEBUG:
                    print "Recursing"

                sub_nodes, sub_edges, removed_edges, sub_branches_analysis, sub_loops_analysis = sjss.compute_loop_subregion(nodes, edges, node, loops_analysis, branches_analysis)
                # This is done by recursively considering a much smaller
                # graph with the loop in it.

                # Only recurse with the branches and loops we
                # want to recurse with.  These are
                # branches and loops that have nodes only within
                # the set of branches and loops being used
                # within the loop.

                # Put those on a stack and recurse, we could iterate,
                # but that seems messier, and we kinda figure, 
                # how deep will this stack really go? i.e. for real
                # automata, how many nested loops will there be?
                # I figure not many.
                loop_algebra = generate_internal(sub_nodes, sub_edges, branch[0], accept_states, end_states, sub_branches_analysis, sub_loops_analysis, options)
                if options.algebra_size_threshold and loop_algebra.size():
                    if options.algebra_size_threshold < loop_algebra.size():
                        raise AlgebraGenerationException("Algebra was too big, detected in an intermediate step and aborted.")

                if ALG_DEBUG:
                    print "Recursion done"
                    print "Got " + str(loop_algebra) + " back"

                # There will be a removed edge at the end of the loop
                # algebra linking it back to the start node to allow
                # the analysis to finish.  We need to replace that:
                # This should be able to handle more cases, just need
                # to figure out how to push the removed edge constant
                # into the loop algebra to the appropriate term.

                # We need to construct a branch --- critically,
                # we need to apply the right edge to the end 
                # of each algebra.

                if loop_algebra.isbranch():
                    branch_elems = loop_algebra.options
                else:
                    branch_elems = [loop_algebra]

                # We know that each removed edge will be of
                # the form [last_node_in_loop, loop_start]
                # So we can just add a sum to the end of the loop:
                for i in range(len(branch_elems)):
                    elemn = branch_elems[i]

                    last_edge = elemn.get_last_node()
                    if last_edge:
                        branch_elems[i] = Sum([branch_elems[i], Const(1, [(last_edge, node)])]).normalize()
                    else:
                        # This is likely due to a branch within
                        # the branch --- we really need some
                        # complicated recusion here to 
                        # then go down every
                        # branch and add the + 1 to
                        # every end.
                        pass

                for (src, dst) in removed_edges:
                    if src == dst:
                        # THis means there is a 1-loop,
                        # which was removed from the underlying
                        # analysis, so add it back in.
                        branch_elems.append(Const(1, [(src, dst)]))

                loop_algebra = Sum([loop_algebra, Const(1, [removed_edges[0]])]).normalize()
                if ALG_DEBUG:
                    print "Generated loop algebra is:"
                    print(loop_algebra)

                algebra = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                algebra_stack[-1][algebra_stack_counts[-1] - 1] = Sum([algebra, Product(loop_algebra)]).normalize()

            # If this branch is a dead-end, add that
            # to the result equation:
            if len(non_loops_from_this_node) == 0:
                try_to_compress = True
                if node in end_states:
                    # Save an end state onto the stack.
                    algebra = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                    algebra = Sum([algebra, End()]).normalize() if algebra else End()
                    algebra_stack[-1][algebra_stack_counts[-1] - 1] = algebra
                else:
                    pass
                    # This case happens in subcalls where edges have been trimmed,
                    # so the algorithm doesn't see the end of the graph
                    # even if it exists.


            # Dunno how often this case comes up, since things should
            # be compressed.  Might happen for the  start node anyway
            if len(non_loops_from_this_node) == 1:
                new_linalg = linear_algebra_for(non_loops_from_this_node[0], accept_states)
                # Persist that algebra into the stack.
                current_stack = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                new_alg = new_linalg if current_stack is None else Sum([current_stack, new_linalg]).normalize()
                if options.algebra_size_threshold and new_alg.size() > options.algebra_size_threshold:
                    raise AlgebraGenerationException("Algebra was too big (nonloops is 1 case)")
                algebra_stack[-1][algebra_stack_counts[-1] - 1] = new_alg

            # If this is a branch, go deeper in the algebra stack.
            if len(non_loops_from_this_node) > 1:
                branches_count = len(non_loops_from_this_node)

                # This keeps track of how many branches there
                # are to explore down this path.
                # Get the algebra for each branch
                branch_algebras = []
                added_count = 0
                for branch in non_loops_from_this_node:
                    if branch[-1] == node:
                        # We don't want to handle loops, those
                        # aren't considered as things to walk down
                        # I think this is probably a bug and will have
                        # to be removed later, but the concept
                        # is that this has to mirror the modifications
                        # to the next node stack.
                        continue
                    alg = linear_algebra_for(branch, accept_states)
                    branch_algebras.append(alg)
                    added_count += 1

                if added_count > options.max_branching_factor:
                    # Basically, this was causing exponential blowup in memory usage that was leading to OOM errors.
                    # I think that these errors aren't inherint
                    # to the algebra, but rather to the delayed normalization process.
                    # i.e. I think that some calls to normalize() within this function could
                    # mean leaving this failure counter out.
                    print "Algebra failed due to too many edges in graph --- skipping"
                    compilation_statistics.failed_algebra_computations += 1
                    raise AlgebraGenerationException("Algebra failed to too too many edges")

                algebra_stack_counts.append(added_count)
                algebra_stack.append(branch_algebras)
                algebra_stack_nodes.append(node)

        if try_to_compress:
            # This loop 'builds' the algebra stack by adding things
            # together and creating branches where there are multiple
            # options.
            # There are two cases where we try to compress ---
            # if we have just loaded something from the cache,
            # or if we have reached a dead-end earlier on.
            while algebra_stack_counts[-1] == 1:
                if ALG_DEBUG:
                    print "Compressing at depth " + str(len(algebra_stack_counts))
                # We need to build the element before deleteing it.
                # But we know this just contains a 1.
                del algebra_stack_counts[-1] # delete the last algebra stack.

                # The tail of the algebra stack becomes a branch.
                algebra = algebra_stack[-1]
                if len(algebra) == 1:
                    algebra = algebra[0]
                else:
                    algebra = Branch(algebra).normalize()
                del algebra_stack[-1]

                if options.algebra_size_threshold and algebra.size():
                    if options.algebra_size_threshold < algebra.size():
                        raise AlgebraGenerationException("Algebra was too big, detected in an intermediate step and aborted.")


                if len(algebra_stack_counts) == 0:
                    # we are done :)

                    if CACHE_ENABLED:
                        # (Put it in the cache too
                        results_cache[unique_cache_index] = algebra

                    return algebra


                if CACHE_ENABLED:
                    # Cache the resutls in the local cache 
                    # if we are not returning.
                    node_we_finished = algebra_stack_nodes[-1]
                    if ALG_DEBUG:
                        print "Node finished :", node_we_finished
                        # print "Has algebra", str(algebra)
                    computed_algebras[node_we_finished] = algebra.normalize()
                del algebra_stack_nodes[-1]
                # We have 'completed' a branch here.
                # Combine the algebra we computed with the last algebra
                # on the stack.
                new_head_of_stack = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                if new_head_of_stack is None:
                    # This case is to deal with the shitty instantiation
                    # for the first iteration that leaves a 'None'
                    # at the start of the algebra stack.
                    new_head_of_stack = algebra
                else:
                    new_head_of_stack = Sum([new_head_of_stack, algebra]).normalize()
                algebra_stack[-1][algebra_stack_counts[-1] - 1] = new_head_of_stack


            # Decrement the stack counts.
            algebra_stack_counts[-1] = algebra_stack_counts[-1] - 1

    # We should not reach the end here.
    assert False


def generate_branches_by_start_lookup(branches):
    # Generate a lookup table that indexes the list
    # of branches by the start node.
    lookup = {}

    for branch in branches:
        for node in branch:
            lookup[node] = []
    for branch in branches:
        lookup[branch[0]].append(branch)

    return lookup


# This basically looks to see if the branch 'branch'
# is a prefix to any of the loops analysis loops.
def isloopstart(branch, loops_analysis):
    branchstart = branch[0]

    for loop in loops_analysis[branchstart]:
        # We don't need total equality, just equality
        # in the second node in the loop.
        if len(loop) == 0:
            return True

        # If the branch is a single node large,
        # then all the loops starting from this node
        # count.
        if len(branch) == 1 or loop[1] == branch[1]:
            return True

    return False

# Given a set of states where we know that there
# are no branches, compute some equation
# for them, e.g. 3 + a + 2 + a + e
def linear_algebra_for(branch, accept_states):
    algebra = []
    edges = []
    single_state_count = 0
    last_state = None

    if ALG_DEBUG:
        print "Computing algebra for branch: " + str(branch)

    last_state = branch[0]
    for state in branch[1:]:
        single_state_count = single_state_count + 1
        edges.append((last_state, state))
        last_state = state

        if state in accept_states:
            const = Const(single_state_count, edges)
            algebra.append(const)
            single_state_count = 0
            edges = []
            algebra.append(Accept())

    if single_state_count > 0:
        algebra.append(Const(single_state_count, edges))

    if single_state_count == 0:
        algebra.append(Const(0, []))

    if len(algebra) == 1:
        sum_elt = algebra[0]
    else:
        # Join them together with Sum operations.
        sum_elt = Sum(algebra)

    if ALG_DEBUG:
        print "Computed Algebra is " + str(sum_elt)

    return sum_elt.normalize()


# This is an implementation of the comparison operator ---
# the concept is that if A < B, then  we can use the circuit
# for B to implement A.  This does not have to do with
# the generation of a translator, which will likely
# use effectively the same algorithm.  See the theory
# paper for a description of this algorithm in a sensible
# manner.
# The problem is that some of these things are massive,
# so a recursive implementation would exceed stack limits
# in python.
def leq(A, B, options):
    unifier = leq_unify(A, B, options)
    return unifier is not None


# This MUST support multithreaded operation.
def leq_unify(A, B, options):
    if LEQ_DEBUG:
        print "Starting new unification...."
        print "Comparing ", str(A), " and ", str(B)
        print "(Sizes ", A.size(), B.size(), ")"

    if not options.no_leq_heuristics and leq_fails_on_heuristics(A, B, options):
        compilation_statistics.cutoff_comparisons += 1
        return None

    compilation_statistics.executed_comparisons += 1

    unifier = leq_internal_wrapper(A, B, options)
    if unifier is not None and unifier.isunifierlist:
        return unifier.as_list()
    else:
        return [unifier]

def leq_fails_on_heuristics(A, B, options):
    if A.size() > options.size_difference_cutoff_factor * B.size():
        if LEQ_DEBUG:
            print "Skipping due to size difference"
        return True

    # Check for overlap in the distances to accept states ---
    # no overlap suggests(?) no hope.
    a_accepting_distances = A.accepting_distances_approximation()
    b_accepting_distances = B.accepting_distances_approximation()
    hits = 0
    misses = 0

    # Trim the list sizes if they happen to be really big:
    if len(a_accepting_distances) > 100:
        a_accepting_distances = a_accepting_distances[:100]
    if len(b_accepting_distances) > 1000:
        b_accepting_distances = b_accepting_distances[:1000]

    # turn b_accepting distances into a set so we can use binary search.
    b_accepting_distances = set(b_accepting_distances)

    for distance in a_accepting_distances:
        if distance in b_accepting_distances:
            hits += 1
        else:
            misses += 1
    # A random equation that is aimed at being
    # very generous and not excluding things that
    # have some chance.  Not sure if it achieves that.
    if hits < misses / 2:
        return True

    return False


def leq_internal_fails_on_heuristics(A, B, options):
    # Size threshold, unlikely to be able to compile something
    # big to something small.
    if A.size() > options.size_difference_cutoff_factor * B.size():
        return True

    if A.branches_count() > 1.5 * B.branches_count():
        return True

    if A.loops_count() > 1.5 * B.loops_count():
        return True

    return False

# This MUST support multithreaded operation.
def leq_internal_wrapper(A, B, options):
    global_variables = {
            'comparison_cache': {},
            # This is a counter to help distinguish between calls.
            'leq_internal_id': 0,
            # Keeps track of the depth of the calls
            'leq_calls': 0,
            # Keep track of the depth --- some of the equations are too big
            # for python to handle.
            'leq_depth': 0,
            'solution_ID': hash(A) + hash(B)
    }

    # Computes if A <= B, where A <= B means that we can
    # run A using automata B.
    def leq_internal(A, B, options, use_leq_on_constants=False):
        if options.memory_debug:
            print "Heap in LEQ Internal"
            h = hpy()
            print(h.heap())
        global_variables['leq_depth'] += 1
        global_variables['leq_calls'] += 1
        if global_variables['leq_calls'] > options.leq_calls_threshold:
            if LEQ_DEBUG:
                print "Failing due to too many calls"
            global_variables['leq_depth'] -= 1
            return None

        # Want to avoid massive comparisons: (a) crash (b) slow
        # (c) unlikely to succeed anyway.
        if global_variables['leq_depth'] > 1000:
            # Recursion depth exceeded.
            global_variables['leq_depth'] -= 1
            if LEQ_DEBUG:
                print "Warning: LEQ Recursion depth exceeded"
            return None

        if LEQ_DEBUG:
            print "Entering a new comparison"
            print "Types are ", A.type(), " and ", B.type()
            this_call_id = global_variables['leq_internal_id']
            global_variables['leq_internal_id'] += 1
            print "Entering call ID: " + str(this_call_id)
        cache_pointer = (A.id, B.id)

        # See if we have a cached comparison for these.
        if CACHE_ENABLED and cache_pointer in global_variables['comparison_cache']:
            global_variables['leq_depth'] -= 1
            return global_variables['comparison_cache'][cache_pointer]

        if not options.no_leq_heuristics:
            if LEQ_DEBUG:
                print "Checking for heuristic fails within an individual comparison..."

            if leq_internal_fails_on_heuristics(A, B, options):
                if LEQ_DEBUG:
                    print "Comparison failed on Heuristics! Returning None"

                # Setup the cache and decrement the stack depth counter.
                global_variables['comparison_cache'][cache_pointer] = None
                global_variables['leq_depth'] -= 1
                return None
            elif LEQ_DEBUG:
                print "Comparison passed :)"

        unifier = None
        result = None
        if B.isbranch() and not A.isbranch():
            if LEQ_DEBUG:
                print "B is a branch, trying to find a branch that unifies with A"
            # In this case, we assume that A is not a branch.
            # So, we can check whether we can compile every
            # individual branch, and if it does, then we can
            # disable the other options.
            opt_unifier = None
            selected_unifier = None
            for opt in B.options:
                sub_unifier = leq_internal(A, opt, options)
                if sub_unifier is not None:
                    opt_unifier = opt
                    selected_unifier = sub_unifier
                    break

            # Note that there is some possibility for more
            # generality here, because one of these branch
            # options might be unifiable, while the others
            # may not be.  We've just picked the first, but
            # a simple heuristic may be more than possible.
            if opt_unifier is not None:
                # Create the unifier.
                unifier = selected_unifier
                for opt in B.options:
                    if opt != opt_unifier:
                        # Unify the first edge with None.
                        # Note that there is also scope here for
                        # more flexibility, because we are really
                        # interested in ensuring that it doesn't
                        # get to an unwanted accepting state.
                        first_edges = opt.first_edge()
                        if first_edges:
                            unifier.add_disabled_edges(first_edges)
                result = True
            else:
                # No branch unified.
                unifier = None
                result = False
        elif A.isbranch() and not B.isbranch():
            if LEQ_DEBUG:
                print "A is a branch and B is not a branch -- trying"
                print "to create structural equality between the two."
            # We can compile this, but require that every branch
            # of A compiles to B.
            unifier = UnifierList([Unifier()])
            result = True
            for opt in A.options:
                sub_unifier = leq_internal(opt, B, options)
                if sub_unifier is None:
                    result = False
                else:
                    unifier.unify_with(sub_unifier)
            if not result:
                # Need to clear the unifier:
                unifier = None
        elif A.isconst():
            if LEQ_DEBUG:
                print "A is const:"
            if B.isconst():
                if LEQ_DEBUG:
                    print "B also const, checking equality of:"
                    print A.val
                    print B.val
                if A.val == B.val:
                    result = True
                    unifier = Unifier()
                    unifier.add_edges(B.edges, A.edges)
                elif use_leq_on_constants and B.val < A.val:
                    result = True
                    unifier = Unifier(cost=A.val - B.val)
                    unifier.add_edges(B.edges, A.edges[:len(B.edges)])
                else:
                    result = False
            elif B.isproduct():
                if LEQ_DEBUG:
                    print "B product"
                # This was true, not sure why.
                result = False # True
            else:
                if LEQ_DEBUG:
                    print "B other"
                result = False
        elif A.isend():
            if LEQ_DEBUG:
                print "A is end: unifying the first edge of B to NoMatch"
            result = True
            # We can unify this, but we need to make sure that
            # we can 'disable' that edge.
            unifier = Unifier()
            first_edges = B.first_edge()
            # We don't always need to unify anything from this --- it
            # could be, e.g. that B is also end
            if first_edges is not None:
                unifier.add_disabled_edges(first_edges)
        elif A.isaccept() and B.isaccept():
            if LEQ_DEBUG:
                print "Both Accept"
            result = True
            unifier = Unifier()
        elif A.isproduct() and B.isproduct():
            if LEQ_DEBUG:
                print "Both are products: Unifying subcomponents"
            unifier = leq_internal(A.e1, B.e1, options)
            if unifier is None:
                result = False
            else:
                result = True
        elif A.issum() and B.issum():
            if LEQ_DEBUG:
                print "Both are sums: unifying subsums"
                print "Lenths are ", len(A.e1),  "and", len(B.e1)

            still_equal = True
            unifier = UnifierList([Unifier()])

            a_index = 0
            b_index = 0
            # We don't need equality up to the end here, due
            # the the (trim) rule (i.e. e <= x (provided x != a))
            while still_equal and a_index < len(A.e1) and b_index < len(B.e1):
                # The algorithm here is to progressively increase
                # the range of terms over which we unify in A to the
                # first element in B.  If that doesn't work, then
                # we progressively unify larger terms of B to the
                # first element of A.
                # We want to match the biggest section possible ---
                # e.g. if there is a branch {1, 1 + 1}, we heuristically
                # want to take the longer branch.
                # That said, it shouldn't be too hard to extend
                # this to try all branches --- it might give more coverage.
                # Unfortunately, the algoritm to unify the biggest
                # section possible was really quite slow, especially
                # when considering very long 1 + 1 + 1...
                # I think it's possible to get away with an heuristic
                # here that just looks to see if the first two terms
                # are consts of the same size, and if they are
                # just bumps forward on the equality.
                if LEQ_DEBUG:
                    print "Call ID ", this_call_id
                    print "Staritng a new iteration of the sum checker"
                    print "The indexes are:"
                    print a_index, b_index

                if A.e1[a_index].isconst() and B.e1[b_index].isconst():
                    # Unify and continue:
                    sub_unifier = leq_internal(A.e1[a_index], B.e1[b_index], options)
                    if sub_unifier is not None:
                        # We can just go back around the loop:
                        unifier.unify_with(sub_unifier)
                        a_index += 1
                        b_index += 1
                        continue

                last_element_of_a = len(A.e1)
                found_match_expanding_a = False
                while not found_match_expanding_a and last_element_of_a > a_index:
                    smaller_elements = Sum(A.e1[a_index:last_element_of_a]).normalize(flatten=False)
                    # Now, try to compile:
                    sub_unifier = leq_internal(smaller_elements, B.e1[b_index], options)
                    if sub_unifier is not None:
                        # Eat all the matched elements and continue:
                        found_match_expanding_a = True
                        if LEQ_DEBUG:
                            print "Found match expanding A"
                    else:
                        last_element_of_a -= 1

                if found_match_expanding_a:
                    # Shrink things and move onward :)
                    unifier.unify_with(sub_unifier)

                    a_index = last_element_of_a
                    b_index += 1
                else:
                    # Otherwise, try matching more things of B to
                    # the first element of A.
                    last_element_of_b = len(B.e1)
                    found_match_expanding_b = False

                    while not found_match_expanding_b and last_element_of_b > b_index:
                        smaller_elements = Sum(B.e1[b_index:last_element_of_b]).normalize(flatten=False)
                        sub_unifier = leq_internal(A.e1[a_index], smaller_elements, options)

                        if sub_unifier is not None:
                            if LEQ_DEBUG:
                                print "Found match expanding B"
                            found_match_expanding_b = True
                        else:
                            last_element_of_b -= 1

                    if found_match_expanding_b:
                        unifier.unify_with(unifier)
                        b_index = last_element_of_b - 1
                        a_index += 1
                    else:
                        # No matches found, so termiate
                        if LEQ_DEBUG:
                            print "Unifying sums failed at indexes", a_index, b_index
                        still_equal = False

            # TODO -- Do the tail approximation check.

            # If A is completely used, then we are done.  We might
            # have to disable the first edge out of as far as we got into B.
            if LEQ_DEBUG:
                print "Exited the sum comparison loop --- managed "
                print "to unify up to index ", a_index, b_index
                print "out of ", len(A.e1), len(B.e1)
            if a_index == len(A.e1):
                if b_index != len(B.e1):
                    if LEQ_DEBUG:
                        print "Attempting to apply trim property..."
                    sum_tail = Sum(B.e1[b_index - 1:]).normalize()
                    # Need to disable the first edge.
                    first_edges = sum_tail.first_edge()

                    # And if there is an accept before the first
                    # edge, then we need to fail.
                    if sum_tail.has_accept_before_first_edge():
                        if LEQ_DEBUG:
                            print sum_tail
                            print "Trim property failed because tail has accept before first edge"
                        result = False
                        unifier = None
                    else:
                        if first_edges:
                            unifier.add_disabled_edges(first_edges)
                else: # We used up all of B, so do not
                    # need to add any disabled edges.
                    result = True
            else:
                # TODO -- Apply the tail approximation. For now,
                # we makr this as a fail.
                result = False
                unifier = None
        elif A.isbranch() and B.isbranch():
            if LEQ_DEBUG:
                print "Both are branches, trying all combinations to find a unifying pair"
            elements_A = A.options
            elements_B = B.options

            # Try all matches --- likely need some kind
            # of cutoff here.
            matches = [None] * len(elements_A)
            for i in range(len(elements_A)):
                matches[i] = [None] * len(elements_B)

                for j in range(len(elements_B)):
                    if LEQ_DEBUG:
                        print "Performing initial checks to build matrix for branch at call " + str(this_call_id) + ":"
                        print "Checking ", elements_A[i]
                        print "Checking ", elements_B[j]
                    matches[i][j] = leq_internal(elements_A[i], elements_B[j], options)

            result = False
            # Now, try and find some match for each i element in A.
            perm_count = 0

            # This could be made smarter, by making some sensible guesses
            # about which permutations might work --- there are definitely
            # constraints here, e.g. we expect the matches matrix
            # to be quite sparse.
            if LEQ_DEBUG:
                print "Unification matrix is: (call " + str(this_call_id) + ")"
                for row in matches:
                    print row

            mcount = 0
            found_match = None
            unifier = UnifierList([Unifier()])
            for combination in permutations(len(elements_A), range(len(elements_B))):
                perm_count += 1
                if perm_count > PERMUTATION_THRESHOLD:
                    print "Warning: Permutation fail due to excessive numbers"
                    break
                # check if the combination is good.
                is_match = True
                for i in range(len(combination)):
                    if not matches[i][combination[i]]:
                        is_match = False

                if is_match:
                    # Create the unifier with this sequence of
                    # assignments:
                    this_branch_unifier = UnifierList([Unifier()])
                    used_branches = []
                    for i in range(len(combination)):
                        used_branches.append(combination[i])
                        this_branch_unifier.unify_with(matches[i][combination[i]])

                    # Disable the other edges:
                    for i in range(len(elements_B)):
                        if i not in used_branches:
                            B_first_edges = elements_B[i].first_edge()
                            if B_first_edges:
                                this_branch_unifier.add_disabled_edges(elements_B[i].first_edge())
                            else:
                                # If the first edge isn't set,
                                # then I think we can assume that an accept is somehow happening right away?
                                # like this: 1 + {a, 1 + a}?
                                # TBH not too sure why this case
                                # came up, but a safe thing to do
                                # is reject this match.
                                is_match = False
                                this_branch_unifier = None

                    if this_branch_unifier:
                        mcount += 1
                        # If the unifier still exists, then add it to the overall
                        # unifiers list.
                        unifier.append_unifiers(this_branch_unifier)
            if mcount == 0 or unifier.length() == 0:
                # Clear the unifier.
                unifier = None

        else:
            if LEQ_DEBUG:
                print "Types differ: unification failed"
                print "Types were", A.type(), B.type()
            result = False

        global_variables['comparison_cache'][cache_pointer] = unifier
        if result is None:
            if LEQ_DEBUG:
                print "Failed to produce a comparison for:"
                print A
                print B

        if LEQ_DEBUG:
            print "Exiting call ", this_call_id
            print "Result is ", unifier

        if unifier:
            unifier.set_algebra_from(A)
            unifier.set_algebra_to(B)

        global_variables['leq_depth'] -= 1
        return unifier

    return leq_internal(A, B, options)


# Yield every cpermustations of i numbers up to j.
def permutations(i, j):
    return itertools.product(j, repeat=i)
