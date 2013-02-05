#!/usr/bin/env python
import pandas as pd
import numpy as np
import sys
from util import *

f = openfile(sys.argv[1])
f.next()
data = {}

cols = set()
tars = set()
for line in f:
    t, c, v = line.strip().split("\t")
    t = remove_pos(t)
    if t not in data:
        data[t] = {}
    assert c not in data[t]
    data[t][c] = v
    cols.add(c)
    tars.add(t)

cols = sorted(cols)
tars = sorted(tars)

for t in tars:
    as_str = " ".join(data[t].get(c, "0") for c in cols)
    print "%s\t%s" % (t, as_str)




