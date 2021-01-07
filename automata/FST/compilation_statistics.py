# This is a module with some stats.
algebras_compiled = 0

# Unifier
ssu_complete_mapping_failed = 0
ssu_correct_mapping_failed = 0
ssu_additions_failed = 0
ssu_disable_edges_failed = 0
ssu_disable_symbols_failed = 0
ssu_success = 0
ssu_addition_correctness_fail = 0
ssu_addition_completeness_fail = 0
ssu_heuristic_fail = 0
ssu_structural_addition_homogeneity_fail = 0

unifier_trimming_events = 0
unifiers_returned = 0

unification_successes = 0

exact_same_compilations = 0

# Caches
compilation_helper_additions = 0

# LEQ
executed_comparisons = 0
cutoff_comparisons = 0

# LEQ failure reasons:
recursion_depth_exceeded = 0
single_arm_to_branch_not_found = 0
branch_to_single_arm_not_possible = 0
const_to_non_const = 0
product_to_product_failed = 0
sum_failure = 0
branch_to_branch_failure = 0
types_differ = 0
accept_to_non_accept = 0
const_to_sum_failed = 0
sum_to_const_failed = 0

# LEQ-related algorithms failure reasons:
no_branch_over_node_mmodifiers = 0

# Size limit counters
graph_too_big = 0
failed_algebra_computations = 0

# Splitting
splits_made = 0

# Addition of new automata to existing accelerators
tail_accelerator_not_none = 0
tail_accelerator_found = 0
