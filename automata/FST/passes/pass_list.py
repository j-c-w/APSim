import compute_algebras
import prefix_split
import splitter
import print_algebras
import sort_by_size

# These passes should work every time inputs are passed to them.
# This module contains a static list of such passes that can be run
# over various IRs

# Automata Wrapper

# GraphIR.
ComputeAlgebras = compute_algebras.ComputeAlgebraPass()
PrintAlgebras = print_algebras.PrintAlgebraPass()

PrefixSplit = prefix_split.PrefixSplitPass()
Splitter = splitter.SplitterPass()

SortBySize = sort_by_size.SortBySizePass()
