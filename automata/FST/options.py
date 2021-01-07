import os
import algebra
import unifier
import terms
import group_compiler

# This file is a total mess -- ideally we'd have all the flags
# defined by the appropriate passes.

class Options(object):
    def __init__(self):
        self.ouptut_folder = 'rxpsc_out'
        self.tail_approximation = False
        self.disabled_edges_approximation = False
        self.print_algebras = False
        self.profile = False
        self.print_compile_time = False
        self.correct_mapping = True
        self.verify = None
        self.no_groups = False
        self.use_cross_compilation = True
        self.use_prefix_merging = False
        self.use_prefix_splitting = False
        self.use_prefix_estimation = False
        self.use_prefix_unification = True
        self.use_splitter = False
        self.prefix_merging_only = False

        self.leq_iterations_file = None
        self.leq_calls_threshold = 100000
        self.leq_call_depth_threshold = 2000
        self.prefix_size_threshold = 5
        self.prefix_acceptance_rate_threshold = 0.10
        self.no_leq_heuristics = True
        self.use_unification_heuristics = True
        self.use_inline_unification_heuristics = True

        self.split_size_threshold = 10
        self.split_threshold_frequency = 5
        self.print_split_stats = False

        self.group_size_distribution = None
        self.print_file_info = False
        self.print_unification_statistics = False
        self.dump_nodes_and_edges = None
        self.dump_failing_nodes_and_edges = None
        self.print_successful_conversions = False
        self.print_regex_injection_stats = False
        self.compression_stats = False

        self.use_size_limits = True
        self.graph_size_threshold = 2000
        self.cross_compilation_threading = 0
        self.algebra_size_threshold = 2000
        self.max_branching_factor = 150

        self.size_difference_cutoff_factor = 5.0
        self.memory_debug = False
        self.time = False
        self.size_limit = None
        self.target = 'single-state'
        self.backend = 'python'
        self.skip_on_fail = True
        self.line_profile = False

        self.use_structural_change = True

        self.comparison_cache = None
        self.dump_comparison_cache = None
        self.use_algebra_cache = True
        self.compile_ony = False
        self.print_leq_failure_reasons = False
        self.print_unification_failure_reasons = False

def create_from_args(args):
    algebra.LEQ_DEBUG = args.debug_leq
    algebra.ALG_DEBUG = args.debug_alg
    algebra.CACHE_ENABLED = not args.no_cache
    algebra.DEBUG_PREFIX_MERGE = args.debug_prefix_merge
    terms.TERMS_DEBUG = args.debug_terms
    unifier.DEBUG_UNIFICATION = args.debug_unification
    unifier.MAX_UNIFIERS = args.max_unifiers
    unifier.PRINT_UNIFICATION_FAILURE_REASONS = args.print_unification_failure_reasons
    group_compiler.DEBUG_COMPUTE_COMPAT_MATRIX = args.debug_compute_compat_matrix
    group_compiler.DEBUG_GENERATE_BASE = args.debug_generate_base
    group_compiler.MODIFICATION_LIMIT = args.modification_limit
    group_compiler.DEBUG_COMPILE_TO_EXISTING = args.debug_compile_to_existing
    group_compiler.DEBUG_REMOVE_PREFIXES = args.debug_remove_prefixes

    opts = Options()
    opts.output_folder = args.output_folder
    opts.tail_approximation = args.tail_approximation
    opts.disabled_edges_approximation = args.disabled_edges_approximation
    opts.correct_mapping = not args.allow_overapproximation
    opts.verify = args.verify
    opts.no_groups = args.no_groups
    opts.print_algebras = args.print_derived
    opts.profile = args.profile
    opts.leq_iterations_file = args.leq_iterations_file
    opts.leq_calls_threshold = args.leq_calls_threshold
    opts.use_structural_change = not args.no_structural_change
    opts.use_unification_heuristics = not args.no_unification_heuristics
    opts.use_prefix_merging = args.use_prefix_merging
    opts.use_prefix_splitting = args.use_prefix_splitting
    opts.use_prefix_estimation = args.use_prefix_estimation
    opts.use_prefix_unification = not args.no_prefix_unification
    opts.prefix_merging_only = args.prefix_merging_only
    opts.use_cross_compilation = args.cross_compile
    opts.use_inline_unification_heuristics = not args.no_inline_unification_heuristics
    opts.use_splitter = args.use_splitter

    opts.group_size_distribution = args.group_size_distribution
    opts.print_file_info = args.print_file_info
    opts.prefix_size_threshold = args.prefix_size_threshold
    opts.prefix_acceptance_rate_threshold = args.prefix_acceptance_rate_threshold
    opts.print_unification_statistics = args.print_unification_statistics
    opts.dump_nodes_and_edges = args.dump_nodes_and_edges
    opts.dump_failing_nodes_and_edges = args.dump_failing_nodes_and_edges
    opts.print_successful_conversions = args.print_successful_conversions
    opts.compression_stats = args.compression_stats
    opts.print_regex_injection_stats = args.print_regex_injection_stats
    opts.use_size_limits = not args.no_size_limits

    opts.split_size_threshold = args.split_size_threshold
    opts.split_threshold_frequency = args.split_threshold_frequency
    opts.print_split_stats = args.print_split_stats

    opts.graph_size_threshold = args.graph_size_threshold
    opts.cross_compilation_threading = args.cross_compilation_threading
    opts.size_difference_cutoff_factor = args.size_difference_cutoff
    opts.no_leq_heuristics = args.no_leq_heuristics
    opts.memory_debug = args.memory_debug
    opts.time = args.time
    opts.algebra_size_threshold = args.algebra_size_threshold
    opts.target = args.target
    opts.backend = args.backend
    opts.print_compile_time = args.print_compile_time
    opts.skip_on_fail = not args.no_skip_on_fail

    opts.comparison_cache = args.comparison_cache
    opts.dump_comparison_cache = args.dump_comparison_cache
    opts.use_algebra_cache = not args.no_algebra_cache
    opts.compile_only = args.compile_only
    opts.print_leq_failure_reasons = args.print_leq_failure_reasons
    opts.line_profile = args.line_profile

    if opts.dump_nodes_and_edges:
        # Clear the file:
        if os.path.exists(opts.dump_nodes_and_edges):
            os.remove(opts.dump_nodes_and_edges)
    return opts

def add_to_parser(parser):
    parser.add_argument('--output-folder', default='rxpsc_output', dest='output_folder', help='Use this folder to output any generated files (e.g. simulators)')
    parser.add_argument('--tail-approximation', default=False, dest='tail_approximation', action='store_true', help='Use the Tail Cutoff approximation in conversions.')
    parser.add_argument('--allow-overapproximation', default=False, dest='allow_overapproximation', action='store_true', help='Allow overapproximation of automata when compiling (completeness but not correctness)')
    parser.add_argument('--no-groups', default=False, dest='no_groups', action='store_true', help='Don\'t use the input groups --- assume every regex can compile to every other regex.')
    parser.add_argument('--disabled-edges-approximation', default=False, dest='disabled_edges_approximation', action='store_true', help='Do not require edges to be disabled.')
    parser.add_argument('--print-algebras', default=False, dest='print_derived',
            help='Print Derived Algebras', action='store_true')
    parser.add_argument('--profile', action='store_true', default=False, dest='profile', help='Run the profiler')
    parser.add_argument('--leq-iterations-file', default=None, dest='leq_iterations_file', help='Dump file for the number of iterations of the LEQ operation')
    parser.add_argument('--leq-calls-threshold', default=100000, dest='leq_calls_threshold', help='Number of recursive calls to make before giving up in the LEQ computation')
    parser.add_argument('--leq-call-depth-threshold', default=2000, dest='leq_call_depth_threshold', help='Max permissible recursion depth when comparing algebras')
    parser.add_argument('--print-file-info', default=False, dest='print_file_info', help='Print the file information', action='store_true')
    parser.add_argument('--no-structural-change', default=False, dest='no_structural_change', help="Don't use structural change.", action='store_true')

    parser.add_argument('--group-size-distribution', default=None, dest='group_size_distribution', help='Dump the group size distribution to this file')
    parser.add_argument('--dump-nodes-and-edges', default=None, dest='dump_nodes_and_edges', help='Dump nodes and edges for each CC into a file')
    parser.add_argument('--dump-failing-nodes-and-edges', default=None, dest='dump_failing_nodes_and_edges', help='Dump nodes and edges for each CC that fails conversion into a graph into a file.')
    parser.add_argument('--graph-size-threshold', default=2000, dest='graph_size_threshold', help="Exclude graphs larger than this value (deal with python recursion limit)")
    parser.add_argument('--max-branching-factor', default=150, dest='max_branching_factor', type=int, help='Maximum branching factor for graphs before omitting.')
    parser.add_argument('--algebra-size-threshold', default=2000, dest='algebra_size_threshold', type=int)
    parser.add_argument('--cross-compilation-threading', default=0,dest='cross_compilation_threading', help='How many threads should be used for genreating comparisons. 0 disables the thread pool entirely.', type=int)
    parser.add_argument('--size-difference-cutoff-factor', default=5.0, dest='size_difference_cutoff', help='If algebra X is this many times larger than algebra Y, then assume that X </= Y, 0 disables', type=float)
    parser.add_argument('--no-leq-heuristics', default=False, dest='no_leq_heuristics', action='store_true', help='Use heuristics to skip some of the comparisons that seem likely to fail anyway')
    parser.add_argument('--modification-limit', default=10, dest='modification_limit', type=int, help='Limit the number of modifications to each accelerator')
    parser.add_argument('--no-unification-heuristics', default=False, dest='no_unification_heuristics', action='store_true', help='Use heuristcs to help skip unifications likely to fail anyway.')
    parser.add_argument('--no-inline-unification-heuristics', default=False, dest='no_inline_unification_heuristics', action='store_true', help='Use no inline heuristics')
    parser.add_argument('--compile-only', default=False, dest='compile_only', action='store_true', help="Don't  run any cross-compilation commands, just compile the algebras")
    parser.add_argument('--max-unifiers', default=20, dest='max_unifiers', type=int, help='Maximum number of unifiers to consider for any particular pair of equations')
    
    # Debug flags.
    parser.add_argument('--debug-leq', default=False, dest='debug_leq', action='store_true')
    parser.add_argument('--debug-terms', default=False, dest='debug_terms', action='store_true', help='Print all information about terms when printing')
    parser.add_argument('--no-skip-on-fail', default=False, dest='no_skip_on_fail', action='store_true', help="Normally, we skip the algebra if a tool fails.  With this flag, we do not skip")
    parser.add_argument('--debug-alg', default=False, dest='debug_alg', action='store_true')
    parser.add_argument('--debug-unification', default=False, dest='debug_unification', action='store_true')
    parser.add_argument('--debug-compute-compat-matrix', default=False, dest='debug_compute_compat_matrix', action='store_true')
    parser.add_argument('--debug-generate-base', default=False, dest='debug_generate_base', action='store_true')
    parser.add_argument('--debug-prefix-merge', default=False, dest='debug_prefix_merge', action='store_true')
    parser.add_argument('--memory-debug', default=False, dest='memory_debug', action='store_true')
    parser.add_argument('--print-compile-time', action='store_true', dest='print_compile_time', default=False)
    parser.add_argument('--debug-compile-to-existing', action='store_true', dest='debug_compile_to_existing', default=False)
    parser.add_argument('--debug-remove-prefixes', action='store_true', dest='debug_remove_prefixes', default=False)
    parser.add_argument('--print-unification-statistics', action='store_true', dest='print_unification_statistics', default=False)
    parser.add_argument('--print-leq-failure-reasons', default=False, dest='print_leq_failure_reasons', action='store_true', help='Print counters indicating why various equations failed the LEQ phase')
    parser.add_argument('--print-unification-failure-reasons', default=False, dest='print_unification_failure_reasons', action='store_true', help='Print reasons that unifiers fail within the single state unification method.')
    parser.add_argument('--compression-stats', default=False, dest='compression_stats', action='store_true')
    parser.add_argument('--print-regex-injection-stats', default=False,
            dest='print_regex_injection_stats', action='store_true', help='Print statistics for the fraction of regular expressions from \
            the set that could be run using other regular \
            expressions in different groups.')
    parser.add_argument('--print-successful-conversions', default=False, dest='print_successful_conversions', action='store_true', help='Print successful conversions between algebras.')
    parser.add_argument('--line-profile', default=False, dest='line_profile', action='store_true', help='Profile the LEQ structure.')
    parser.add_argument('--time', default=False, dest='time', action='store_true', help='Print the compilation time')
    parser.add_argument('--verify', default=False, dest='verify', help='Do a verification --- the inputs are line-by-line in the file that is provided as argument.')
    parser.add_argument('--no-algebra-generation-cache', default=False, dest='no_cache', action='store_true', help='Disable the computation caches --- this makes things /much/ shlower.')
    parser.add_argument('--no-algebra-cache', default=False, dest='no_algebra_cache', action='store_true', help='Do not cache algebra generation results from particular graphs.  Will speed up computation if using methods only relying a single algebra computation per graph.')
    parser.add_argument('--no-size-limits', default=False, dest='no_size_limits', help="Disable all size limits on input graphs (Not recommended!)")
    parser.add_argument('--use-prefix-merging', default=False, dest='use_prefix_merging', help="Use prefix merging (experimental only)", action='store_true')
    parser.add_argument('--use-splitter', default=False, dest='use_splitter', help='Use automata splitting to make automata more structurally compatible.', action='store_true')
    parser.add_argument('--print-split-stats', default=False, dest='print_split_stats', action='store_true')
    parser.add_argument('--split-size-threshold', default=10, dest='split_size_threshold', type=int)
    parser.add_argument('--no-prefix-unification', default=False, dest='no_prefix_unification', help="Don't use prefix unification, and use traditional unification instead (means you don't use translation resources for a particular state)", action='store_true')
    parser.add_argument('--prefix-merging-only', default=False, dest='prefix_merging_only', help="Use prefix merging only (prefix_merging)", action='store_true')
    parser.add_argument('--use-prefix-splitting', default=False, dest='use_prefix_splitting', help="Use prefix splitting to split automata being translated (makes external techniques such as input-stream translation more effective)", action='store_true')
    parser.add_argument('--split-threshold-frequency', default=False, dest='split_threshold_frequency', help="How many occurances we require of a particular pattern to perform a split", type=int)
    parser.add_argument('--use-prefix-estimation', default=False, dest='use_prefix_estimation', help="Use prefix estimation to allow overapproximation of automata.", action='store_true')
    parser.add_argument('--cross-compile', default=False, dest='cross_compile', help='Use cross compilation to compress regexes', action='store_true')
    parser.add_argument('--prefix-size-threshold', default=5, dest='prefix_size_threshold', help='Smallest size of prefix to use.', type=int)
    parser.add_argument('--prefix-acceptance-rate-threshold', default=0.10, dest='prefix_acceptance_rate_threshold', type=float, help='What fraction of (random) strings should prefixes be allowed to accept?')

    # Target flags
    parser.add_argument('--target', choices=['single-state', 'symbol-only-reconfiguration', 'perfect-unification'], default='single-state')
    parser.add_argument('--backend', choices=['python', 'none'], default='none')

    # Intermediate output flags
    parser.add_argument('--dump-comparison-cache', default=None, dest='dump_comparison_cache', help='Dump a conversion map in a file --- this can be used to speedup subsequent runs by caching comparison results.')
    parser.add_argument('--comparison-cache', default=None, dest='comparison_cache', help='Takes as input a comparison cache file (as generated by the --dump-comparison-cache flag).  This makes the unifier generation /much/ faster when repeatedly running over the same file')

EmptyOptions = Options()
