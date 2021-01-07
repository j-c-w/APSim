import rxp_pass

class SortBySizePass(rxp_pass.Pass):
    def __init__(self):
        super(SortBySizePass, self).__init__("SortBySizePass")

    # Sort within each group by size of the algebras,
    # biggest to smallest.
    def execute(self, groups, options):
        for i in range(len(groups)):
            groups[i] = sorted(groups[i], key=lambda x: x.algebra.size(), reverse=True)
        return groups
