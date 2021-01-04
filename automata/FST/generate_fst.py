import sys
import FST
from unifier import Modifications

class GenerationFailureReason(object):
    def __init__(self, reason):
        self.reason = reason

def expand_ranges(ranges):
    ranges = list(ranges)
    result = []
    for char_range in ranges:
        left = char_range.left.point
        right = char_range.right.point

        # Not sure I understand the case where these fail.
        # The packed input objects (see ste.py) seem excessively
        # complicated.
        assert len(left) == 1
        assert len(right) == 1
        result += range(left[0], right[0] + 1)
    return set(result)

def edge_label_lookup_generate(atma):
    edges = list(atma.get_edges(data=True))
    lookup = {}
    for (to, from_ind, data) in edges:
        symbols = expand_ranges(data['symbol_set'])
        lookup[(to, from_ind)] = symbols
    return lookup

# Given a component, generate a map to itself.
def generate_self_map(component, options):
    if options.target == 'single-state':
        return FST.EmptySingleStateTranslator()
    elif options.target == 'symbol-only-reconfiguration':
        lookup = {}
        for edge in component.algebra.all_edges():
            start, end = edge
            symbols = component.automata.symbol_lookup[edge]
            lookup[end] = symbols
        return FST.SymbolReconfiguration(lookup, Modifications([], []))
    elif options.target == 'perfect-unification':
        result = FST.AllPowerfulUnifier(Modifications([], []))

def generate(unification, to_atma, from_atma, options):
    assert unification is not None
    # Get the lookup tables.

    to_edge_lookup = to_atma.symbol_lookup
    from_edge_lookup = from_atma.symbol_lookup

    best_result = None
    best_structural_modification_count = 1000000
    best_overapproximation_factor = 1000000
    unifiers_attempted = 0

    unification = sorted(unification, key=lambda u: u.structural_modification_count())

    for unifier in unification:
        if not unifier:
            continue
        else:
            unifiers_attempted += 1

        if options.target == 'single-state':
            result = unifier.unify_single_state(from_edge_lookup, to_edge_lookup, options)
        elif options.target == 'symbol-only-reconfiguration':
            result = unifier.unify_symbol_only_reconfigutaion(to_edge_lookup, from_edge_lookup, options)
        elif options.target == 'perfect-unification':
            result = FST.AllPowerfulUnifier(Modifications(unifier.additions_between_nodes, unifier.additions_from_node))
        else:
            print "Unkown target " + options.target
            sys.exit(1)

        # We want to return results with 0 structural modification
        # where possible.  So, if we find one with structural
        # modification, then keep going.
        structural_modification_count = unifier.structural_modification_count()
        # We also keep track of the overapproximation factor, i.e.
        # how many edges are overapproximated.
        if result:
            overapproximation_factor = result.overapproximation_factor()

        if result and structural_modification_count == 0 and overapproximation_factor <= 0.000005:
            # Auto-return if we get an answer with 0 modification and
            # no overapproximation.
            return result, None
        elif result and (overapproximation_factor < best_overapproximation_factor or \
                (structural_modification_count < best_structural_modification_count and overapproximation_factor <= best_overapproximation_factor + 0.0005)): 
            best_result = result
            best_structural_modification_count = structural_modification_count
            best_overapproximation_factor = overapproximation_factor

    if best_result is not None:
        return best_result, None
    elif unifiers_attempted > 0:
        return None, GenerationFailureReason("Unification Failure")
    elif unifiers_attempted == 0:
        return None, GenerationFailureReason("Structural Failure")
