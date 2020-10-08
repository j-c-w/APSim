import FST
import compilation_statistics
# We need a value to indicate that an edges should not match
# anything.
DEBUG_UNIFICATION = False
PRINT_UNIFICATION_FAILURE_REASONS = False

# The maximum number of unifiers to keep in the unifier lists.
MAX_UNIFIERS = 20

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

    def add_insert(self, insert, edges_after):
        for unifier in self.unifiers:
            unifier.add_insert(insert, edges_after)

    def add_branch(self, branch, edges_after):
        for unifier in self.unifiers:
            unifier.add_branch(branch, edges_after)

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
        self.inserts = []
        self.branches = []

    def structural_modification_count(self):
        return len(self.inserts) + len(self.branches)

    def has_structural_additions(self):
        return len(self.inserts) > 0 or len(self.branches) > 0

    def add_insert(self, insert, edges_after):
        assert not insert.has_accept_before_first_edge()
        assert insert.first_edge() is not None

        self.inserts.append((insert, edges_after))

    def add_branch(self, branch, edges_after):
        assert not branch.has_accept_before_first_edge()
        assert branch.first_edge() is not None

        self.branches.append((branch, edges_after))

    def deep_clone(self):
        result = Unifier()
        result.isunifierlist = self.isunifierlist
        result.from_edges = self.from_edges[:]
        result.to_edges = self.to_edges[:]
        result.disabled_edges = self.disabled_edges[:]
        result.cost = self.cost
        result.ununified_terms = self.ununified_terms[:]
        result.branches = self.branches[:]
        result.inserts = self.inserts[:]
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
                for character in symbol_lookup_1[from_edge]:
                    # If the table is already set, then
                    # we need to make sure we are not changing
                    # the table:
                    if character not in lookup:
                        if PRINT_UNIFICATION_FAILURE_REASONS or DEBUG_UNIFICATION:
                            print "Unification failed due to double-mapped state"
                        return None
                # Also check that none of the already-mapped
                # symbols should not be.
                compilation_character_set = set(symbol_lookup_1[from_edge])
                for character in lookup:
                    if character not in compilation_character_set:
                        if PRINT_UNIFICATION_FAILURE_REASONS or DEBUG_UNIFICATION:
                            print "Unification failed due to double-mapped state"
                        return None

            else:
                lookup = {}
                for character in symbol_lookup_1[from_edge]:
                    lookup[character] = True

                state_lookup[dest_state] = lookup

        return FST.SymbolReconfiguration(state_lookup)

    # There may be some issues surrounding the naming convention
    # of what is 'from' and what is 'to' in this function (and
    # elsewhere tbh). Anyway, any issues with that should be aparent
    # even if a pain.
    def unify_single_state(self, symbol_lookup_1, symbol_lookup_2, options):
        # This unifies into a single state.
        state_lookup = {}
        matching_symbol = {}

        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            print "Starting new unification between "
            print self.algebra_from.str_with_lookup(symbol_lookup_2)
            print self.algebra_to.str_with_lookup(symbol_lookup_1)

        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            if self.algebra_from.equals(self.algebra_to, symbol_lookup_2, symbol_lookup_1):
                print "Algebras are actually exactly the same..."
                for i in range(len(self.from_edges)):
                    if symbol_lookup_1[self.from_edges[i]] != symbol_lookup_2[self.to_edges[i]]:
                        print "But edges are not the same..."

            compilation_statistics.exact_same_compilations += 1

        for i in range(len(self.from_edges)):
            if DEBUG_UNIFICATION:
                print "Trying to unify edges: "
                print self.from_edges[i]
                print self.to_edges[i]
                print symbol_lookup_1
                print symbol_lookup_2
                print "Symbol sets are:"
                print symbol_lookup_1[self.from_edges[i]]
                print symbol_lookup_2[self.to_edges[i]]
            from_chars = symbol_lookup_1[self.from_edges[i]]
            to_chars = symbol_lookup_2[self.to_edges[i]]

            for from_char in from_chars:
                if from_char in state_lookup:
                    overlap_set = set()
                    for character in state_lookup[from_char]:
                        if character in to_chars:
                            overlap_set.add(character)

                    if len(overlap_set) == 0:
                        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
                            print "Unification failed due to double-mapped state"
                            print "(" + str(from_char) + ") already mapped to " + str(state_lookup[from_char]) + " when something in " + str(to_chars) + " is required"
                        compilation_statistics.single_state_unification_double_map_fails += 1
                        return None
                    else:
                        # The overlap set is non-zero, but may
                        # still be smaller than it was before.
                        state_lookup[from_char] = overlap_set
                else: # Fromchar not in state lookup.
                    state_lookup[from_char] = to_chars

            if to_chars:
                for char in to_chars:
                    matching_symbol[char] = True

        # As an approximation, we need to make sure that we can disable any
        # of the edges that have to be added when running the original automaton.
        # We could look at the cost of adding a translator to the original automata too,
        # but we're not interested in that right now.
        for (branch, edges_after) in self.branches:
            # Only handle the 1 + a + e branches for the time being.
            if not branch.issum() and not branch.e1[0].isconst() and not branch.e1[1].isaccept() and \
                    not branch.e1[2].isend():
                return None

            # Need to be able to disable the first edge of the branch:
            target_symbolset = set()
            for edge in branch.first_edge():
                # Get the target symbolset from the first edge:
                source_characterset = symbol_lookup_2[edge]
                for char in source_characterset:
                    if char in state_lookup:
                        target_symbolset.add
                    else:
                        target_symbolset.add(char)

        disabling_symbols = set()
        for i in range(0, 256):
            if i not in matching_symbol:
                disabling_symbols.add(i)

        for (insert, edges_after) in self.inserts:
            # Only handle small inserts.
            if insert.size() > 2:
                return None

            if len(disabling_symbols) == 0:
                return None
            # We first need to pick the characterset for the insert --- use
            # all the characters in the first edge of the insert.
            insert_characterset = set()
            # The first edges can't be none if this was added
            # as an insert --- that would mean this is going to be
            # difficult to disable I think...
            assert insert.first_edge() is not None
            for edge in insert.first_edge():
                for character in symbol_lookup_2[edge]:
                    # This could definitely be moved up to the part before state_lookup is
                    # solidified.
                    if character in state_lookup:
                        for c in state_lookup[character]:
                            insert_characterset.add(c)
                    else:
                        # assume that we will map character to itself.
                        insert_characterset.add(character)

            # Now, make sure that we can disable that edge in normal use of
            # the accelerator.  We do that by mapping the contents of that edge
            # to one of the non_matching symbols.
            for character in insert_characterset:
                # Try to map this character to one of the disabled characters:
                if character in state_lookup:
                    existing_set = state_lookup[character]
                    new_set = disabling_symbols.intersection(existing_set)
                    if len(new_set) == 0:
                        return None
                    else:
                        state_lookup[character] = new_set

                    # TODO --- Need to disable one of the characters in
                    # the new_set from the matching_set.   this is actually
                    # broken until that happens.
                else:
                    state_lookup[character] = [sorted(list(disabling_symbols))[0]]
                    # this is now a symbol that matches this edge.
                    # TODO -- need to make clear that the disabling set is for this
                    # particular structure.
                    matching_symbol[(sorted(list(disabling_symbols))[0])] = True

            # Need to make sure that every character in the loop is treated
            # as a matching symbol and not used as a disabling symbol.
            # for edge in insert.all_edges():
            # For now, we skip this by failing unless A is a single element big :)


        # Now, go through and map any None values, which mean
        # that symbols should be mapped to things that don't match
        # any edges.
        non_matching = None
        non_matching_set = set()
        for i in range(0, 256):
            if i not in matching_symbol:
                non_matching_set.add(i)
                non_matching = i

        # We can't have symbols accidentally activating an edge
        # they are not meant to.  Go through and make sure
        # that they aren't doing that.
        for i in range(len(self.from_edges)):
            # Each edge lines up to exactly one other edge ---
            # the other edges might line up to more than
            # one of the from_edges though.
            from_symbols = symbol_lookup_1[self.from_edges[i]]

            for j in range(len(self.to_edges)):
                if j == i:
                    continue # No restrictions matching yourself.

                other_symbols = symbol_lookup_2[self.to_edges[j]]

                for from_symbol in from_symbols:
                    # These are the symbols that activate this
                    # other edge.  Need to not translate to these...
                    for symb in other_symbols:
                        if symb in state_lookup[from_symbol]:
                            state_lookup[from_symbol].remove(symb)
                            if len(state_lookup[from_symbol]) == 0:
                                # Fail because now there are no options to translate this symbol to.
                                return False

        disabled_edges = self.get_disabled_edges()
        if non_matching is None and len(disabled_edges) != 0 and not options.disabled_edges_approximation:
            if DEBUG_UNIFICATION:
                print "Unification failed due to required edge disabling that cannot be achieved"
            compilation_statistics.single_state_unification_non_matching += 1
            return None
        elif non_matching is not None:
            for disable in disabled_edges:
                state_lookup[disable] = non_matching

        # Translate everything else to itself.  This is an
        # relatively arbitrary decision I'm pretty sure.
        for i in range(0, 256):
            if chr(i) not in state_lookup:
                state_lookup[chr(i)] = chr(i)

        if DEBUG_UNIFICATION or PRINT_UNIFICATION_FAILURE_REASONS:
            print "Returning a real result"

        compilation_statistics.single_state_unification_success += 1
        modification_count = len(self.branches) + len(self.inserts)
        return FST.SingleStateTranslator(state_lookup, modification_count)
