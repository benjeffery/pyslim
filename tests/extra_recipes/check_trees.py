#!/usr/bin/env python3
import sys

import tskit

treefile = sys.argv[1]

ts = tskit.load(treefile)
message = (
    f"The file '{treefile}' has {ts.num_trees} trees relating "
    f"{ts.num_individuals} individuals with {ts.num_mutations} mutations at "
    f"{ts.num_sites} sites."
)
print(message)
