# Get the algebtra terms
from simple_graph import SimpleGraph
from terms import *
from unifier import *
import compilation_statistics
import group_compiler
import itertools
import single_compiler
import sjss
try:
    import line_profiler
    from guppy import hpy
except:
    # Fails using pypy because the module
    # is not supported --- only used for memory
    # footprint debugging anyway
    pass

ALG_DEBUG = True
LEQ_DEBUG = True
DEBUG_PREFIX_MERGE = False
# This should probably be enabled for most things, it
# drastically helps avoid exponential blowup for non-SJSS
# graphs.
CACHE_ENABLED = True

# How many permutations should we explore when trying to
# find branch equality?
PERMUTATION_THRESHOLD = 10000

profiler = None

class AlgebraGenerationException(Exception):
    pass

class UnsupportedAlgebraException(Exception):
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
            if options.use_size_limits and options.algebra_size_threshold and algebra.size() > options.algebra_size_threshold:
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
                print([[str(i) for i in x] for x in algebra_stack])
                print("Algebra stack indexes are:")
                print(algebra_stack_counts)
                print("Node stack is: ")
                print(algebra_stack_nodes)
                print("Node cache hits so far is:")
                print(node_cache_hits)
                print("Current Algebra is:")
                algebra = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                print(algebra)
                print "Branch lookup is:"
                print(branch_lookup)

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
                if ALG_DEBUG:
                    print "Sub-edges are ", sub_edges
                    print "Removed edges are", removed_edges
                    print "Sub-branches analysis is", sub_branches_analysis
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
                if options.use_size_limits and options.algebra_size_threshold and loop_algebra.size():
                    if options.use_size_limits and options.algebra_size_threshold < loop_algebra.size():
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

                for (src, dst) in removed_edges:
                    if src == dst:
                        # THis means there is a 1-loop,
                        # which was removed from the underlying
                        # analysis, so add it back in.
                        branch_elems.append(Const(0, []))
                        if ALG_DEBUG:
                            print "Found a self-loop"

                # We know that each removed edge will be of
                # the form [last_node_in_loop, loop_start]
                # So we can just add a sum to the end of the loop:
                for i in range(len(branch_elems)):
                    elemn = branch_elems[i]

                    if elemn.isconst() and elemn.val == 0:
                        # This happens e.g. with a self-loop.
                        last_node = node
                    else:
                        last_node = elemn.get_last_node()
                        assert elemn.get_first_node() == node

                    if ALG_DEBUG:
                        print "Getting last node from.. ", elemn
                        print "Appending edge: ", last_node, ", ", node, "to each element"
                    if last_node is not None:
                        assert (last_node, node) in edges
                        branch_elems[i] = Sum([branch_elems[i], Const(1, [(last_node, node)])])

                        # Also check if we need to add a '+ a' to
                        # the end.
                        if node in accept_states:
                            branch_elems[i].e1.append(Accept())

                        branch_elems[i] = branch_elems[i].normalize()
                    else:
                        # THe comment here used to read
                        # that this was probably a branch,
                        # and that in that case, we would need to
                        # go and do more work by appending an element
                        # to each option in the branch.  However, I'm not sure
                        # that is the case, and the things
                        # I've seen here are mostly Const(0) and
                        # End()/ Sum(End())
                        if ALG_DEBUG:
                            print "Last node was None, and that happened in this structure:"
                            print elemn

                        assert not elemn.isbranch()
                        pass

                loop_algebra = Product(Branch(branch_elems)).normalize()
                if ALG_DEBUG:
                    print "Generated loop algebra is:"
                    print "(From node ", node, ")"
                    print(loop_algebra)
                    print "Edges represented are", loop_algebra.all_edges()

                # Increment the stack with this loop algebra on top.:
                algebra_stack.append([loop_algebra])
                algebra_stack_counts.append(1)
                algebra_stack_nodes.append(node)

            # If this branch is a dead-end, add that
            # to the result equation:
            if len(non_loops_from_this_node) == 0:
                if ALG_DEBUG:
                    print "Non-loops from this node is 0, getting ready to compress"
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
                if ALG_DEBUG:
                    print "Non loops from this node is 1 --- continuing"
                    print "Node is", node
                    print "Non-loops are", non_loops_from_this_node

                new_linalg = linear_algebra_for(non_loops_from_this_node[0], accept_states)
                # Persist that algebra into the stack.
                current_stack = algebra_stack[-1][algebra_stack_counts[-1] - 1]
                new_alg = new_linalg if current_stack is None else Sum([current_stack, new_linalg]).normalize()
                if options.use_size_limits and options.algebra_size_threshold and new_alg.size() > options.algebra_size_threshold:
                    raise AlgebraGenerationException("Algebra was too big (nonloops is 1 case)")
                algebra_stack[-1][algebra_stack_counts[-1] - 1] = new_alg

            # If this is a branch, go deeper in the algebra stack.
            if len(non_loops_from_this_node) > 1:
                if ALG_DEBUG:
                    print "Non-loops from this node gt 1, getting ready to expand search"
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

                if options.use_size_limits and added_count > options.max_branching_factor:
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

                if options.use_size_limits and options.algebra_size_threshold and algebra.size():
                    if options.use_size_limits and options.algebra_size_threshold < algebra.size():
                        raise AlgebraGenerationException("Algebra was too big, detected in an intermediate step and aborted.")


                if len(algebra_stack_counts) == 0:
                    # we are done :)

                    if CACHE_ENABLED:
                        # (Put it in the cache too
                        results_cache[unique_cache_index] = algebra

                    return algebra

                node_we_finished = algebra_stack_nodes[-1]
                del algebra_stack_nodes[-1]

                if CACHE_ENABLED:
                    # Cache the resutls in the local cache
                    # if we are not returning.
                    # Don't put this into the cache unless
                    # it is the last time we need to compress
                    # for this node:
                    if node_we_finished not in algebra_stack_nodes:
                        if ALG_DEBUG:
                            print "Node finished :", node_we_finished
                            print "Has algebra", str(algebra)
                            print "Entering in cache..."
                        computed_algebras[node_we_finished] = algebra.normalize()
                    else:
                        if ALG_DEBUG:
                            print "Call was finished and compressed, but node ", node_we_finished, " still has work to be done."
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

# Given an algebra, and a symbol lookup for it, estimate
# the acceptance rate of that algebra for a random string
# of characters.  Note that since we are dealing with NFAs,
# the acceptance rate /can be higher/ than 1.0 (ie. we could
# get multiple accepts for a string)
# See inline comments, but this actually turns out to eb
# more like 1 - rejection probability, which is slightly
# different (e.g. for algebras that do not have accept statements)
def acceptance_rate(algebra, symbol_lookup):
    if algebra.isaccept():
        return 1.0
    elif algebra.isend():
        # This is of course not strictly true.  Perhaps
        # this should be seen as '1 - likelyhood to reject something'.
        return 1.0
    elif algebra.isconst():
        # Again, not strictly 'accepting rate', more like 1 - reject rate.
        assert algebra.val == 1
        # What fraction of charactrs active this edge?
        fraction = float(len(symbol_lookup[algebra.edges[0]])) / 256.0
        return fraction
    elif algebra.isbranch():
        accept_odds = 0.0
        for opt in algebra.options:
            # I get the feeling we might have FP errors here...
            # Hopefully doesn't matter since this is an heuristic.
            accept_odds += acceptance_rate(opt, symbol_lookup)
        return accept_odds
    elif algebra.issum():
        accept_odds = 1.0
        for e in algebra.e1:
            sub_odds = acceptance_rate(e, symbol_lookup)
            accept_odds *= sub_odds
        return accept_odds
    elif algebra.isproduct():
        # This doesn't reduce accepting chances at all, just
        # stick with 1., i.e., there could be some accepts
        # in it, but mainly it doesn't have some non-zero chance
        # of getting derailed.
        return 1.0
    else:
        assert False


# This is an alternative to the below algorithm taht supporst
# generation of a full graph from an APA, but doesn't give you
# the final node (expect that would not be hard to achieve)
def full_graph_for(algebra, symbol_lookup):
    symbol_lookup = dict(symbol_lookup) # Deep copy the symbol lookup
    edges = set(algebra.all_edges())
    start_state = algebra.get_first_node()
    nodes = set()

    for (from_n, to_n) in set(edges):
        if from_n == start_state and start_state != 0:
            if from_n == 97 and to_n == 108:
                print "Found node you are looking for"
            symbol_lookup[(0, to_n)] = symbol_lookup[(from_n, to_n)]
            del symbol_lookup[(from_n, to_n)]
            edges.remove((from_n, to_n))
            from_n = 0
            edges.add((from_n, to_n))
        nodes.add(to_n)
        nodes.add(from_n)
    # We have turned the start state into 0 by here.
    start_state = 0

    accepting_states = algebra.get_accepting_nodes()
    for edge in edges:
        assert edge in symbol_lookup

    return SimpleGraph(nodes, edges, symbol_lookup, accepting_states, start_state)

# This generates a graph for a linear section of algebra.
# It could be a full inverse to the algebra generation algorithm,
# but it really doesn't need to be given that the current
# usecase is small extensions to graphs.
# Returns: nodes, edges, start_states, accept_states, symbols, end_nodes
def graph_for(algebra, symbol_lookup):
    edges = set()
    accept_states = set()
    result_lookup = {}
    last_nodes = set()
    end_nodes = set()

    node_counter = 1
    # Create the start node:
    start_node = 0
    start_state = start_node
    nodes = set([start_node])
    if algebra.issum():
        last_node = start_node
        for obj in algebra.e1:
            if obj.isconst():
                assert obj.val == 1 # Can support non-1 consts,
                # but don't need to with current normalization policies.
                new_node = node_counter
                node_counter += 1

                nodes.add(new_node)
                edges.add((last_node, new_node))
                result_lookup[(last_node, new_node)] = symbol_lookup[obj.edges[0]]
                # Move the node along one for the next term.
                last_node = new_node
            elif obj.isaccept():
                accept_states.add(last_node)
            elif obj.isend():
                last_nodes.add(last_node)
            elif obj.isproduct() and obj.e1.isconst():
                edges.add((last_node, last_node))

                result_lookup[(last_node, last_node)] = symbol_lookup[obj.e1.edges[0]]

                last_node = new_node
            else:
                # We could support the generation of a graph
                # from more complex algebras, but choose
                # not to due to the unnessecary implementation
                # complexity.  We expect that we get most
                # of the benefit from supporting small
                # extensions anyway.
                raise UnsupportedAlgebraException()
        end_nodes = [last_node]
    elif algebra.isconst():
        # Return a two-node graph.
        next_node = node_counter
        edges.add((start_node, next_node))
        nodes.add(node_counter)
        result_lookup[(start_node, next_node)] = symbol_lookup[algebra.edges[0]]
        end_nodes.add(next_node)
    elif algebra.isproduct():
        # Do this by computing the subgraph, then linking the
        # last node to the first node.
        subgraph, end_nodes = graph_for(algebra.e1, symbol_lookup)
        nodes = subgraph.nodes
        edges = subgraph.edges
        result_lookup = subgraph.symbol_lookup
        accepting_states = subgraph.accepting_states
        start_state = subgraph.start_state
        # Make the end state and the start state the same, because this
        # is a loop.
        for state in end_nodes:
            for edge in set(edges):
                # If this edge goes to an ending state, then point
                # it around at a start state.
                # Note that for various more complicated structures,
                # like a branch with a possible ending within
                # a loop, this doesn't work.
                # (e.g. (1 + {1 + e, 1})* )
                if edge[1] == state:
                    new_edge = (edge[0], start_state)
                    result_lookup[new_edge] = result_lookup[edge]
                    del result_lookup[edge]
                    edges.remove(edge)
                    edges.add(new_edge)
            # Also remove the deleted node from the list of nodes.
            for node in set(nodes):
                if node == state:
                    nodes.remove(node)
        end_nodes = []
    return SimpleGraph(nodes, edges, result_lookup, accept_states, start_state), end_nodes


# This implements prefix merging with unification.
# That is, it returns three componenets:
#   The algebra that can be prefix merged
#   The first passed algebra
#   The second passed algebra
#   B unifier that has to be completed to complete the unification.
# We focus on unifying from the B /to/ A. (i.e. A is underlying
# hardware)
def prefix_unify(A, symbol_lookup_A, B, symbol_lookup_B, options, can_end_in_accept=False):
    prefix, postA, postB, unifier = prefix_unify_internal_wrapper(A, symbol_lookup_A, B, symbol_lookup_B, options, can_end_in_accept=can_end_in_accept)

    if prefix is not None:
        psize = prefix.size()
    else:
        psize = 0
    if postA is not None:
        bsize = postA.size()
    else:
        bsize = 0

    if psize + bsize != A.size():
        print "Computed sizes are"
        print psize
        print bsize
        print "But original size was"
        print B.size()
        assert False

    if prefix is not None and prefix.equals(Const(0, [])):
        prefix = None
    if postA is not None and postA.equals(Const(0, [])):
        postA = None
    if postB is not None and postB.equals(Const(0, [])):
        postB = None

    if unifier is None:
        unifier = None
    elif unifier.isunifierlist:
        unifier = unifier.as_list()
    else:
        unifier = [unifier]

    return prefix, postA, postB, unifier


def prefix_unify_internal_wrapper(A, symbol_lookup_A, B, symbol_lookup_B, options, can_end_in_accept=False):
    globals = {
            'symbol_lookup_A': symbol_lookup_A,
            'symbol_lookup_B': symbol_lookup_B,
            'options': options,
            # Some implementations might take a prefix
            # and try to connect it with other nodes
            # in the graph.  Those implementations should
            # probably set 'can_end_in_accept' to false, particularly
            # if they don't want to overaccept.
            # Other implementations, such as the python simulator,
            # or the proposed Grapefruit model, can deal with this
            # being set to True (and benefit greatly from it).
            'can_end_in_accept': can_end_in_accept
    }

    def prefix_unify_internal(A, B):
        if DEBUG_PREFIX_MERGE:
            print "Trying to prefix unify"
            print A
            print B
        if A.isconst() and B.isconst() and A.val == B.val:
            last_equal_index = -1

            unifier = Unifier()
            unifier.add_edges(B.edges, A.edges, options)

            # If we were not normalizing 1 all the time, this would
            # be a challenging problem to deal with.
            # However, since we are currently normalizing the const
            # to 1, this is a bit simpler to deal with (i.e. we can
            # assume that we want to unify the whole thing)
            prefix = Const(A.val, A.edges)
            post_A = None
            post_B = None

            if DEBUG_PREFIX_MERGE:
                print "In const case"
                print prefix
                print post_A
                print post_B

            return prefix, post_A, post_B, unifier
        elif A.isend() and B.isend():
            return End(), None, None, Unifier()
        elif A.isaccept() and B.isaccept():
            return Accept(), None, None, Unifier()
        elif A.isproduct() and B.isproduct():
            sub_prefix, tail_A, tail_B, unifier = prefix_unify_internal(A.e1, B.e1)

            if tail_A is None and tail_B is None:
                return A.clone(), None, None, unifier
            else:
                # Product merges are a bit of an all-or-nothing case.
                # If we didn't get all of each, we can't partially unify
                # this.
                return None, A, B, None
        elif A.isbranch() and B.isbranch():
            # We need every branch end to be a complete combination.
            if len(A.options) != len(B.options):
                return None, A, B, None

            assignment_indicies = [None] * len(B.options)
            unifiers = [None] * len(B.options)
            for b_index in range(len(B.options)):
                b_opt = B.options[b_index]
                prefix_index = None

                for a_index in range(len(A.options)):
                    a_opt = A.options[a_index]
                    prefix_unification, tail_a, tail_b, unifier = prefix_unify_internal(a_opt, b_opt)

                    # Can only unify the branch if we have unity all the way to the end.
                    if tail_a is None and tail_b is None:
                        assignment_indicies[b_index] = a_index
                        assert unifier is not None
                        unifiers[b_index] = unifier

            # We could do a better job here by trying to decide
            # which unifiers to proceed with (all of them?) instead
            # we'll just return one for the moment.
            # Jackson thinks that there is some significant
            # but not otherworldly gain here.
            unifier = Unifier()
            for i in range(len(assignment_indicies)):
                assignment = assignment_indicies[i]
                # Got no assignment for this label.
                if assignment is None:
                    return None, A, B, None
                unifier.unify_with(unifiers[i])

            # Again, we (unnessecarily?) treat this as
            # an all-or-nothing.  Splits automat a lot
            # to split them in the middle of branches.
            return A.clone(), None, None, unifier
        elif A.issum() and B.issum():
            # There is a significant question here: do we really want
            # to unify as far as possible? (Which is what this does)
            # Perhaps we need an heurisitic that the unifier can
            # quickly estimate to stop unifying any further.
            total_prefix = []
            tail_A = None
            if len(A.e1) > len(B.e1):
                tail_A = A.e1[len(B.e1):]
            tail_B = None
            if len(B.e1) > len(A.e1):
                tail_B = B.e1[len(A.e1):]
            # We want to keep track of both of these, in case
            # the unification is expected to fail so we can
            # stop unifying.
            unifiers_found = []
            unifier_result = Unifier()
            for elt in range(min(len(A.e1), len(B.e1))):
                sub_prefix, sub_tail_A, sub_tail_B, sub_unifier = prefix_unify_internal(A.e1[elt], B.e1[elt])

                if DEBUG_PREFIX_MERGE:
                    print "Result of sub-unification is (from", A.e1[elt], B.e1[elt], ")"
                    print sub_prefix
                    print sub_tail_A
                    print sub_tail_B

                fail = False
                if sub_tail_A is None and sub_tail_B is None:
                    unifier_result.unify_with(sub_unifier)
                    # We implement a little bit of the idea of not going
                    # too far here by using the mapping heuristic, i.e.
                    # to fail if there is an obvious symbol collision.
                    if options.use_inline_unification_heuristics and unifier_result.mapping_heuristic_fail(globals['symbol_lookup_B'], globals['symbol_lookup_A'], globals['options']):
                        fail = True
                    else:
                        # keep going.
                        total_prefix.append(sub_prefix)
                        unifiers_found.append(sub_unifier)
                else:
                    fail = True

                if fail:
                    if DEBUG_PREFIX_MERGE:
                        print "No more element unification, computing tails"
                    # Do not keep unifying --- we reached the end.
                    # We can (and should) reset the tails in this case.
                    tail_A = A.e1[elt:]
                    tail_B = B.e1[elt:]
                    break

            # Can't just leave a + e, or + a at the beginning
            # of the tail_A or tail_B, because those are actuall
            # modifiers to the last const --- so if that's the case,
            # then pull the last const out of the total prefix.
            if tail_A and tail_B and (tail_A[0].isaccept() or tail_B[0].isaccept()):
                assert can_end_in_accept
                if can_end_in_accept:
                    # We said it can end in accept, just drop the + a part from the tails.
                    if tail_A[0].isaccept():
                        tail_A = tail_A[1:]
                    if tail_B[0].isaccept():
                        tail_B = tail_B[1:]
                else: # can't end in accept.
                    assert len(total_prefix) > 0 # Don't think we
                    # have any empty regexes input, pretty sure MNRL
                    # converter doesn't support that.
                    tail_A = A.e1[elt - 1:]
                    tail_B = B.e1[elt - 1:]

                    assert not tail_A[0].isaccept() and not tail_B[0].isaccept()
                    # Remove the element we just added back on the tails.
                    del total_prefix[-1]
                    del unifiers_found[-1]

            # If they are just +e, then drop them.
            if tail_A and len(tail_A) == 1 and tail_A[0].isend():
                tail_A = []

            if tail_B and len(tail_B) == 1 and tail_B[0].isend():
                tail_B = []

            if DEBUG_PREFIX_MERGE:
                print "Reached end of sum unification, the total prefix extracted was ", Sum(total_prefix).normalize()
                print "Tail A is :"
                print Sum(tail_A).normalize() if tail_A is not None else None
                print "Tail B is"
                print Sum(tail_B).normalize() if tail_B is not None else None

            if len(total_prefix) > 0:
                # Create the master unifier
                unifier_result = Unifier()
                for unifier in unifiers_found:
                    unifier_result.unify_with(unifier)
                prefix_result = Sum(total_prefix).normalize()
                tail_A_result = None if tail_A is None or len(tail_A) == 0 else Sum(tail_A).normalize()
                tail_B_result = None if tail_B is None or len(tail_B) == 0 else Sum(tail_B).normalize()

                return prefix_result, tail_A_result, tail_B_result, unifier_result
            else:
                return None, A, B, None
        else:
            # Types don't match.
            if DEBUG_PREFIX_MERGE:
                print "Types don't match, returning"
                print A.type()
                print B.type()
                print "^ unmatched types"
            return None, A, B, None

    return prefix_unify_internal(A, B)

# This implements prefix merging.  (See REduce).
# That is, it returns three componenets:
#   The algebra that can be prefix merged
#   The first passed algebra
#   The second passed algebra
def prefix_merge(A, symbol_lookup_A, B, symbol_lookup_B, options):
    if DEBUG_PREFIX_MERGE:
        print "Trying to prefix merge"
        # print A.str_with_lookup(symbol_lookup_A)
        # print B.str_with_lookup(symbol_lookup_B)
        print A
        print B
    if A.isconst() and B.isconst() and A.val == B.val:
        last_equal_index = -1
        for i in range(len(A.edges)):
            if symbol_lookup_A[A.edges[i]] == symbol_lookup_B[B.edges[i]]:
                last_equal_index = i
            else:
                break

        prefix = Const(last_equal_index + 1, A.edges[:last_equal_index + 1])
        post_A = Const(A.val - last_equal_index - 1, A.edges[last_equal_index + 1:])
        post_B = Const(B.val - last_equal_index - 1, B.edges[last_equal_index + 1:])

        if DEBUG_PREFIX_MERGE:
            print "In const case"
            print "Merged up to index ", last_equal_index
            print prefix
            print post_A
            print post_B

        if last_equal_index == -1:
            return None, A, B
        elif last_equal_index == A.val - 1:
            return prefix, None, None
        else:
            return prefix, post_A, post_B
    elif A.isend() and B.isend():
        return End(), None, None
    elif A.isaccept() and B.isaccept():
        return Accept(), None, None
    elif A.isproduct() and B.isproduct():
        sub_prefix, tail_A, tail_B = prefix_merge(A.e1, symbol_lookup_A, B.e1, symbol_lookup_B, options)

        if tail_A is None and tail_B is None:
            return A.clone(), None, None
        else:
            return None, A, B
    elif A.isbranch() and B.isbranch():
        # We need every branch end to be a complete combination.
        if len(A.options) != len(B.options):
            return None, A, B

        assignment_indicies = [None] * len(A.options)
        for a_index in range(len(A.options)):
            a_opt = A.options[a_index]
            prefix_index = None

            for b_index in range(len(B.options)):
                b_opt = B.options[b_index]

                prefix_unification, tail_a, tail_b = prefix_merge(a_opt, symbol_lookup_A, b_opt, symbol_lookup_B, options)

                if tail_a is None and tail_b is None:
                    assignment_indicies[a_index] = b_index
        # Because we are just working with equality all the way
        # through each branch, we don't have to worry about double
        # assignments here.
        for assignment in assignment_indicies:
            if assignment is None:
                return None, A, B
        return A.clone(), None, None
    elif A.issum() and B.issum():
        total_prefix = []
        tail_A = None
        if len(A.e1) > len(B.e1):
            tail_A = A.e1[len(B.e1):]
        tail_B = None
        if len(B.e1) > len(A.e1):
            tail_B = B.e1[len(A.e1):]
        for elt in range(min(len(A.e1), len(B.e1))):
            sub_prefix, sub_tail_A, sub_tail_B = prefix_merge(A.e1[elt], symbol_lookup_A, B.e1[elt], symbol_lookup_B, options)
            if DEBUG_PREFIX_MERGE:
                print "Result of sub-unification is (from", A.e1[elt], B.e1[elt], ")"
                print sub_prefix
                print sub_tail_A
                print sub_tail_B
            if sub_tail_A is None and sub_tail_B is None:
                # keep going.
                total_prefix.append(sub_prefix)
            else:
                if DEBUG_PREFIX_MERGE:
                    print "No more element unification, computing tails"
                # Do not keep unifying --- we reached the end.
                tail_A = A.e1[elt:]
                tail_B = B.e1[elt:]
                break

        # Can't just leave a + e, or + a at the beginning
        # of the tail_A or tail_B, because those are actuall
        # modifiers to the last const --- so if that's the case,
        # then pull the last const out of the total prefix.
        if tail_A and tail_B and (tail_A[0].isaccept() or tail_B[0].isaccept()):
            assert len(total_prefix) > 0 # Don't think we
            # have any empty regexes input, pretty sure MNRL
            # converter doesn't support that.
            tail_A = A.e1[elt - 1:]
            tail_B = B.e1[elt - 1:]

            assert not tail_A[0].isaccept() and not tail_B[0].isaccept()
            # Remove the element we just added back on the tails.
            del total_prefix[-1]

        # If they are just +e, then drop them.
        if tail_A and len(tail_A) == 1 and tail_A[0].isend():
            tail_A = []

        if tail_B and len(tail_B) == 1 and tail_B[0].isend():
            tail_B = []

        if DEBUG_PREFIX_MERGE:
            print "Reached end of sum unification, the total prefix extracted was ", total_prefix

        if len(total_prefix) > 0:
            prefix_result = Sum(total_prefix).normalize()
            tail_A_result = None if tail_A is None or len(tail_A) == 0 else Sum(tail_A).normalize()
            tail_B_result = None if tail_B is None or len(tail_B) == 0 else Sum(tail_B).normalize()
            return prefix_result, tail_A_result, tail_B_result
        else:
            return None, A, B
    else:
        # Types don't match.
        return None, A, B


# This is similar to the leq functions, but it is designed
# to be used with symbol-reconfiguration methods
# that are much more receptive to structural modification
# techniques than setateless translation is.
# Again, we assume that we have a circuit for B,
# and we are trying to implement A.  (Read A <= B)
def leq_merge(A, B, options):
    if LEQ_DEBUG:
        print "Starting Unification between "
        print A, "and", B
        print "Using algorithm leq_merge"
    # Require using structural change for this algorithm ---
    # it assumes structural change at every step.  The leq
    # algorithm is a bit better for cases where you don't
    # want structural modification.
    assert options.use_structural_change
    result = leq_merge_internal_wrapper(A, B, options)

    return result


def leq_merge_internal_wrapper(A, B, options):
    globals  = {
            'call_depth': 0,
            'internal_id': 0,
            'comparison_cache': {},
            'call_count': 0
            }

    # Merge A to B.  should_split_sums refers to the algorithms
    # trying to do the merge, when they come across sums
    # 1 + 1 and 1 + 1, should they try all the sub-combinations?
    # Used internally to avoid infinite recursion.
    def leq_merge_internal(A, B, should_split_sums=True):
        # Check  whether we  have the result already cached.
        cache_pointer = (A.id, B.id)
        this_call_id = globals['internal_id']
        globals['internal_id']  += 1
        if cache_pointer in globals['comparison_cache']:
            return globals['comparison_cache'][cache_pointer]

        globals['call_depth'] += 1
        globals['call_count'] += 1
        if globals['call_count'] > options.leq_calls_threshold:
            compilation_statistics.recursion_depth_exceeded += 1
            if LEQ_DEBUG:
                print "Failed due to exceeding call threshold"
            return None
        if globals['call_depth'] > options.leq_call_depth_threshold:
            compilation_statistics.recursion_depth_exceeded += 1
            if LEQ_DEBUG:
                print "Failed  due to exceeding call depth"
            return None

        if LEQ_DEBUG:
            print "Entering new call --- Types  are:"
            print A.type()
            print B.type()
            print "Call ID is ", globals['internal_id']
            print A
            print B

        # Do the algorithm:
        if A.isconst() and not B.isbranch():
            # Most of these cases are independent of the type
            # of B, however, the arm to branch case requires
            # basically the same algorithm as the branch-to-branch
            # case, so we avoid that here.
            if B.isconst():
                result = Unifier()
                result.add_edges(A.all_edges(), B.all_edges(), options)
            else:
                # Need to add a modification --- this algorithm
                # is designed to almost never fail completely.
                # However, I've decided that this case doesn't have
                # enough context to successfully do a modification ---
                # we'd rather just skip and let a parent case, most likely
                # issum() deal with the consequences.
                result = None
                compilation_statistics.no_branch_over_node_mmodifiers += 1
        elif A.isaccept():
            # Can't aritificially induce an accept on B.
            # Expect that to be done by the sum case.
            if B.isaccept():
                result = Unifier()
            else:
                compilation_statistics.accept_to_non_accept += 1
                result = None
        elif A.isend():
            # Unlike the accept case, this can easily be
            # changed here by disabling the next edge
            # in B in the unifier.
            first_node_in_b = B.get_first_node()
            if B.isend():
                result = Unifier()
            else:
                result = Unifier()
                result.add_disabled_edges(B.first_edge())
        elif A.isproduct():
            if B.isproduct():
                # Try to unify within the loop.
                result = leq_merge_internal(A.e1, B.e1)
            else:
                result = None

            # If we couldn't do the unification within
            # that loop, try disabling the first edge
            # of B, and then adding an insert.
            if not result:
                first_edge = B.first_edge()
                # We can't disable things without
                # edges.
                if first_edge is None:
                    result = None
                else:
                    first_node = B.get_first_node()

                    result = Unifier()
                    result.add_disabled_edges(first_edge)
                    result.add_from_node(first_node)
        elif A.isbranch() or B.isbranch():
            if LEQ_DEBUG:
                print "A is a branch"

            if not B.isbranch():
                # We can add in the extra branches overtop
                # of most components. (a and e excluded)
                # Let the branch case handle that by making this
                # into a branch --- since it'll be a singleton
                # branch, we need to not normalize it.
                B = Branch([B])

            if not A.isbranch():
                A = Branch([A])

            # Here for show -- but should always be true.
            if B.isbranch():
                # Try to do an elementwise matching
                # within the branch.   This is copied
                # from the leq function with heavy modification.
                # Because this method is aimed at symbol reconfiguration,
                # it doesn't support two virtual branches
                # targetting the same physical branch.

                # Try all matches --- likely need some kind
                # of cutoff here.
                elements_A = A.options
                elements_B = B.options
                matches = [None] * len(elements_A)
                for i in range(len(elements_A)):
                    matches[i] = [None] * len(elements_B)

                    for j in range(len(elements_B)):
                        if LEQ_DEBUG:
                            print "Performing initial checks to build matrix for branch at call " + str(this_call_id) + ":"
                            print "Checking ", elements_A[i]
                            print "Checking ", elements_B[j]
                        matches[i][j] = leq_merge_internal(elements_A[i], elements_B[j])

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

                # Tried the heuristics, because the unifier list is limited
                # in length, that turned out to be the true limit here.
                # Might come back to this, but ISTM that the real benefit
                # would be in better heurisitics for trimming unifier lists.
                # heuristic_perms = list(permutations_with_heuristics(matches))
                max_matches = 0
                min_added_states = 10000000
                max_matches_unifier = None
                max_matches_combination = None
                max_matches_remaining_branches = None
                max_matches_assigned_branches = None
                for combination in permutations(len(elements_A), range(len(elements_B))):
                    perm_count += 1
                    if perm_count > PERMUTATION_THRESHOLD:
                        print "Warning: Permutation fail due to excessive numbers"
                        break
                    # check if the combination is good.
                    match_count = 0
                    added_states = 0
                    for i in range(len(combination)):
                        if matches[i][combination[i]]:
                            if LEQ_DEBUG:
                                print "Structural mod count is:"
                                print matches[i][combination[i]].structural_modification_count()
                            match_count += 1
                            added_states += matches[i][combination[i]].structural_modification_state_count()

                    if match_count > max_matches or added_states < min_added_states:
                        # Create the unifier with this sequence of
                        # assignments:
                        this_branch_unifier = Unifier()
                        # Keep track of which of the
                        # hardware branches we are using
                        used_branches = []

                        # Keep track of which of the virtual
                        # branches that we didn't find matches
                        # for.
                        unmatched_branches = []
                        for i in range(len(combination)):
                            if matches[i][combination[i]]:
                                used_branches.append(combination[i])
                                this_branch_unifier.unify_with(matches[i][combination[i]])
                            else:
                                unmatched_branches.append(i)

                        # Disable the other edges:
                        for i in range(len(elements_B)):
                            if i not in used_branches:
                                B_first_edges = elements_B[i].first_edge()
                                if B_first_edges:
                                    this_branch_unifier.add_disabled_edges(B_first_edges)
                                else:
                                    # If the first edge isn't set,
                                    # then I think we can assume that an accept is somehow happening right away?
                                    # like this: 1 + {a, 1 + a}?
                                    # TBH not too sure why this case
                                    # came up, but a safe thing to do
                                    # is reject this match.
                                    is_match = False
                                    this_branch_unifier = None

                        # Some unifications could fail
                        # in the last stage, so don't update
                        # the state of the unifier until this point.
                        if this_branch_unifier:
                            # If the unifier still exists, then use it.
                            max_matches_unifier = this_branch_unifier
                            max_matches_remaining_branches = unmatched_branches
                            max_matches_assigned_branches = used_branches
                            max_matches_combination = combination
                            max_matches = match_count
                            min_added_states = added_states
                            if LEQ_DEBUG:
                                print "Set the max combination to ", max_matches_combination
                                print "Assigned branches is ", max_matches_assigned_branches
                                print "Remaining Branches is ", max_matches_remaining_branches
                                print "Match count is ", match_count
                                print "Added state count is ", min_added_states
                #endfor combination in combinations
                if LEQ_DEBUG:
                    print "Finished matching --- best assignemnt found is "
                    print max_matches_combination
                if max_matches_unifier is None:
                    if LEQ_DEBUG:
                        print "DId not find a max_matches_unifier... Setting defaults to add overtop of all edges"
                    # There were not partial matches, so introduce a branch
                    # over this element as a whole.
                    max_matches_unifier = Unifier()
                    max_matches_remaining_branches = range(len(B.options))
                    max_matches_assigned_branches = []

                # This is a unifier with the appropriate
                # branches disabled.
                result = max_matches_unifier

                # Now, add the branches to the unifier.
                branch_last_node = B.get_last_node()
                branch_first_node = B.get_first_node()

                if branch_last_node is None or branch_first_node is None:
                    # Then all the branch arms are stuff
                    # like 1 + e
                    if B.has_first_edge():
                        for branch in max_matches_remaining_branches:
                            result.add_from_node(A.options[branch], B.first_edge())
                    else:
                        # Can't do this since
                        # this has no first edge to build from.
                        result = None
                else:  # branch_last_node is not None and branch_first_node is not None
                    for branch in max_matches_remaining_branches:
                        result.add_between_nodes(A.options[branch], (branch_first_node, branch_last_node))
            else:
                #endif B.isbranch()
                assert False
        elif A.issum() and should_split_sums:
            if LEQ_DEBUG:
                print "Entering a split sums case"
            # The concept here is to look at every combination
            # and see which one results in the fewest
            # structural additions --- use the one
            # that has the fewest such structural additions.
            #  In practice, we aren't going to be able to look
            # at /every/ combination.  However, we try to approximate
            # that here.

            # If B is not a sum, turn it into a singleton sum
            # so that the below algorithm can work on it.
            if not B.issum():
                B = Sum([B])

            # All the sub-calls within this function should have
            # should_split_sums set to false to avoid recursing here.

            # Right now, this just passes onto the not should_split_sums
            # case.  I'm expecting various splitting heuristics to be useful here.
            result = leq_merge_internal(A, B, should_split_sums=False)
        elif A.issum() and not should_split_sums:
            # In this case, we unify as much as we can with B, without
            # splitting the sum --- anything left over should
            # be added as a nodification.
            if not B.issum():
                B = Sum([B])

            # Iterate, unifying each respective element if possible.
            # if a unification is not possible, stop, and add an
            # extension instead.
            a_index = 0
            b_index = 0
            has_match = True
            unifier = Unifier()
            while a_index < len(A.e1) and b_index < len(B.e1) and has_match:
                if LEQ_DEBUG:
                    print "Starting iteration for indexes ", a_index, b_index
                    print "The heads are:", A.e1[a_index], B.e1[b_index]

                if B.e1[b_index].isaccept() or B.e1[b_index].isend() and \
                        not A.e1[a_index].isaccept() and not A.e1[a_index].isend():
                    if LEQ_DEBUG:
                        print "Failed to compute the sum --- can't convert to a modifier from a non-modifier"

                # Do various checks to allow merging of modifiers
                if a_index < len(A.e1) - 1 and b_index < len(B.e1) - 1 \
                        and A.e1[a_index].isconst() and A.e1[a_index + 1].isaccept() \
                        and B.e1[b_index].isconst() and not B.e1[b_index + 1].isaccept() \
                        and not B.e1[b_index + 1].isend():
                    if LEQ_DEBUG:
                        print "A has a non-terminating accept, trying to create a branch for it..."
                    # This is a 1 + a, and B only has 1 + ..., so we need to
                    # insert a branch to make this unification.
                    unifier.add_between_nodes(A.e1[a_index:a_index + 2], (B.e1[b_index].get_first_node(), B.e1[b_index + 1].get_last_node()))

                    a_index += 2
                    b_index += 1
                    continue

                if A.e1[a_index].isproduct():
                    if LEQ_DEBUG:
                        print "A is a product, trying to unify"
                    # See if we can do a unification --- otherwise, we can just
                    # insert this for 'free'.
                    sub_unifier = leq_merge_internal(A.e1[a_index], B.e1[b_index])
                    if sub_unifier is None:
                        # Insert the product then move on.  There is a choice
                        # here --- we could skip a lot of B.  However, we should
                        # leave that choice to the splitting funciton.
                        if LEQ_DEBUG:
                            print "Product unification failed, inserting..."
                        first_b_node = B.e1[b_index].get_first_node()
                        if first_b_node is not None:
                            unifier.add_between_nodes(A.e1[a_index], (first_b_node, first_b_node))
                            a_index += 1
                            continue
                    else:
                        # Otherwise, just continue on to the default case.
                        pass

                if B.e1[b_index].isproduct() and not A.e1[a_index].isproduct():
                    if LEQ_DEBUG:
                        print "Disabling a product in B"
                        print "Product is ", B.e1[b_index]
                    # Since A is not a product we need to skip this.
                    first_edges = B.e1[b_index].first_edges()
                    unifier.add_disabled_edges(first_edges)
                    b_index += 1
                    continue

                if B.e1[b_index].isbranch() and not A.e1[a_index].isbranch():
                    # Exploring arm to branch conversions:
                    if LEQ_DEBUG:
                        print "Exploring arm to branch conversions"
                    # We have the opportunity to match to a branch here.
                    # For each arm, see how much matching we get
                    # --- the more the better.  Pick the match
                    # that gets us the most distance through A.
                    b_branch = B.e1[b_index]
                    unifier_found = None
                    unifier_size = -1
                    for i in range(len(A.e1), a_index, -1):
                        # This is a call with a different
                        # sum in the new B, so we
                        # are going to let it be split.
                        # Not sure if it's a good idea to
                        # do this here, since it does kind
                        # of defeat the point.
                        # Ultimately, I think that this
                        # algorithm needs better approximations.
                        # e.g. it performs really poorly
                        # with 2 + a + e and {1, 2} + 1 + a + e
                        if LEQ_DEBUG:
                            print "Trying to unify arm to branch... (source call id is ", this_call_id, ")"

                        # The branching case will explore each arm
                        # of this sine B[b_index] is a branch and
                        # A.e1[... is probably not (it will also
                        # explore all the combinations even if it is.
                        sub_unifier = leq_merge_internal(Sum(A.e1[a_index: i]).normalize(), B.e1[b_index])

                        if LEQ_DEBUG:
                            print "Internal check done --- at call ", this_call_id
                        if sub_unifier is None or sub_unifier.has_structural_additions():
                            # Ideally, we would allow for structural
                            # additions, what we really want to check here
                            # is that there isn't a whole huge chunk of
                            # A that is hanging off the end.
                            continue
                        else:
                            this_unifier_size = i - a_index
                            if unifier_size > this_unifier_size:
                                unifier_found = sub_unifier
                                unifier_size = this_unifier_size

                    if unifier_found is not None:
                        unifier.unify_with(unifier_found)
                        a_index += unifier_size
                        # We've used the branch.
                        b_index += 1
                        continue

                # We want to split sums again --- e.g. if the first element
                # of this is {1 + 1, ...} we want to split the 1 + 1 since
                # we hanven't done that yet.
                if LEQ_DEBUG:
                    print "No special cases found --- unifying the heads..."
                sub_unifier = leq_merge_internal(A.e1[a_index], B.e1[a_index])
                if sub_unifier is not None:
                    unifier.unify_with(sub_unifier)
                    a_index += 1
                    b_index += 1
                else:
                    has_match = False

            if a_index < len(A.e1):
                # Do an insert for the rest.
                if A.e1[a_index].isend() or A.e1[a_index].isaccept():
                    # Can't start a modification with a modifier!
                    unifier = None
                else:
                    last_node_matched = B.e1[b_index - 1].get_last_node()
                    unifier.add_from_node(Sum(A.e1[a_index:]).normalize(), last_node_matched)

            result = unifier
        elif A.isproduct():
            if B.isproduct():
                if LEQ_DEBUG:
                    print "Trying to unify products..."
                sub_unifier = leq_merge_internal(A.e1, B.e1)

                if sub_unifier is not None:
                    result = sub_unifier
            else:
                # In theory we could do an insert, but in practice,
                # we don't have enough context to do one.
                result = None
        elif B.isaccept():
            # These handle cases where
            assert False
            result = None
            compilation_statistics.sum_to_modifier_failed += 1
        elif B.isend():
            result = None
            compilation_statistics.sum_to_modifier_failed += 1

        # Sanity-check results.
        if LEQ_DEBUG and result is not None:
            print "Checked edge lenghts before return!"
            all_edges_set = A.all_edges()
            print "Have unified ", len(all_edges_set), "edges"
            if result.all_from_edges_count() != len(all_edges_set):
                print "Error, lengths differ: ", len(result.from_edges), len(all_edges_set)
                print "From edges is ", result.from_edges
                print "All edges is ", all_edges_set
                print [str(x) for x in result.additions_between_nodes]
                print result.from_edges
                print all_edges_set
                print A
                print B
                assert False
            print "Returning a real result! (from call ", this_call_id, ")"
            print "Result is: ", result

        # Handle the results:
        globals['comparison_cache'][cache_pointer] = result
        globals['call_depth'] -= 1
        return result
    return leq_merge_internal(A, B)

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
def leq(A, B, options, from_symbols_lookup=None, to_symbols_lookup=None):
    unifier = leq_unify(A, B, options, from_symbols_lookup=from_symbols_lookup, to_symbols_lookup=to_symbols_lookup)
    return unifier is not None and unifier != []


# This MUST support multithreaded operation.
def leq_unify(A, B, options, from_symbols_lookup=None, to_symbols_lookup=None):
    if LEQ_DEBUG:
        print "Starting new unification...."
        print "Comparing ", str(A), " and ", str(B)
        print "(Sizes ", A.size(), B.size(), ")"

    if not options.no_leq_heuristics and leq_fails_on_heuristics(A, B, options):
        compilation_statistics.cutoff_comparisons += 1
        return None

    compilation_statistics.executed_comparisons += 1

    unifier = leq_internal_wrapper(A, B, options, from_symbols_lookup=from_symbols_lookup, to_symbols_lookup=to_symbols_lookup)
    if unifier is not None and unifier.isunifierlist:
        result = unifier.as_list()
    elif unifier is not None:
        result = [unifier]
    else:
        result = []

    return result

def leq_fails_on_heuristics(A, B, options):
    a_loop_sizes = A.loop_sizes()
    b_loop_sizes = set(B.loop_sizes())
    for loop_size in a_loop_sizes:
        # 4 is an arbitrary threshold here, that dictates how large
        # a loop can be injected --- but the larger this is,
        # the slower it is.
        if loop_size > 4 and loop_size not in b_loop_sizes:
            return False

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
    max_accepting_distance = max(b_accepting_distances)

    for distance in a_accepting_distances:
        hit = False
        if distance <= max_accepting_distance:
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

    return False

# This MUST support multithreaded operation.
def leq_internal_wrapper(A, B, options, from_symbols_lookup=None, to_symbols_lookup=None):
    global_variables = {
            'comparison_cache': {},
            # This is a counter to help distinguish between calls.
            'leq_internal_id': 0,
            # Keeps track of the depth of the calls
            'leq_calls': 0,
            # Keep track of the depth --- some of the equations are too big
            # for python to handle.
            'leq_depth': 0,
            'solution_ID': hash(A) + hash(B),
            'from_symbols_lookup': from_symbols_lookup,
            'to_symbols_lookup': to_symbols_lookup
    }

    def internal_unifier_creation():
        return Unifier(symbol_lookup_from=global_variables['from_symbols_lookup'],
                        symbol_lookup_to=global_variables['to_symbols_lookup'])

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
            compilation_statistics.recursion_depth_exceeded += 1
            if LEQ_DEBUG:
                print "Warning: LEQ Recursion depth exceeded"
            return None

        if LEQ_DEBUG:
            print "Entering a new comparison"
            print "Types are ", A.type(), " and ", B.type()
            print A
            print B
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
            opt_unifiers = []
            selected_unifiers = []
            for opt in B.options:
                sub_unifier = leq_internal(A, opt, options)
                if sub_unifier is not None:
                    opt_unifiers.append(opt)
                    selected_unifiers.append(sub_unifier)

            # Note that there is some possibility for more
            # generality here, because one of these branch
            # options might be unifiable, while the others
            # may not be.  We've just picked the first, but
            # a simple heuristic may be more than possible.
            if len(opt_unifiers) > 0:
                # Create the unifier.
                for i in range(len(selected_unifiers)):
                    this_unifier = selected_unifiers[i]
                    for opt in B.options:
                        if opt != opt_unifiers[i]:
                            # Unify the first edge with None.
                            # Note that there is also scope here for
                            # more flexibility, because we are really
                            # interested in ensuring that it doesn't
                            # get to an unwanted accepting state.
                            first_edges = opt.first_edge()
                            if first_edges:
                                this_unifier.add_disabled_edges(first_edges)
                result = True
                unifier = UnifierList([])
                for u in selected_unifiers:
                    unifier.append_unifiers(u)
            else:
                # No branch unified.
                unifier = None
                compilation_statistics.single_arm_to_branch_not_found += 1
                result = False
        elif A.isbranch() and not B.isbranch():
            if LEQ_DEBUG:
                print "A is a branch and B is not a branch -- trying"
                print "to create structural equality between the two."
            # We can compile this, but require that every branch
            # of A compiles to B.
            unifier = UnifierList([internal_unifier_creation()])
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
                compilation_statistics.branch_to_single_arm_not_possible += 1
        # If B is a sum, then we want to use the sum algorithm.
        elif A.isconst() and not B.issum():
            if LEQ_DEBUG:
                print "A is const:"
            if B.isconst():
                if LEQ_DEBUG:
                    print "B also const, checking equality of:"
                    print A.val
                    print B.val
                    print len(A.edges)
                    print len(B.edges)
                if A.val == B.val:
                    result = True
                    unifier = internal_unifier_creation()
                    unifier.add_edges(A.edges, B.edges, options)
                elif use_leq_on_constants and B.val < A.val:
                    # This case shouldn't be in use right now ---
                    # I'm pretty sure it's not valid.
                    assert False
                    result = True
                    # If this case is re-activated, this should
                    # use the internal_unifier_creation function.
                    unifier = Unifier(cost=A.val - B.val)
                    unifier.add_edges(A.edges[:len(B.edges)], B.edges, options)
                else:
                    result = False
            elif B.isproduct():
                if LEQ_DEBUG:
                    print "B product"
                # This was true, not sure why.
                result = False # True
            else:
                compilation_statistics.const_to_non_const += 1
                if LEQ_DEBUG:
                    print "B other"
                result = False
        elif A.isend():
            if LEQ_DEBUG:
                print "A is end: unifying the first edge of B to NoMatch"
            result = True
            # We can unify this, but we need to make sure that
            # we can 'disable' that edge.
            unifier = internal_unifier_creation()
            first_edges = B.first_edge()
            # We don't always need to unify anything from this --- it
            # could be, e.g. that B is also end
            if first_edges is not None:
                unifier.add_disabled_edges(first_edges)

            # Can't have an accept before the first edge though.
            # We can have an accept before the first edge if we
            # are overaccepting --- note that this might be a bad
            # tradeoff of accuracy.
            if options.correct_mapping and B.has_accept_before_first_edge():
                result = False
                unifier = None
        elif A.isaccept() and B.isaccept():
            if LEQ_DEBUG:
                print "Both Accept"
            result = True
            unifier = internal_unifier_creation()
        elif A.isproduct() and B.isproduct():
            if LEQ_DEBUG:
                print "Both are products: Unifying subcomponents"
            unifier = leq_internal(A.e1, B.e1, options)
            if unifier is None:
                result = False
                compilation_statistics.product_to_product_failed += 1
            else:
                result = True
        # This case is a mess and basically a dirty hack that considers
        # a single special case that requires a lot of fine-tuning.
        # Sorry.
        elif A.isconst() and B.issum():
            # I'm not sure how correct this case is --- what if it is called as part of a larger check?  How can we just
            # disable the outgoing edges correctly?
            if LEQ_DEBUG:
                print "Const to sum conversion.."
            # There are a few cases we consider here --- consider this as a
            # base-case for A.issum and B.issum().
            elts = B.e1
            # This should be true because we should have normalized things.
            assert len(elts) > 1
            if not result:
                compilation_statistics.const_to_sum_failed += 1
        elif A.issum() and B.isconst():
            # This is the equivalent base-case, but doesn't have anywhere near as many options in it.
            # Check if we are just inserting a loop, which we
            # can do :)
            if options.use_structural_change and len(A.e1) == 3:
                    if len(A.e1) == 3 and \
                            A.e1[0].isconst() and \
                            A.e1[1].isproduct() and \
                            A.e1[1].e1.isconst() and \
                            A.e1[2].isconst():
                        #This is a loop :)
                        unifier = internal_unifier_creation()
                        unifier.add_between_nodes(A, B.edges[0])
                        result = True
                    else:
                        failed_loop_insertion = True
            else:
                result = False
                compilation_statistics.sum_to_const_failed += 1

            if LEQ_DEBUG:
                print "Hit a case converting a sum to a const, not implemented"
        elif A.issum() and B.issum():
            if LEQ_DEBUG:
                print "Both are sums: unifying subsums"
                print "Lenths are ", len(A.e1),  "and", len(B.e1)

            # If A is 1 + a + e, then we have a getout option here:
            # This could be a lot more general, e.g. if A is 1 + a + 1,
            # we could also do something with a split and a rejoin into B,
            # but for the moment, we are ignoring that and just leaving pointy-ends.
            if options.use_structural_change and len(A.e1) == 3 and \
                    A.e1[0].isconst() and A.e1[1].isaccept() and A.e1[2].isend() and \
                    not (len(B.e1) >= 3 and B.e1[0].isconst() and B.e1[1].isaccept() and B.e1[2].isend()):
                unifier = internal_unifier_creation()
                unifier.add_from_node(A, B.first_edge())
                result = True
            # It would be good if we could handle this case, but it is a bit more
            # complicated, becuase it requires a bit more complex structural change.
            elif options.use_structural_change and len(A.e1) >= 3 and \
                    A.e1[0].isconst() and A.e1[1].isaccept() and not B.has_accept():
                pass
            else:
                still_equal = True
                unifier = UnifierList([internal_unifier_creation()])
                result = True # Needs to be set to false whereever this fails.

                a_index = 0
                b_index = 0
                # We don't need equality up to the end here, due
                # the the (trim) rule (i.e. e <= x (provided x != a))
                while still_equal and a_index < len(A.e1) and b_index < len(B.e1):
                    if ALG_DEBUG:
                        print "Remaining algebras for next iteration are:"
                        print Sum(A.e1[a_index:])
                        print Sum(B.e1[b_index:])
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

                    # If we have overapproximation, we don't care
                    # if there is a loop here that is non-existent
                    # in A.
                    if not options.correct_mapping and B.e1[b_index].isproduct() and not A.e1[a_index].isproduct():
                        # Just move B forward --- we can ignore
                        # the product, which will trigger, but
                        # which will be part of the overapproximation.
                        # May want to keep track of this if we want to do something
                        # like estimating the error rate.
                        b_index += 1
                        continue
                    # If we have structural modificaton /and/ overapproximation, we can insert a loop from
                    # A into the algebra (that will hopefully be picked up bu the above case
                    # when we need it to.
                    if not options.correct_mapping and options.use_structural_change and A.e1[a_index].isproduct() and not B.e1[b_index].isproduct() and B.e1[b_index].first_edge():
                        unifier.add_from_node(A.e1[a_index], B.e1[b_index].first_edge())
                        a_index += 1
                        continue

                    # The expanding algorithm works well for a lot of things, but for picking up this
                    # case, it doens't work very well.  This makes sure that we trigger the
                    # branch addition case if we are using structural change.
                    if options.use_structural_change and \
                            len(A.e1) - a_index == 3 and A.e1[a_index].isconst() and\
                            A.e1[a_index + 1].isaccept() and \
                            (len(B.e1) - b_index < 3 or not B.e1[b_index + 1].isaccept()):
                            # (commentary on on last case)
                            # But don't trigger this case if we'll probably get a unification
                            # anyway --- it's better not to trigger the above case if we
                            # can avoid it, since that introduces new edges, and this shares
                            # existing edges.
                        sub_unifier = leq_internal(Sum(A.e1[a_index:]), Sum(B.e1[b_index:]).normalize(), options)
                        if sub_unifier is not None:
                            unifier.unify_with(sub_unifier)
                            a_index = len(A.e1)
                            break

                    # Check if we need to insert a loop, and
                    # make that recursive call if nessecary.
                    # This can't be the last element --- I can't remember whether that's actually going to cause
                    # problems or would just need a special case.
                    if options.use_structural_change and \
                            len(A.e1) >= a_index + 3 and len(B.e1) >= b_index + 2 and A.e1[a_index].isconst() and \
                            A.e1[a_index + 1].isproduct() and A.e1[a_index + 1].e1.isconst() and A.e1[a_index + 2].isconst() and \
                            not B.e1[b_index + 1].isproduct() and \
                            B.e1[b_index].isconst():
                        # There is no way were are going to be able to
                        # unify the next element in A.  See if we
                        # can create the branch instead:
                        sub_unifier = leq_internal(Sum(A.e1[a_index:a_index + 3]).normalize(), B.e1[b_index], options)
                        if sub_unifier is not None:
                            unifier.unify_with(sub_unifier)
                            a_index += 3
                            b_index += 1
                            continue

                    # This is an approximation that speeds things up significantly, e.g.
                    # by unifying long sequences of 1 + 1 + 1...
                    if A.e1[a_index].isconst() and B.e1[b_index].isconst():
                        # Unify and continue:
                        sub_unifier = leq_internal(A.e1[a_index], B.e1[b_index], options)
                        if sub_unifier is not None:
                            # We can just go back around the loop:
                            unifier.unify_with(sub_unifier)
                            a_index += 1
                            b_index += 1
                            continue

                    # This is also an approximation that speeds things
                    # up significantly by unifier (1)* and (1)* both
                    # at the head of large sums.
                    if A.e1[a_index].isproduct() and B.e1[b_index].isproduct():
                        sub_unifier = leq_internal(A.e1[a_index], B.e1[b_index], options)
                        if sub_unifier is not None:
                            unifier.unify_with(sub_unifier)
                            a_index += 1
                            b_index += 1
                            continue

                    # This one is actually a correctness hack --- something about
                    # the expanding algorithm means that branch-to-branch things aren't properly
                    # unified.
                    if A.e1[a_index].isbranch() and B.e1[b_index].isbranch():
                        sub_unifier = leq_internal(A.e1[a_index], B.e1[b_index], options)
                        if sub_unifier is not None:
                            unifier.unify_with(sub_unifier)
                            a_index += 1
                            b_index += 1
                            continue

                    # Loops from Grapefruit internals are of the format:
                    #   {1, 1 + (1)* + 1} -- unfortunately, this makes for poor
                    # matching for straight-line code when over approximation
                    # is enabled because the longest match for 1 + 1 will be 1 + (1)* + 1 --- we probably want 1 + 1
                    # to match the 1 branch instead.
                    if len(A.e1) > a_index + 1 and A.e1[a_index].isconst() and not A.e1[a_index + 1].isproduct() and \
                            B.e1[b_index].isbranch() and len(B.e1[b_index].options) == 2:
                        if LEQ_DEBUG:
                            print "Attempting to apply branch shortlink approximation..."
                        opt1 = B.e1[b_index].options[0]
                        opt2 = B.e1[b_index].options[1]

                        check_for_optimization = True
                        if opt1.isconst():
                            other_opt = opt2
                            other_branch_index = 1
                        elif opt2.isconst():
                            other_opt = opt1
                            other_branch_index = 0
                        else:
                            check_for_optimization = False

                        if check_for_optimization and \
                                other_opt.issum() and len(other_opt.e1) == 3 and \
                                other_opt.e1[0].isconst() and other_opt.e1[1].isproduct() and \
                                other_opt.e1[1].e1.isconst() and \
                                other_opt.e1[2].isconst():
                            # Try a shortcut where we unify A.e1[0]
                            # to the short option rather than the long option.
                            sub_unifier = leq_internal(A.e1[a_index], B.e1[b_index], options)
                            if sub_unifier is not None:
                                unifier.unify_with(sub_unifier)
                                a_index += 1
                                b_index += 1
                                continue

                    last_element_of_a = len(A.e1)
                    found_match_expanding_a = False
                    while not found_match_expanding_a and last_element_of_a > a_index:
                        # We can call simple_normalize here because (a) it is much faster, and (b)
                        # we already know that all the sub-elements are normalized, and that
                        # there is no inter-element normalization to do.
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
                        element_index = b_index + 1
                        found_match_expanding_b = False

                        while not found_match_expanding_b and element_index <= len(B.e1):
                            smaller_elements = Sum(B.e1[b_index:element_index]).normalize(flatten=False)
                            sub_unifier = leq_internal(A.e1[a_index], smaller_elements, options)

                            if sub_unifier is not None:
                                if LEQ_DEBUG:
                                    print "Found match expanding B"
                                    print "Match was between "
                                    print A.e1[a_index]
                                    print Sum(B.e1[b_index:element_index])
                                found_match_expanding_b = True
                            else:
                                element_index += 1

                        if found_match_expanding_b:
                            unifier.unify_with(sub_unifier)
                            b_index = element_index
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
                        sum_tail = Sum(B.e1[b_index:]).normalize()
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
                    compilation_statistics.sum_failure += 1
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
            assert unifier is None
            unifier = UnifierList([])
            # Tried the heuristics, because the unifier list is limited
            # in length, that turned out to be the true limit here.
            # Might come back to this, but ISTM that the real benefit
            # would be in better heurisitics for trimming unifier lists.
            # heuristic_perms = list(permutations_with_heuristics(matches))
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
                    this_branch_unifier = UnifierList([internal_unifier_creation()])
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
                compilation_statistics.branch_to_branch_failure += 1

        else:
            compilation_statistics.types_differ += 1
            result = False
            if LEQ_DEBUG:
                print "Types differ: unification failed"
                print "Types were", A.type(), B.type()

        global_variables['comparison_cache'][cache_pointer] = unifier
        if unifier is None:
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

        if LEQ_DEBUG and unifier is not None:
            if unifier.isunifierlist:
                unifiers = unifier.as_list()
            else:
                unifiers = [unifier]

            print "Checked edge lenghts before return!"
            all_edges_set = A.all_edges()
            print "Have unified ", len(all_edges_set), "edges"
            for u in unifiers:
                if u.all_from_edges_count() != len(all_edges_set):
                    print "Error, lengths differ: ", len(u.from_edges), len(all_edges_set)
                    print [str(x) for x in u.additions_between_nodes]
                    print u.from_edges
                    print all_edges_set
                    print A
                    print B
                    assert False

        global_variables['leq_depth'] -= 1
        return unifier

    if options.line_profile:
        global profiler
        wrapper = profiler(leq_internal)
        wrapper(A, B, options)
    else:
        result = leq_internal(A, B, options)
        return result


# Yield every cpermustations of i numbers up to j.
def permutations(i, j):
    # This used to be product, by the thing is, the
    # number of examples that actually unify with
    # multiple arms to one branch or vice-versa
    # is extremely small.
    # And now that it is permutations, it is not just
    # an approximation --- leq_merge relies on this
    # being a permutations function now.
    return itertools.permutations(j, i)

# Yield the permutations we should try and unify between two different
# lists in an heuristic order, sorted by the most likely options.
def permutations_with_heuristics(cross_compilatiion_matrix):
    # Keep track of which elts_B each elt_A is likely to map to.
    # --- just use size to do this.
    likely_to_map = []
    for _ in cross_compilatiion_matrix:
        likely_to_map.append([])

    for a_i in range(len(cross_compilatiion_matrix)):
        for b_i in rotate(range(len(cross_compilatiion_matrix[a_i])), a_i):
            if cross_compilatiion_matrix[a_i][b_i]:
                likely_to_map[a_i].append(b_i)

    for map in likely_to_map:
        if len(map) == 0:
            return []

    # Now, we just need to generate a list of all combinations
    # where elts_A[i] is only mapped to elts_B[i] iff
    # there is an appropriate size difference.
    result = itertools.slide(itertools.product(*likely_to_map), PERMUTATION_THRESHOLD)
    return result

# Given an automata, and a list of additions, inject the additions
# into the automata.
def apply_structural_transformations(automata, additions, options):
    if group_compiler.DEBUG_GENERATE_BASE:
        print "Start graph is"
        print automata
        print "It has algebra", single_compiler.compute_depth_equation(automata, options)

    result_graph = apply_structural_transformations_internal(automata, additions, options)

    if group_compiler.DEBUG_GENERATE_BASE:
        print "After modification, graph is"
        print result_graph
        print "and has algebra", single_compiler.compute_depth_equation(result_graph, options)
    return result_graph

def apply_structural_transformations_internal(simple_graph, additions, options):
    old_graph = simple_graph
    # multiple modifications --- one for each unification to this
    # automata
    modification_count = 0
    for modification_set in additions:
        # muliple additions per unification :)
        for addition in modification_set.all_modifications():
            modification_count += 1
            if group_compiler.DEBUG_GENERATE_BASE:
                print "Adding:"
                print "(of ", len(modification_set), " additions)"
                print addition
            # Then, insert this by generating new edge numbers and
            # putting it in with the appropriate symbol set.
            new_graph, last_nodes = graph_for(addition.algebra, addition.symbol_lookup)

            # check that we are only inserting things.
            og = old_graph.clone()
            # And insert it into the graph:
            if addition.isinsert():
                # Get the nodes around which we insert this:
                (before, after) = addition.edge
                old_graph = sjss.splice_between(og, before, after, new_graph, last_nodes)
            else:
                # Get the edges that this has to be before
                edges_after = addition.edges_after
                # Now, get the node that leads to the 'edges after',
                # and insert this one before all the edges after.
                nodes_before = list(sjss.get_node_before_edges(edges_after))

                # I don't think we currently support adding things
                # with many different start nodes --- not sure how
                # that would work.
                assert len(nodes_before) == 1

                old_graph = sjss.splice_after(og, nodes_before[0], new_graph)

            if group_compiler.DEBUG_GENERATE_BASE:
                # Ensure that all the new lookups are in the new
                # graph:

                for edge in new_graph.edges:
                    assert edge in new_graph.symbol_lookup
    if group_compiler.DEBUG_GENERATE_BASE:
        if modification_count > 0:
            print "Applied", modification_count, "transformations to the graph"
    return old_graph
