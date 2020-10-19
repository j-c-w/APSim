import FST
import compilation_statistics
# We need a value to indicate that an edges should not match
# anything.
DEBUG_UNIFICATION = False
PRINT_UNIFICATION_FAILURE_REASONS = False

# The maximum number of unifiers to keep in the unifier lists.
MAX_UNIFIERS = 20

# This is a fast set for sets of 255 elements --- like the ones
# we use below.
class FastSet(object):
    def __init__(self, preset=[]):
        self.elements = [False] * 256
        for x in preset:
            self.elements[x] = True
        self.elt_count = len(preset)

    def __contains__(self, elt):
        return self.elements[elt] == True

    def add(self, elt):
        self.elements[elt] = True
        self.elt_count += 1

    def remove(self, elt):
        if self.elements[elt]:
            self.elt_count -= 1
            self.elements[elt] = False

    def __list__(self):
        return self.elements

    def __len__(self):
        return self.elt_count

    def __iter__(self):
        for i in range(256):
            if self.elements[i]:
                yield i

    def __str__(self):
        result = "(" + ",".join([x for x in range(0, 256) if self.elements[x]]) + ")"
        return result

    def __eq__(self, other):
        if self.elt_count != other.elt_count:
            return False

        for i in range(0, 256):
            if self.elements[i] != other.elements[i]:
                return False
        return True

    @staticmethod
    def big_intersection(sets):
        result = FastSet()
        for i in range(256):
            result.add(i)
            for s in sets:
                if i not in s:
                    result.remove(i)
                    break
        return result

# This class is a stupid abstrction that we need because I designed
# the algebra.leq functions around a single unifier, then I realized
# that the abstraction where we separate structural equality and
# character equality creates problems when it comes to branches,
# where multiple arms may share structural equality, but only a single
# grouping might have character set compatability.  This class
# aims to address that by providing a transparent list-based wrapper
# around the unifiers --- the aim is to keep the leq functions roughly
# as they are.
# So, this has a wrapper function around everything that the Unifier
# provides.
class UnifierList(object):
    def __init__(self, unifiers):
        self.unifiers = [u for u in unifiers if u is not None]
        self.isunifierlist = True
        self.trim_unifier_list()

    def append_unifiers(self, unifiers):
        if unifiers.isunifierlist:
            for other_unifier in unifiers.unifiers:
                if other_unifier is not None:
                    self.unifiers.append(other_unifier)
        else:
            if unifiers is not None:
                self.unifiers.append(unifiers)

        self.trim_unifier_list()

    def add_between_nodes(self, insert, edge_to_snip):
        for unifier in self.unifiers:
            unifier.add_between_nodes(insert, edge_to_snip)

    def add_from_node(self, branch, edges_after):
        for unifier in self.unifiers:
            unifier.add_from_node(branch, edges_after)

    def trim_unifier_list(self):
        if len(self.unifiers) > MAX_UNIFIERS:
            compilation_statistics.unifier_trimming_events += 1
            self.unifiers = self.unifiers[:MAX_UNIFIERS]

    def as_list(self):
        compilation_statistics.unifiers_returned += len(self.unifiers)
        return self.unifiers

    def length(self):
        return len(self.unifiers)

    def set_algebra_to(self, A):
        for unifier in self.unifiers:
            unifier.algebra_to = A

    def set_algebra_from(self, B):
        for unifier in self.unifiers:
            unifier.algebra_from = B

    def add_edges(self, from_edges, to_edges):
        for unifier in self.unifiers:
            unifier.add_edges(from_edges, to_edges)

    def set_ununified_terms(self, terms):
        for unifier in self.unifiers:
            unifier.set_ununified_terms(terms)

    def add_disabled_edges(self, edges):
        for unifier in self.unifiers:
            unifier.add_disabled_edges(edges)

    def add_cost(self, cost):
        for unifier in self.unifiers:
            unifier.add_cost(cost)

    def get_disabled_edges(self):
        assert False # You have to call this on the individual unifiers.

    def unify_with(self, other):
        if other.isunifierlist:
            # We want to return the cross-product of unifiers if these are both lists.
            new_unifiers = []
            for unifier in self.unifiers:
                for other_unifier in other.unifiers:
                    cloned_unifier = unifier.deep_clone()
                    cloned_unifier.unify_with(other_unifier)
                    new_unifiers.append(cloned_unifier)
            self.unifiers = new_unifiers
            self.trim_unifier_list()
        else:
            # The other is a single unifier, so unify with every element of the list.
            for unifier in self.unifiers:
                if unifier is not None:
                    unifier.unify_with(other)

    def __str__(self):
        return "[" + ", ".join([str(u) for u in self.unifiers]) + "]"

class Unifier(object):
    def __init__(self, algebra_from=None, algebra_to=None, cost=0):
        self.isunifierlist = False
        self.from_edges = []
        self.to_edges = []
        self.disabled_edges = []
        self.algebra_from = algebra_from
        self.algebra_to = algebra_to
        self.cost = cost
        self.ununified_terms = []
        # What modifications have to be made to the underlying automata
        # for a successful conversion?
        self.additions_between_nodes = []
        self.additions_from_node = []

    # Return a count of all the edges represented in the 'from'
    # portion of this unifier.
    def all_from_edges_count(self):
        return len(self.all_from_edges())

    def all_from_edges(self):
        result = set(self.from_edges)
        for mod in self.additions_between_nodes + self.additions_from_node:
            result = result.union(mod.algebra.all_edges())
        return result

    def structural_modification_count(self):
        return len(self.additions_between_nodes) + len(self.additions_from_node)

    def has_structural_additions(self):
        return len(self.additions_between_nodes) > 0 or len(self.additions_from_node) > 0

    # Note taht for this and teh additions_from_node, the 'insert' corresponds
    # to the automata we are going to accelerate,
    # the edges after corresponds to the automata we have an
    # accelerator for
    def add_between_nodes(self, insert, edge_to_snip):
        assert not insert.has_accept_before_first_edge()
        assert insert.first_edge() is not None

        self.additions_between_nodes.append(InsertModification(insert, edge_to_snip))

    def add_from_node(self, branch, edges_after):
        assert not branch.has_accept_before_first_edge()
        assert branch.first_edge() is not None

        self.additions_from_node.append(Modification(branch, edges_after))

    def deep_clone(self):
        result = Unifier()
        result.isunifierlist = self.isunifierlist
        result.from_edges = self.from_edges[:]
        result.to_edges = self.to_edges[:]
        result.disabled_edges = self.disabled_edges[:]
        result.cost = self.cost
        result.ununified_terms = self.ununified_terms[:]
        result.additions_from_node = self.additions_from_node[:]
        result.additions_between_nodes = self.additions_between_nodes[:]
        # We don't deep clone this because it's immutable from
        # the perspective of a unifier.
        result.algebra_from = self.algebra_from
        result.algebra_from = self.algebra_to

        return result

    def set_algebra_from(self, A):
        self.algebra_from = A

    def set_algebra_to(self, A):
        self.algebra_to = A

    def add_edges(self, from_edges, to_edges):
        assert len(from_edges) == len(to_edges)

        self.from_edges += from_edges
        self.to_edges += to_edges

    def set_ununified_terms(self, terms):
        assert self.ununified_terms == []
        self.ununified_terms.append(terms)

    # Add some edges to make sure are never active.
    def add_disabled_edges(self, edges):
        self.disabled_edges += edges

    def add_cost(self, cost):
        self.cost += cost

    def get_disabled_edges(self):
        return self.disabled_edges

    def unify_with(self, other):
        self.from_edges += other.from_edges
        self.to_edges += other.to_edges
        self.cost += other.cost
        self.additions_from_node += other.additions_from_node
        self.additions_between_nodes += other.additions_between_nodes
        self.ununified_terms.append(other.ununified_terms)

    def unify_symbol_only_reconfigutaion(self, symbol_lookup_1, symbol_lookup_2, options):
        # In this unification method, we can unify each state individually ---
        # giving us much better compression.
        state_lookup = {}
        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            print "Starting new unification between (symbol-only-reconfiguration mode)"
            print self.algebra_from.str_with_lookup(symbol_lookup_1)
            print self.algebra_to.str_with_lookup(symbol_lookup_2)

        for i in range(len(self.from_edges)):
            # Try and unify the individual edges  --- This should almost always
            # work.
            from_edge = self.from_edges[i]
            to_edge = self.to_edges[i]

            # since each state is homogeneous, the question is "does this
            # state get enabled on this particular input character?"
            # and we aim to change the answer from the one in 'from_edge'
            # to the one in to_edge.
            _, dest_state = from_edge
            if dest_state in state_lookup:
                lookup = state_lookup[dest_state]
                # We want to enable every  character coming
                # into this edge.  We can't double map things
                # though. --- In this part, we need to check that
                # we are not double mapping.
                # Check that nothing that needs to be mapped
                # is not already.
                for character in symbol_lookup_2[from_edge]:
                    # If the table is already set, then
                    # we need to make sure we are not changing
                    # the table:
                    if character not in lookup:
                        if PRINT_UNIFICATION_FAILURE_REASONS or DEBUG_UNIFICATION:
                            print "Unification failed due to double-mapped state"
                        return None
                # Also check that none of the already-mapped
                # symbols should not be.
                compilation_character_set = FastSet(symbol_lookup_2[from_edge])
                for character in lookup:
                    if character not in compilation_character_set:
                        if PRINT_UNIFICATION_FAILURE_REASONS or DEBUG_UNIFICATION:
                            print "Unification failed due to double-mapped state"
                        return None

            else:
                lookup = {}
                for character in symbol_lookup_2[from_edge]:
                    lookup[character] = True

                state_lookup[dest_state] = lookup

        modifications = Modifications(self.additions_from_node, self.additions_between_nodes, symbol_lookup_2)
        return FST.SymbolReconfiguration(state_lookup, modifications)

    # There may be some issues surrounding the naming convention
    # of what is 'from' and what is 'to' in this function (and
    # elsewhere tbh). Anyway, any issues with that should be aparent
    # even if a pain.
    def unify_single_state(self, symbol_lookup_1, symbol_lookup_2, options):
        # This unifies into a single state.
        state_lookup = {}
        matching_symbol = {}

        if options.use_unification_heuristics and mapping_heuristic_fail(self.from_edges, self.to_edges, symbol_lookup_1, symbol_lookup_2, options):
            compilation_statistics.ssu_heuristic_fail += 1
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Failed matching heursitic..."
            return None

        if DEBUG_UNIFICATION:
            print "Starting new unification between "
            print self.algebra_from.str_with_lookup(symbol_lookup_2)
            print self.algebra_to.str_with_lookup(symbol_lookup_1)

        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            if self.algebra_from.equals(self.algebra_to, symbol_lookup_1, symbol_lookup_2):
                print "Algebras are actually exactly the same..."
                for i in range(len(self.from_edges)):
                    if symbol_lookup_1[self.from_edges[i]] != symbol_lookup_2[self.to_edges[i]]:
                        print "But edges are not the same..."

            compilation_statistics.exact_same_compilations += 1

        # Generate a mapping that is complete, but not correct. (i.e. does not miss anything)
        state_lookup, matching_symbol = generate_complete_mapping(self.from_edges, self.to_edges, symbol_lookup_1, symbol_lookup_2, options)
        if state_lookup is None:
            compilation_statistics.ssu_complete_mapping_failed += 1
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Failing due to completeness fail"
            return None

        # Make that mapping correct. (i.e. not an overapproximation)
        # Even if we aren't required to do this, it is good
        # to reduce the overapproximation error rate.
        state_lookup = generate_correct_mapping(state_lookup, self.from_edges, self.to_edges, symbol_lookup_1, symbol_lookup_2, options)
        if state_lookup is None:
            compilation_statistics.ssu_correct_mapping_failed += 1
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Failing due to generate correct fail"
            return None

        # Check that we would be able to unify with the structural
        # modifications:  this just has to be an approximation, because
        # we don't really use this to unify, just to guide decisions
        # for a later reconstruction pass.
        state_lookup, matching_symbol = generate_additions_mapping(state_lookup, matching_symbol, self.from_edges, self.to_edges, symbol_lookup_1, symbol_lookup_2, self.additions_between_nodes, self.additions_from_node, options)

        if state_lookup is None:
            compilation_statistics.ssu_additions_failed += 1
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Failing due to generate additions failed"
            return None

        # This is correctness, not completeness related:
        non_matching = compute_non_matching_symbol(matching_symbol)
        if options.correct_mapping:
            # Get the non-matching symbols:

            # We can't have a symbol activating an edge that it is not
            # supposed to activate.
            # Go through and get all the valid activating symbols
            # together
            state_lookup = disable_edges(state_lookup, non_matching, self.get_disabled_edges(), options)

            if state_lookup is None:
                compilation_statistics.ssu_disable_edges_failed += 1
                if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                    print "Failing due to disable edge fail"
                return None

        # Collapse any symbol sets that are still more than one element,
        # and also complete the conversion table to include
        # all characters.
        state_lookup = collapse_and_complete_state_lookup(state_lookup, non_matching, options)

        if state_lookup is None:
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Failing due to disabled symbols fail"
            compilation_statistics.ssu_disable_symbols_failed += 1
            return None

        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            print "Returning a real result"
        compilation_statistics.ssu_success += 1

        modifications = Modifications(self.additions_from_node, self.additions_between_nodes, symbol_lookup_1)
        return FST.SingleStateTranslator(state_lookup, modifications, unifier=self)

class Modifications(object):
    def __init__(self, additions_from_node, additions_between_nodes, symbol_lookup):
        self.additions_from_node = additions_from_node
        self.additions_between_nodes = additions_between_nodes
        self.symbol_lookup = symbol_lookup

    def __len__(self):
        return len(self.additions_from_node) + len(self.additions_between_nodes)

    def all_modifications(self):
        return self.additions_from_node + self.additions_between_nodes

    def __str__(self):
        return "[" + ','.join([str(x) for x in self.all_modifications()]) + ']'

class InsertModification(object):
    def __init__(self, algebra, edge):
        self.algebra = algebra
        self.edge = edge

    def __str__(self):
        return str(self.algebra) + " Inserted over " + str(self.edge)

    def isinsert(self):
        return True

    def is_between_nodes(self):
        return True

class Modification(object):
    def __init__(self, algebra, edges_after):
        self.algebra = algebra
        self.edges_after = edges_after

    def __str__(self):
        return str(self.algebra) + " Inserted before " + str(self.edges_after)

    def isinsert(self):
        return False

    def is_between_nodes(self):
        return False

def mapping_heuristic_fail(from_edges, to_edges, symbol_lookup_from, symbol_lookup_to, options):
    # Go through the mappings and look at the ones that don't
    # require set operations to refute --- much faster than the
    # full unificadtion set-based algorithm.
    # This is an effective heuristic, but it doesn't save much
    # time --- it gets rid of the things that would be quickly
    # discounted by the complete mapping generator anyway.
    single_mappings = {}
    for edge_index in range(len(from_edges)):
        from_set = symbol_lookup_from[from_edges[edge_index]]
        to_set = symbol_lookup_to[to_edges[edge_index]]

        # The size of the from_set here is just trading off computation
        # time spinning in this loop for every state vs
        # things we could reject that would get through.
        if len(to_set) == 1 and len(from_set) < 10:
            to_elt = list(to_set)[0]

            for from_elt in from_set:
                if from_elt in single_mappings and single_mappings[from_elt] != to_elt:
                    return True
                single_mappings[from_elt] = to_elt

    return False

# Given a set of input edges and output edges, generate a set
# of input/output assignments that /does not double-map any symbol/
# (return None, None if it does double-map a symbol).
def generate_complete_mapping(from_edges, to_edges, symbol_lookup_1, symbol_lookup_2, options):
    state_lookup = {}
    uncompressed_state_lookup = {}
    matching_symbol = FastSet()
    for i in range(len(from_edges)):
        if DEBUG_UNIFICATION:
            print "Trying to unify edges: "
            print from_edges[i]
            print to_edges[i]
            print symbol_lookup_1
            print symbol_lookup_2
            print "Symbol sets are:"
            print symbol_lookup_1[from_edges[i]]
            print symbol_lookup_2[to_edges[i]]
        from_chars = symbol_lookup_1[from_edges[i]]
        to_chars = symbol_lookup_2[to_edges[i]]

        for from_char in from_chars:
            if from_char in uncompressed_state_lookup:
                uncompressed_state_lookup[from_char].append(to_chars)
            else:
                uncompressed_state_lookup[from_char] = [to_chars]

        for char in to_chars:
            matching_symbol.add(char)

    for char in uncompressed_state_lookup:
        # overlap_set = uncompressed_state_lookup[char][0].intersection(*uncompressed_state_lookup[char])
        overlap_set = FastSet.big_intersection(uncompressed_state_lookup[char])

        if len(overlap_set) == 0:
            if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                print "Unification failed due to double-mapped state"
                print "(" + str(char) + ") needs to be mapped to " + str(overlap_set) + "which is not possible"
                print 'u'.join([str(x) for x in uncompressed_state_lookup[char]])
            return None, None
        state_lookup[char] = overlap_set

    return state_lookup, matching_symbol

def generate_additions_mapping(state_lookup, matching_symbol, from_edges, to_edges, symbol_lookup_1, symbol_lookup_2, additions_between_nodes, additions_from_node, options):
    # As an approximation, we need to make sure that we can disable any
    # of the edges that have to be added when running the original automaton.
    # We could look at the cost of adding a translator to the original automata too,
    # but we're not interested in that right now.
    unmodified_matching_symbol = FastSet(matching_symbol)
    for modification in additions_from_node + additions_between_nodes:
        branch = modification.algebra

        # TODO --- We should really be able to just translate ---
        # this requies some co-behaviour between this stage and
        # the automata editing stage.
        # i.e., we don't actually require that the labelling on
        # these edges stays as-is --- it would be beneficial
        # if they
        if modification.is_between_nodes():
            # The last edge will have the same edge value
            # as the ones going into the last node.
            last_node = modification.edge[1]

            # Make sure that the two input symbols are the same:
            inserted_last_symbol_set = None
            for (from_e, to_e) in branch.all_edges():
                if to_e == branch.get_last_node():
                    inserted_last_symbol_set = symbol_lookup_1[(from_e, to_e)]
            assert inserted_last_symbol_set is not None

            # Then, find an underlying accelerator edge
            # coming into the target node --- need to make
            # sure the symbol set on that is the same.
            for (from_e, to_e) in to_edges:
                if to_e == last_node:
                    # Get the symbol set
                    other_last_symbol_set = symbol_lookup_2[(from_e, to_e)]
                    if inserted_last_symbol_set != other_last_symbol_set:
                        if PRINT_UNIFICATION_FAILURE_REASONS or DEBUG_UNIFICATION:
                            print "Failed due to insert symbols not lining up"
                        compilation_statistics.ssu_structural_addition_homogeneity_fail += 1

                        return False
                    break
        else:
            # If this is a loop, need to check that it has the same
            # input symol as the loop it is attached to.
            # Not currently implemented because I think this should
            # happen due to homogeneity of all input graphs involved,
            # but it would be a good check.
            pass

        # We should check whether we will be able to do completeness:
        # That is; can we map the input symbols for the added
        # edge to one of themselves?
        incoming_symbols = symbol_lookup_1[branch.first_edge()[0]]
        for symbol in incoming_symbols:
            if symbol in state_lookup:
                targets = state_lookup[symbol]
            else:
                targets = FastSet(range(256))
                matching_symbol.add(symbol)
            new_targets = FastSet(targets)
            for target in targets:
                if not target in incoming_symbols:
                    if DEBUG_UNIFICATION:
                        print "Removing symbol", target, "from the potential targets..."
                    new_targets.remove(target)
                    if len(new_targets) == 0:
                        if DEBUG_UNIFICATION:
                            print "Failed to unify because we cannot target the new edge appropriately."
                        compilation_statistics.ssu_addition_completeness_fail
                        return None, matching_symbol
            state_lookup[symbol] = new_targets

        # And, if required, correctness.
        if options.correct_mapping:
            # We need to check that the incoming edge to this node
            # can be disabled.
            assert len(branch.first_edge()) == 1
            incoming_symbols = symbol_lookup_1[branch.first_edge()[0]]
            for symbol in incoming_symbols:
                if symbol in unmodified_matching_symbol:
                    if DEBUG_UNIFICATION:
                        print "Failed to unify because we cannot disable edge on addition"
                    compilation_statistics.ssu_addition_correctness_fail += 1
                    return None, matching_symbol

    return state_lookup, matching_symbol

def compute_non_matching_symbol(matching):
    # Now, go through and map any None values, which mean
    # that symbols should be mapped to things that don't match
    # any edges.
    non_matching = None
    non_matching_set = FastSet()
    for i in range(0, 256):
        if i not in matching:
            non_matching_set.add(i)
            non_matching = i

    return non_matching

def disable_edges(state_lookup, non_matching, disabled_edges, options):
    if non_matching is None and len(disabled_edges) != 0 and not options.disabled_edges_approximation and options.correct_mapping:
        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            print "Unification failed due to required edge disabling that cannot be achieved"
        return None
    elif non_matching is not None:
        for disable in disabled_edges:
            state_lookup[disable] = non_matching

    return state_lookup

def collapse_and_complete_state_lookup(state_lookup, non_matching, options):
    # Translate everthing not mapped to the non_matching character
    # if we don't have correctness, then we can translate things
    # to themselves in the event that there is no non-matching character.
    # otherwise, we have to fail, because the character will
    # activate an edge, and the virtual symbol set doesn't have 
    # that edge active.
    for i in range(0, 256):
        if i in state_lookup:
            state_lookup[i] = list(state_lookup[i])[0]
        else:
            if non_matching:
                state_lookup[i] = non_matching
            elif not options.correct_mapping:
                # We can just do whatever with this symbol,
                # it isn't required for completeness.
                state_lookup[i] = i
            else:
                # We have to fail.
                if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                    print "Failed due to inability to disable input character."
                return None
    return state_lookup
                    

def generate_correct_mapping(state_lookup, from_edges, to_edges, symbol_lookup_1, symbol_lookup_2, options):
    # The aim here is to make sure that we don't have any 'false'
    # activations --- go through all the edges, and build
    # up a dictionary of what translates to what.
    # We build 'activation sets', of edges that are activated
    # by particular characters.  We then remove symbols from
    # the state lookup that activate the wrong edges and see
    # if there is anything left.

    if DEBUG_UNIFICATION:
        print "Forcing correct mapping..."

    # Which edges are activated by each character
    accelerator_active_edges = {}
    # Which edges need to be active for each character
    base_active_edge_mapping = {}

    for i in range(0, 256):
        accelerator_active_edges[i] = set()
        base_active_edge_mapping[i] = set()

    for j in range(len(from_edges)):
        from_edge = from_edges[j]
        to_edge = to_edges[j]

        for i in symbol_lookup_2[to_edge]:
            accelerator_active_edges[i].add(to_edge)

        # Aldo so the same thing for tbe base_active_edges:
        for i in symbol_lookup_1[from_edge]:
            base_active_edge_mapping[i].add(to_edge)

    # Now we have a set of edges that have to be active for
    # each character, and a set of edges that are activated
    # for each character, so go through and make sure that
    # those are exact:
    for i in range(0, 256):
        # When we translate this character, we will get something
        # from the set:
        if i not in state_lookup:
            continue # If there's not mappings for this symbol, 
        # we don't need to deal with that here.
        targets = state_lookup[i]

        # We need to make sure this doesn't activate anything
        # we don't want, so compute the set of all activated nodes
        # for each character in targets:

        # Compute the edges we can't activate:
        edges_inactive = set()
        edges_active = base_active_edge_mapping[i] # edges the must be active
        all_activated = set().union(*[accelerator_active_edges[x] for x in targets])

        for edge in all_activated:
            if edge not in edges_active:
                edges_inactive.add(edge)

        if DEBUG_UNIFICATION:
            print "Active edges is "
            print edges_active
            print "Inactive edges is "
            print edges_inactive

        # Algorithm here is to:
        # 1: remove all the characters in the unactive set
        # 2: see if the remaining characters can cover the active set.
        # 1: build the inactive set --- the characters we can't use.
        invalid_symbols = set().union(*[symbol_lookup_2[edge] for edge in edges_inactive])

        if DEBUG_UNIFICATION:
            print "Invalid symbols is"
            print invalid_symbols

        # 2: find the active set --- the characters that activate things.
        new_symbols = FastSet()
        for character in targets:
            if character not in invalid_symbols:
                new_symbols.add(character)

        if len(new_symbols) == 0:
            # We failed to add any character that could activate this edge.
            if options.correct_mapping:
                if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                    print "Failed due to unnessecarily activated edges"
                return None
            else:
                # Pick a single symbol anyway --- it is OK to activate
                # some other edges to get the right edge activation.
                # This is obviously an approximation here -- it would be better
                # to pick the character that activates the fewest non-desired edges.
                new_symbols.add(list(targets)[0])
        state_lookup[i] = new_symbols
        if DEBUG_UNIFICATION:
            print "Successfully reduced edges for character ", i
            print "Had", len(targets), "options before, and ", len(new_symbols), "options now"
    return state_lookup
