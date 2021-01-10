import unittest
from automata.FST.terms import *
from automata.FST.options import EmptyOptions
import automata.FST.unifier as unifier
from automata.FST.unifier import Modifications, Modification
import automata.FST.algebra as alg


class AlgebraTest(unittest.TestCase):
    def test_long_loop(self):
        nodes = [0, 1654, 1655, 1656, 1657, 1658, 1659, 1660, 1661]
        edges = [(1654, 1661), (1654, 1654), (1654, 1655), (1661, 1661), (1661, 1654), (1661, 1655), (1659, 1660), (1659, 1661), (1660, 1660), (1660, 1661), (1658, 1659), (1657, 1658), (1656, 1657), (0, 1656)]
        algebra = alg.generate(nodes, edges, 0, [1657], EmptyOptions)
        for edge in algebra.all_edges():
            self.assertTrue(edge in edges)
        # I'm really not sure about tha e in the middle of the loop.
        # Seems like there is a simple equivalent to me?  Not sure
        # though.
        # Don't think it's incorrect, just obtuse and hard to 
        # compile to.
        self.assertEqual(str(algebra), '2 + a + 2 + {1, 1 + (1)* + 1} + ({1, 1 + (1)* + 1 + e})* + 1 + e')

    # It is not 100% clear to me that these should nessecarily
    # be of the format a + (1 + a)*, rather than (a + 1)*.
    # I think that the later requires applying the loop rolling
    # property, but I'm not actually sure.
    def test_trailing_product_2(self):
        algebra = alg.generate([0, 1, 2, 3, 4, 5], [(0, 1), (1, 3), (3, 4), (1, 4), (4, 5), (5, 4)], 0, [4], EmptyOptions)
        self.assertEqual("1 + {1, 2} + a + (2 + a)*", str(algebra))

    def test_trailing_product(self):
        algebra = alg.generate([0, 1, 2, 3, 4], [(0, 1), (1, 3), (3, 4), (1, 4), (4, 4)], 0, [4], EmptyOptions)
        self.assertEqual("1 + {1, 2} + a + (1 + a)*", str(algebra))

    def test_trailing_product_3(self):
        nodes = [4, 5, 6, 7, 0, 8, 11]
        edges =  [(4, 5), (4, 6), (5, 6), (6, 7), (7, 8), (0, 4), (7, 11), (7, 7)]
        accepting = [11]
        start = 0
        algebra = alg.generate(nodes, edges, start, accepting, EmptyOptions)
        print algebra
        self.assertEqual(str(algebra), "1 + {1, 2} + 1 + (1)* + {1 + e, 1 + a + e}")


    def test_simpleTest(self):
        simple = alg.generate([0, 1, 2, 3], [(0, 1), (1, 2), (2, 3)], 0, [3], EmptyOptions)
        self.assertEquals("3 + a + e", str(simple))

    # Generated from a failing exmapl
    def test_cross_loop(self):
        nodes = [0, 1, 2, 3, 4, 5]
        edges = [(0, 1), (0, 2), (2, 3), (3, 4), (4, 2), (1, 5), (1, 3), (2, 5)]
        # print alg.generate(nodes,edges, 0, [5])

    def test_branch(self):
        simple_branches = alg.generate([0, 1, 2], [(0, 1), (0, 2)], 0, [1, 2], EmptyOptions)
        self.assertEquals("{1 + a + e, 1 + a + e}", str(simple_branches))

        delayed_branches = alg.generate([0, 1, 2, 3], [(0, 1), (1, 2), (1, 3)], 0, [2], EmptyOptions)
        self.assertEquals("1 + {1 + a + e, 1 + e}", str(delayed_branches))

    def test_complex_branch(self):
        branches = alg.generate([0, 1, 2, 3, 4, 5], [(0, 1), (0, 2), (0, 3), (3, 4), (3, 5)], 0, [2, 3, 5], EmptyOptions)
        self.assertEquals(str(branches), "{1 + e, 1 + a + e, 1 + a + {1 + e, 1 + a + e}}")

    def test_generate_linear_algebras(self):
        simple = str(alg.linear_algebra_for([0, 1, 2], [2]).normalize())
        self.assertEquals("2 + a", simple)

    def test_simple_loop(self):
        loop = alg.generate([0, 1, 2, 3], [(0, 1), (1, 2), (2, 1), (1, 3)], 0, [3], EmptyOptions)
        self.assertEquals("1 + (2)* + 1 + a + e", str(loop))

    def test_simple_loop_2(self):
        loop = alg.generate([0, 1, 2, 3, 4], [(0, 1), (1, 2), (2, 1), (2, 3), (3, 2), (1, 4)], 0, [4], EmptyOptions)
        self.assertEquals("1 + (1 + (2)* + 1)* + 1 + a + e", str(loop))

    def test_mono_loop(self):
        loop = alg.generate([0], [(0, 0)], 0, [0], EmptyOptions)
        # I am not actually sure this is correct --- it might
        # need to be a + (1 + a)*?  --- Not too sure though.
        # Also not sure it matters.
        self.assertEqual("(1 + a)*", str(loop))

    # This is an edge case we don't really handle well, but
    # it isn't incorrect -- the algebra just makes the automaton
    # seem more general than it is.  That problem will get
    # fixed upon unification though.
    def test_diverging_triple(self):
        triple = alg.generate([0, 1, 2, 3, 4], [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 4), (3, 4)], 0, [4], EmptyOptions)
        print str(triple)

    def test_converging_triple(self):
        triple = alg.generate([0, 1, 2, 3, 4], [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (1, 4), (2, 4)], 0, [4], EmptyOptions)
        print triple

    def test_multiple_removed_edges(self):
        res = alg.generate([0, 1, 2, 3, 4], [(0, 1), (1, 1), (1, 2), (2, 1), (2, 3), (3, 4)], 0, [4], EmptyOptions)
        print(res)

    def test_multiple_loops(self):
        res = alg.generate([0, 1, 2, 3, 4], [(0, 1), (1, 2), (2, 1), (1, 3), (3, 1), (1, 4)], 0, [4], EmptyOptions)

    def test_double_branch(self):
        res = alg.generate([0, 1, 2, 3, 4, 5], [(0, 1), (0, 2), (2, 3), (1, 3), (3, 4), (3, 5)], 0, [], EmptyOptions)
        self.assertEqual(str(res), "{2, 2} + {1 + e, 1 + e}")

    def test_double_branch_2(self):
        res = alg.generate([0, 1, 2, 3, 4, 5, 6], [(0, 1), (0, 2), (2, 3), (1, 3), (3, 4), (4, 5), (4, 6)], 0, [], EmptyOptions)
        self.assertEqual(str(res), "{2, 2} + 1 + {1 + e, 1 + e}")

class UnificationTest(unittest.TestCase):
    def test_loop_insert_2(self):
        t1 = parse_terms("1 + (1)* + 12 + (1)* + 3 + {1 + (1)* + 1, 1} + (1)* + 1 + (1)* + 1 + (1)* + 1 + (1)* + 1 + a + e")
        t2 = parse_terms("1 + (1)* + 11 + (1)* + {1, 1 + (1)* + 1, 1 + (1)* + 1} + 2 + {1 + (1)* + 1, 1} + (1)* + 1 + (1)* + 1 + (1)* + 1 + (1)* + 1 + a + e")
        EmptyOptions.correct_mapping = False
        EmptyOptions.use_structural_change = False
        res = alg.leq_unify(t2, t1, EmptyOptions)
        EmptyOptions.correct_mapping = True
        EmptyOptions.use_structural_change = True
        for r in res:
            pass

    def test_loop_insert(self):
        t1 = parse_terms("{1 + (1)* + 1, 1} + 1 + a + e")
        t2 = parse_terms("{1 + (1)* + 1, 1} + 1 + a + e")
        res = alg.leq_unify(t2, t1, EmptyOptions)
        assert len(res) > 0

    def test_loop_skipping_2(self):
        t1 = parse_terms("4 + {1, 1 + (1)* + 1} + 1 + (1)* + 1 + {24 + a + e, 1 + a + e}")
        t2 = parse_terms("5 + (1)* + 4 + a + e")

        EmptyOptions.correct_mapping = False
        res = alg.leq_unify(t2, t1, EmptyOptions)
        EmptyOptions.correct_mapping = True
        assert len(res) > 0

    def test_loop_skipping(self):
        t1 = parse_terms("1 + {1, 1 + (1)* + 1} + 1 + a + e")
        t2 = parse_terms("3 + a + e")
        EmptyOptions.correct_mapping = False
        res = alg.leq_unify(t2, t1, EmptyOptions)
        EmptyOptions.correct_mapping = True
        assert len(res) > 0

    def test_complex_unification_5(self):
        t1 = parse_terms("3 + {{{{{{{{{{{{{{{{{{{2, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1 } + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + 1, 1} + {6 + a + (1 + a)*, 6 + a + (1 + a)*, 5 + a + (1 + a)*, 5 + a + (1 + a)*, 5 + a + (1 + a)*, 5 + a + e}                        ")
        res = alg.leq_unify(t1, t1, EmptyOptions)
        print res

    def test_complex_unification_4(self):
        t1 = parse_terms("7 + (1)* + 5 + (1)* + 1 + {9 + a + {2 + a + e, 1 + a + e}, 5 + {{2, 1} + 1, 1} + 1 + {{2, 1} + 1, 1} + 1 + a + {2 + a + e, 1 + a + e}, 7 + {{2, 1} + 1 , 1} + 1 + a + {2 + a + e, 1 + a + e}, 9 + {{2, 1} + 1, 1} + 1 + a + {2 + a + e, 1 + a + e}, 13 + a + {2 + a + e, 1 + a + e}, 1 + {3, 3, 3} + 1 + {{2, 1} + 1, 1} + 1 + {{2, 1} + 1, 1} + 1 + a + {2 + a + e, 1 + a + e}}")
        EmptyOptions.use_structural_change = False
        res = alg.leq_unify(t1, t1, EmptyOptions)
        for r in res:
            self.assertTrue(not r.has_structural_additions())
        EmptyOptions.use_structural_change = True

        for unifier in res:
            unifier.unify_single_state

    def test_complex_unification_3(self):
        t1 = Sum([Const(1, [1]), Branch([Sum([Const(1, [4]), Product(Const(1, [5])), Const(1, [6])]), Const(1, [7])]), Const(2, [8, 9]), Accept(), End()]).normalize()
        t2 = Sum([Branch([Sum([Product(Const(1, [4])), Branch([Sum([Const(1, [5]), Branch([Sum([Const(1, [6]), Product(Const(1, [7])), Const(1, [8])]), Const(1, [9])]), Const(2, [10, 11]), Accept(), End()]), Sum([Const(1, [12]), Accept(), End()])])])])]).normalize()
        print t1
        print t2
        EmptyOptions.use_structural_change = False
        res = alg.leq_unify(t1, t2, EmptyOptions)
        EmptyOptions.use_structural_change = True
        print res

    def test_complex_unification_2(self):
        t1 = Sum([Const(2, [1, 2]), Product(Const(1, [7])), Branch([Sum([Const(1, [8]), Product(Const(1, [9])), Const(1, [10])]), Const(1, [11])]), Branch([Sum([Const(1, [12]), Product(Const(1, [13])), Const(1, [14]), Accept(), End()]), Sum([Const(1, [15]), Accept(), End()])])]).normalize()
        print t1
        t2 = Sum([Const(1, [1]), Product(Const(1, [5])), Const(1, [6]), Branch([Sum([Const(1, [9]), Product(Const(1, [10])), Const(1, [11])]), Const(1, [12])]), Branch([Sum([Const(1, [12]), Product(Const(1, [13])), Branch([Sum([Const(1, [14]), Accept(), End()]), Sum([Const(1, [15]), Accept(), End()])])]), Sum([Const(1, [15]), Accept(), End()])])]).normalize()
        print t2
        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertTrue(len(res) == 0)

    def test_complex_unification(self):
        t1 = Sum([Const(5, [1, 2, 3, 4, 5]), Product(Const(1, [6])), Branch([Sum([Const(1, [7]), Product(Const(1, [8]))]), Sum([Const(1, [9]), Accept(), End()])])]).normalize()
        t2 = Sum([Const(5, [101, 102, 103, 104, 105]), Product(Const(1, [106])), Const(1, [107]), Accept(), End()]).normalize()
        print t1
        print t2
        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertEqual(res, [])
        res = alg.leq_unify(t2, t1, EmptyOptions)
        # Need at least one of these to have no structural additions
        no_branches = False
        for u in res:
            if len(u.additions_from_node) == 0:
                no_branches = True
        self.assertTrue(no_branches)

    def test_simple_unifier(self):
        res = alg.leq_unify(Const(1, [(1, 2)]), Const(1, [(2, 3)]), EmptyOptions)[0]
        self.assertEqual(res.from_edges, [(1, 2)])
        self.assertEqual(res.to_edges, [(2, 3)])

    def test_unifier_branches(self):
        t1 = Branch([Const(2, [(1, 2), (2, 3)]), Const(1, [(4, 5)])]).normalize()
        t2 = Const(2, [(-1, -2), (-2, -3)]).normalize()

        res = alg.leq_unify(t2, t1, EmptyOptions)[0]
        self.assertEqual(res.to_edges, [(1, 2), (2, 3)])
        self.assertEqual(res.from_edges, [(-1, -2), (-2, -3)])
        self.assertEqual(res.disabled_edges, [(4, 5)])

    def test_structural_modification(self):
        t1 = Sum([Const(1, [1]), Product(Const(1, [1])), Const(1, [1])])
        t2 = Sum([Const(1, [2]), Product(Const(1, [2])), Const(1, [2]), Accept(), End()])

        self.assertEqual(alg.leq(t1, t2, EmptyOptions), False)

    def test_unifier_both_branches(self):
        t1 = Branch([Sum([Const(1, [(0, 1)]), Accept()]), Sum([Const(2, [(1, 2), (2, 3)]), End()])]).normalize()
        t2 = Branch([Sum([Const(1, [(0, 5)]), End()]), Sum([Const(1, [(0, 1)]), Accept()]), Sum([Const(2, [(2, 3), (3, 4)]), End()])]).normalize()
        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertNotEqual(res, [])

        # print(res.from_edges)
        # print(res.to_edges)

    def test_unifier_sum_selection(self):
        t1 = Sum([Const(1, [(0, 1)]), Branch([Const(1, [(1, 2)]), End()])])
        t2 = Sum([Const(2, [(0, 1), (1, 2)])]).normalize()
        res = alg.leq_unify(t2, t1, EmptyOptions)
        print res
        self.assertNotEqual(res, [])

    def test_unifier_single_to_branch(self):
        t1 = End()
        t2 = Branch([End(), End()])
        res = alg.leq_unify(t2, t1, EmptyOptions)

        self.assertNotEqual(res, [])

    def test_unifier_deep_sum_selection(self):
        t1 = Sum([Const(3, [(1, 2), (2, 3), (3, 4)]), Accept()]).normalize()
        t2 = Sum([Const(1, [(0, 1)]), Branch([End(), Accept(), Const(1, [(1, 2)])]), Const(1, [(2, 3)]), Accept()]).normalize()
        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertNotEqual(res, [])
        # TODO --- Need to consider a case where we have a branch that unifies with more than one term.

    def test_unifier_plus_plus(self):
        t1 = Sum([Const(30, [(0, 1)] * 30)]).normalize()
        t2 = Sum([Const(30, [(0, 1)] * 30)]).normalize()

        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertNotEqual(res, [])

    def test_unifier_end(self):
        t1 = End()
        t2 = Sum([Const(1, [(0, 1)]), Const(1, [(1, 2)])]).normalize()

        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertNotEqual(res, [])

    def test_unifier_sum_sum(self):
        t1 = Sum([Const(1, [1]), Const(1, [2])])
        t2 = Sum([Const(1, [1]), Product(Const(1, [2])), Const(1, [3])])

        res = alg.leq_unify(t2, t1, EmptyOptions)
        res = [x for x in res if x is not None]
        self.assertNotEqual(res, [])

    def test_unifier_sum_product_const(self):
        t1 = Sum([Const(1, [1]), Accept(), End()])
        t2 = Sum([Const(1, [1]), Product(Const(1, [2])), Const(1, [1]), Accept(), End()])

        EmptyOptions.correct_mapping = False
        res = alg.leq_unify(t1, t2, EmptyOptions)
        EmptyOptions.correct_mapping = True
        self.assertNotEqual(res, [])

    def test_unifier_const_to_branch_in_sum(self):
        t1 = Const(1, [1])
        t2 = Sum([Branch([Const(1, [1]), Const(1, [1])])]).normalize()

        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertNotEqual(res, [])

    def test_unifier_sum(self):
        t1 = Sum([ Product(Const(1, [1])), Const(1, [1])])
        t2 = Sum([ Const(1, [2])])

        # Can't do these due to homogeneity --- that is,
        # the product will have the same inputs as the enxt
        # element so will fail unification.
        res = alg.leq_unify(t1, t2, EmptyOptions)
        self.assertEqual(res, [])
        res = alg.leq_unify(t2, t1, EmptyOptions)
        self.assertEqual(res, [])

class TestDeconstruction(unittest.TestCase):
    def test_graph_for_extended_loop(self):
        graph, end_nodes = alg.graph_for(Sum([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])]), {(0, 1): 'a', (1, 2): 'b', (2, 3): 'c'})
        self.assertEqual(end_nodes, [2])
        self.assertEqual(len(graph.edges), 3)
        print graph.edges

    def test_graph_for_const(self):
        graph, end_nodes = alg.graph_for(Const(1, [(0, 1)]), {(0, 1): 'a'})
        self.assertEqual(graph.edges, set([(0, 1)]))
        self.assertEqual(graph.start_state, 0)
        self.assertEqual(end_nodes, set([1]))

    def test_graph_for_sum(self):
        graph, end_nodes = alg.graph_for(Sum([Const(1, [(0, 1)]), Accept(), End()]), {(0, 1): 'a'})
        self.assertEqual(graph.accepting_states, set([1]))

    def test_graph_for_loop(self):
        graph, end_nodes = alg.graph_for(Product(Const(1, [(2, 2)])), {(2, 2): 'a'})
        self.assertEqual(graph.edges, set([(0, 0)]))
        self.assertEqual(end_nodes, [])
        self.assertEqual(graph.nodes, set([0]))

class StructuralTransformations(unittest.TestCase):
    def test_apply_structural_transformations(self):
        graph, _ = alg.graph_for(Sum([Const(1, [(0, 1)]), Const(1, [(1, 2)])]), {(0, 1): 'a', (1, 2): 'b'} )
        slookup = {
                (0, 0): 'a'
                }
        mod = Modification(Product(Const(1, [(0, 0)])), [(1, 2)])
        mod.symbol_lookup = slookup

        additions = [
                Modifications([], [mod])
                ]
        result = alg.apply_structural_transformations_internal(graph, additions, EmptyOptions)
        self.assertTrue((1, 1) in result.edges)
        self.assertEqual(result.symbol_lookup[(1, 1)], 'a')

    def test_apply_branch(self):
        graph, _ = alg.graph_for(Sum([Const(1, [(0, 1)]), Const(1, [(1, 2)]), Const(1, [(2, 3)])]), {(0, 1): 'a', (1, 2): 'b', (2, 3): 'c'} )
        slookup = {
                (0, 1): 'd'
                }
        mod = Modification(Sum([Const(1, [(0, 1)]), Accept(), End()]), [(1, 2)])
        mod.symbol_lookup = slookup
        additions = [
                Modifications([mod], [])
                ]
        result = alg.apply_structural_transformations_internal(graph, additions, EmptyOptions)
        self.assertTrue((1, 5) in result.edges)

class PrefixTest(unittest.TestCase):
    def test_simple(self):
        s1 = {
                (0, 1): [65],
                (1, 2): [66],
                (2, 3): [67],
                (3, 4): [68]
        }
        t1 = Sum([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(3, 4)])])
        t2 = Sum([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])

        prefix, alg_a, alg_b = alg.prefix_merge(t1, s1, t2, s1, EmptyOptions)
        self.assertEqual(str(prefix), "1 + (1)*")
        self.assertEqual(str(alg_a), "1")
        self.assertEqual(str(alg_b), "1")

    def test_simple_unify(self):
        s1 = {
                (0, 1): [65],
                (1, 2): [66],
                (2, 3): [67],
                (3, 4): [68]
        }
        t1 = Sum([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(3, 4)])])
        t2 = Sum([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])

        prefix, alg_a, alg_b, unifier = alg.prefix_unify(t1, s1, t2, s1, EmptyOptions)
        self.assertEqual(alg_a, None)
        self.assertEqual(alg_b, None)
        self.assertNotEqual(unifier, None)

    def test_branch_prefix_merge(self):
        s1 = {
                (0, 1): [65],
                (1, 2): [66],
                (2, 3): [67],
                (3, 4): [68]
        }
        t1 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])
        t2 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])

        prefix, alg_a, alg_b = alg.prefix_merge(t1, s1, t2, s1, EmptyOptions)
        self.assertEqual(alg_a, None)

    def test_branch_prefix_merge_unify(self):
        s1 = {
                (0, 1): [65],
                (1, 2): [66],
                (2, 3): [67],
                (3, 4): [68]
        }
        t1 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])
        t2 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])

        prefix, alg_a, alg_b, unifier = alg.prefix_unify(t1, s1, t2, s1, EmptyOptions)
        self.assertNotEqual(unifier, None)

    def test_prefix_branches(self):
        s1 = {
                (0, 1): [65],
                (1, 2): [66],
                (2, 3): [67],
                (3, 4): [68],
                (4, 5): [69]
        }
        t1 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(1, [(2, 3)])])
        t2 = Branch([Const(1, [(0, 1)]), Product(Const(1, [(1, 2)])), Const(3, [(2, 3), (3, 4), (4, 5)])])

        print alg.prefix_unify(t1, s1, t2, s1, EmptyOptions)

class AcceptRateTest(unittest.TestCase):
    def test_ar(self):
        slookup = {0: [0]*256, 1:[1,2,3,4,5], 2: [1], 3: [8,3,5,1,2,3,1,4,1,2,3,1,2]}


        t = Sum([Const(2, [0, 1]), Accept(), End()]).normalize()
        t2 = Sum([Const(2, [0, 1]), Branch([Const(1, [2]), Const(1, [3])]), Accept()]).normalize()

        self.assertTrue(alg.acceptance_rate(t, slookup) < 0.03)
        self.assertTrue(alg.acceptance_rate(t2, slookup) < 0.002)

class LEQMergeTest(unittest.TestCase):
    def test_branch(self):
        t1 = Branch([Const(1, [(0, 1)]), Const(1, [(0, 1)])])
        t2 = Branch([Const(1, [(0, 1)])])

        u = alg.leq_merge(t1, t2, EmptyOptions)
        self.assertEqual(u.structural_modification_count(), 1)
        u2 = alg.leq_merge(t2, t1, EmptyOptions)
        self.assertEqual(u2.structural_modification_count(), 0)

    def test_sums_simpler(self):
        t1 = Sum([Const(2, [(0, 1), (1, 2)])]).normalize()
        t2 = Sum([Const(2, [(10, 11), (11, 12)])]).normalize()
        u = alg.leq_merge(t1, t2, EmptyOptions)
        self.assertEqual(u.structural_modification_count(), 0)
        self.assertEqual(u.get_edge_mapping()[(0, 1)], (10, 11))

    def test_arm_to_branch(self):
        t1 = Sum([Const(2, [(0, 1), (1, 2)])]).normalize()
        t2 = Branch([Const(1, [(10, 11)]), Const(2, [(10, 13), (13, 11)])]).normalize()

        u = alg.leq_merge(t1, t2, EmptyOptions)
        print u.get_edge_mapping()
        self.assertEqual(u.structural_modification_count(), 0)
        self.assertEqual(u.get_edge_mapping()[(0, 1)], (10, 13))

    def test_simple_sums_2(self):
        t1 = Sum([Const(1, [(0, 1)]), Const(1, [(1, 2)])])
        t2 = Sum([Const(1, [(10, 11)]), Branch([Const(1, [(11, 12)]), Const(1, [(11, 12)])])])
        u = alg.leq_merge(t1, t2, EmptyOptions)
        self.assertEqual(u.structural_modification_count(), 0)
        self.assertEqual(u.get_edge_mapping()[(0, 1)], (10, 11))

    def test_simple_sums(self):
        t1 = Sum([Const(1, [(0, 1)]), Const(1, [(1, 2)]), Const(1, [(2, 3)]), Accept(), End()])
        # 1 + {1, 2} + 1 + a + e
        t2 = Sum([Const(1, [(10, 11)]), Branch([Const(1, [(11, 12)]), Sum([Const(1, [(11, 13)]), Const(1, [(13, 12)])])]), Const(1, [(12, 15)]), Accept(), End()])
        u = alg.leq_merge(t1, t2, EmptyOptions)
        self.assertEqual(u.structural_modification_count(), 0)
        self.assertEqual(u.get_edge_mapping()[(2, 3)], (12, 15))
        self.assertEqual(u.get_edge_mapping()[(1, 2)], (11, 12))

if __name__ == "__main__":
    unittest.main()
