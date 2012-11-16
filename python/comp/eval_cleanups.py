#!/usr/bin/env python
# -*- coding: utf-8 -*- 

import sys
import argparse

import pandas as pd
from pandas.core.reshape import melt
from scipy.stats import spearmanr, kendalltau

from standard_cleanup import aggregate_ratings
from standard_cleanup import remove_deviant_ratings, remove_deviant_subjects
from elo import elo
from rebin import rebin
from whiten import whiten


HEAD_FILE = '/Users/stephen/Working/imsgrounded/data/comp/comp_ratings_head.csv'
MOD_FILE = '/Users/stephen/Working/imsgrounded/data/comp/comp_ratings_const.csv'
WHOLE_FILE = '/Users/stephen/Working/imsgrounded/data/comp/amt_reshaped.csv'
ASSOC_FILE = '/Users/stephen/Working/imsgrounded/results/big_assoc_similarties.csv'

# COMBINE_METHODS = ['sum', 'prod', 'hmean']
COMBINE_METHODS = ['prod']
# ASSOC_METHODS = ['jaccard', 'cosine']
ASSOC_METHODS = ['jaccard']


# Things we need to output:
# - Correlations with wholes, from perspective of just heads and just mods
# - Correlation with wholes, from perspective of sum/prod of heads and mods together
# - ditto for Association measures
# - results of varying the filter parameters
# - do the same cleanups for the wholes?

class Cleaner(object):
    def scores(self, df):
        raise NotImplementedError('Base class.')

    def paramaters(self):
        return {}

    def __str__(self):
        return "Base class"


class BaselineCleaner(Cleaner):
    def scores(self, df):
        return df

    def parameters(self):
        return {}

    def __str__(self):
        return "Do nothing"

class RemoveDeviantSubjectCleaner(Cleaner):
    def __init__(self, min_rho):
        self.min_rho = min_rho

    def scores(self, df):
        return remove_deviant_subjects(df, self.min_rho)

    def parameters(self):
        return {'min_rho': self.min_rho}

    def __str__(self):
        return "Remove Subj (rho < %f)" % self.min_rho

class RemoveDeviantRatings(Cleaner):
    def __init__(self, zscore):
        self.zscore = zscore

    def parameters(self):
        return {'zscore': self.zscore}

    def scores(self, df):
        return remove_deviant_ratings(df, self.zscore)

    def __str__(self):
        return "Remove Judgements (z < %f)" % self.zscore

class EloRatings(Cleaner):
    def __init__(self, k=32, start=1500, spread=400):
        self.k = k
        self.start = start
        self.spread = spread

    def parameters(self):
        return dict(elo_k=self.k)

    def scores(self, df):
        return elo(df, self.k, self.start, self.spread)

    def __str__(self):
        return "Elo (k=%d, start=%f, spread=%f)" % (self.k, self.start, self.spread)

class RebinCleaner(Cleaner):
    def __init__(self, new_bins):
        if isinstance(new_bins, dict):
            self.bin_names = "".join(str(new_bins[k]) for k in sorted(new_bins.keys()))
            self.bin_mapping = new_bins
        elif isinstance(new_bins, (list, tuple)):
            self.bin_names = "".join(map(str, new_bins))
            self.bin_mapping = dict(zip(range(1, len(new_bins) + 1), new_bins))
        elif isinstance(new_bins, str):
            self.__init__(map(int, new_bins))
        else:
            raise ValueError("Inappropriate bin value.")

    def parameters(self):
        return dict(bins=self.bin_names)

    def scores(self, df):
        return rebin(df, self.bin_mapping)

    def __str__(self):
        return "Rebin (%s)" % self.bin_names


class SvdCleaner(Cleaner):
    def __init__(self, k):
        self.k = k

    def parameters(self):
        return dict(svd_k=self.k)

    def scores(self, df):
        return whiten(df, self.k)

    def __str__(self):
        return "SVD (Rank %d)" % self.k

class FillCleaner(Cleaner):
    def __init__(self, fill_value):
        self.fill_value = fill_value

    def scores(self, df):
        return df.fillna(self.fill_value)

    def parameters(self):
        return dict(fill_value=self.fill_value)

    def __str__(self):
        return "Fill w %d" % self.fill_value

def decrange(start, stop, inc):
    out = []
    x = start
    while x <= stop:
        out.append(x)
        x += inc
    return out

def combine_measures(agg_heads_and_mods, method='prod'):
    # returns a new DataFrame that's the exact same format as the whole file
    # method should be either 'sum' or 'prod'.
    grouped = agg_heads_and_mods.groupby('compound')
    if method == 'sum':
        together = grouped.sum()
    elif method == 'prod':
        together = grouped.prod()
    elif method == 'hmean':
        together = 2 * grouped.prod() / grouped.sum()
    else:
        raise ValueError("Invalid method for combining measures.")
    together['compound'] = together.index
    return together

# def rho_with_wholes(indiv, whole):
#     assert (indiv['compound'] == whole['compound']).all()
# 
#     rho, p = spearmanr(indiv['mean'], whole['mean'])
#     # rho, p = kendalltau(indiv['mean'], whole['mean'])
#     # hardcode statistical significance
#     if not p < .05:
#         #import pdb
#         #pdb.set_trace()
#         sys.stderr.write("Uh oh, got a p < .05 (%f)\n" % p)
#     return rho, p
# 
# def rho_with_assoc(indiv, assoc, measure):
#     assert (indiv['compound'] == assoc['compound']).all()
#     assert (indiv['const'] == assoc['const']).all()
#     assert measure in ('jaccard', 'cosine')
#     # return kendalltau(indiv['mean'], assoc[measure])
#     return spearmanr(indiv['mean'], assoc[measure])
# 
# 
# 


heads = pd.read_csv(HEAD_FILE)
mods = pd.read_csv(MOD_FILE)
whole = pd.read_csv(WHOLE_FILE)
assoc = pd.read_csv(ASSOC_FILE)

# make sure we drop the association measures between a compound
# and itself. they're always 1.
assoc = assoc[assoc.compound != assoc.const]

# we can only work with the intersection of all 3 files in terms of
# judgements
good_compounds = reduce(
    set.intersection,
    [set(x.compound) for x in [heads, mods, whole, assoc]]
)
heads, mods, whole, assoc = [
    d[d.compound.map(good_compounds.__contains__)]
    for d in [heads, mods, whole, assoc]
]


# go ahead and sort the whole judgements and assoc measures
whole_orig = whole.sort('compound')
whole = aggregate_ratings(whole_orig)
assoc = assoc.sort(['compound', 'const'])
concatted = pd.concat([heads, mods], ignore_index=True)


setups = []
setups += [BaselineCleaner()]
setups += [RemoveDeviantSubjectCleaner(r) for r in decrange(0.20, 0.6, 0.05)]
setups += [RemoveDeviantRatings(z) for z in decrange(1.0, 4.0, 0.5)]
#setups += [EloRatings(k, 1500, 400) for k in [.001, .05, .1, 1, 5, 10, 30]]
setups += [RebinCleaner(b) for b in ["1144477","1444447","1114777","1122233","1222223","1112333"]]
setups += [SvdCleaner(k) for k in range(1, 31)]
setups += [FillCleaner(0), FillCleaner(1), FillCleaner(7)]

results = []
parameters = set()

CONCAT_BEFORE = True

for cleaner in setups:
    sys.stderr.write("Evaluating model: %s\n" % cleaner)
    if CONCAT_BEFORE:
        concat_cleaned = cleaner.scores(concatted)
    else:
        concat_cleaned = pd.concat([cleaner.scores(heads), cleaner.scores(mods)], ignore_index=True)
    agg = aggregate_ratings(concat_cleaned).sort(['compound', 'const'])
    sys.stderr.write("Finished cleaning head/const ratings. (%s)\n" % cleaner)
    whole_clean = aggregate_ratings(cleaner.scores(whole_orig)).sort('compound')
    sys.stderr.write("Finished cleaning whole ratings. (%s)\n" % cleaner)
    row_rho = cleaner.parameters()
    row_rho['metric'] = 'rho'
    row_tau = cleaner.parameters()
    row_tau['metric'] = 'tau'
    parameters.update(row_rho.keys())

    together = combine_measures(agg, 'prod').sort('compound')
    rho, p1 = spearmanr(together['mean'], whole['mean'])
    tau, p2 = kendalltau(together['mean'], whole['mean'])
    row_rho['whole'] = rho
    row_tau['whole'] = tau

    # and now when we clean up whole measures
    rho, p1 = spearmanr(together['mean'], whole_clean['mean'])
    tau, p2 = kendalltau(together['mean'], whole_clean['mean'])
    row_rho['whole cleaned'] = rho
    row_tau['whole cleaned'] = tau

    rho, p1 = spearmanr(agg['mean'], assoc['jaccard'])
    tau, p2 = kendalltau(agg['mean'], assoc['jaccard'])
    row_rho['association sim'] = rho
    row_tau['association sim'] = tau

    results.append(row_rho)
    results.append(row_tau)

results = pd.DataFrame(results)
output = melt(results, id_vars=parameters)
output.to_csv(sys.stdout, index=False)

# produce plots
from rplots import line_plot
import operator
parameters.remove('metric')
for p in parameters:
    other_params = parameters - set([p])
    if other_params:
        experiment = reduce(operator.and_, [output[op].isnull() for op in other_params])
        experiment = output[experiment]
    else:
        experiment = output
    line_plot("graphs/" + p + ".pdf", experiment, p, 'value', 'variable',
            ylab='Resulting Correlation',
            linetype='metric', linename="Metric", colorname="Eval Method")



