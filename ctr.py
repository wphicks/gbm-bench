from __future__ import print_function

import os
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from conversion import *
from metrics import *
from utils import *

import glob

def load_npy_files(globpath):
    files = glob.glob(globpath)

    # cheap way to shuffle the data a bit
    np.random.shuffle(files)
    # files.sort()
    # show the first 10 files...
    print("First 10 files...")
    print(files[0:10])
    # print the total number of files...
    print("Imported {} files.".format(len(files)))

    # faster way of loading/concatenating files...
    ndarr_list = []
    for f in files:
        ndarr = np.load(f)
        ndarr_list.append(ndarr)
    ndarrs = np.concatenate(ndarr_list)

    # slower way of loading/concatenating files...
    # ndarrs = np.load(files[0])
    # for f in files[1:]:
    #     ndarrs = np.append(ndarrs, np.load(f), axis=0)

    # double-check the shape...
    print("Shape of imported ndarray: {}".format(ndarrs.shape))

    # double-check first row of data...
    print("First row of data...")
    print(ndarrs[0])

    return ndarrs

def prepareImplCommon(dbFolder, testSize, shuffle, dbSubFolder, numRows):
    start = time.time()
    s = time.time()
    print("Loading npy files...")
    data = load_npy_files(os.path.join(dbFolder, dbSubFolder, "day_[0-1]/*.npy"))
    # data = load_npy_files(os.path.join(dbFolder, dbSubFolder, "day_0/*.npy"))

    X = data[:, 1:]
    y = data[:, 0]
    del data

    # reset the numRows
    # print("Resetting numRows to the maximum length (ignoring input).")
    # numRows = len(y)

    print("Dataset has " + str(len(X[0])) + " input features.")
    print("Dataset has " + str(len(X)) + " rows.")

    idx = np.random.choice(np.arange(len(y)), numRows, replace=False)
    X = X[idx]
    y = y[idx]
    print("Done loading npy files. %.2fs" % (time.time() - s))
    
    s = time.time()
    print("Generating train/test split...")
    # X_train, X_test, y_train, y_test = train_test_split(X, y, stratify=y, shuffle=shuffle, random_state=42, test_size=testSize)
    X_train, X_test, y_train, y_test = train_test_split(X, y, stratify=None, shuffle=False, random_state=42, test_size=testSize)
    print("Done generating train/test split. %.2fs" % (time.time() - s))
    del X, y
    load_time = time.time() - start
    print("Criteo CTR dataset loaded in %.2fs" % load_time, file=sys.stderr)
    return Data(X_train, X_test, y_train, y_test)

def prepareImpl(dbFolder, testSize, shuffle, nrows):
    rows = 2e7 if nrows is None else nrows
    return prepareImplCommon(dbFolder, testSize, shuffle, "etled", rows)

def prepare(dbFolder, nrows):
    return prepareImpl(dbFolder, 0.01, True, nrows)


def metrics(y_test, y_prob):
    return classification_metrics_binary_prob(y_test, y_prob)

def catMetrics(y_test, y_prob):
    pred = np.argmax(y_prob, axis=1)
    return classification_metrics_binary_prob(y_test, pred)


nthreads = get_number_processors()
nTrees = 200

xgb_common_params = {
    "eta":              0.2,
    "gamma":            0.4,
    # "learning_rate":    0.1,
    "max_depth":        7,
    # "max_leaves":       2**8,
    "min_child_weight": 20,
    "num_round":        nTrees,
    # "reg_lambda":       1,
    # "scale_pos_weight": 2,
    "subsample":        1,
    "lambda":           100,
    "eval_metric":      "logloss",
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "alpha":            3,
}

lgb_common_params = {
    "learning_rate":    0.1,
    "min_child_weight": 30,
    "min_split_gain":   0.1,
    "num_leaves":       2**8,
    "num_round":        nTrees,
    "objective":        "binary",
    "reg_lambda":       1,
    "scale_pos_weight": 2,
    "subsample":        1,
    "task":             "train",
}

cat_common_params = {
    "depth":            8,
    "iterations":       nTrees,
    "l2_leaf_reg":      0.1,
    "learning_rate":    0.1,
    "loss_function":    "Logloss",
}

# NOTES: some benchmarks are disabled!
#  . xgb-gpu  encounters illegal memory access
#[16:16:33] /xgboost/dmlc-core/include/dmlc/./logging.h:300: [16:16:33] /xgboost/src/tree/updater_gpu.cu:528: GPU plugin exception: /xgboost/src/tree/../common/device_helpers.cuh(319): an illegal memory access was encountered
#  . cat-gpu  currently segfaults
benchmarks = {
    "xgb-cpu":      (True, XgbBenchmark, metrics,
                     dict(xgb_common_params, tree_method="exact",
                          nthread=nthreads)),
    "xgb-cpu-hist": (True, XgbBenchmark, metrics,
                     dict(xgb_common_params, nthread=nthreads,
                          grow_policy="lossguide", tree_method="hist")),
    "xgb-gpu":      (False, XgbBenchmark, metrics,
                     dict(xgb_common_params, tree_method="gpu_exact",
                          objective="gpu:binary:logistic")),
    "xgb-gpu-hist": (True, XgbBenchmark, metrics,
                     dict(xgb_common_params, tree_method="gpu_hist",
                          objective="gpu:binary:logistic")),

    "lgbm-cpu":     (True, LgbBenchmark, metrics,
                     dict(lgb_common_params, nthread=nthreads)),
    "lgbm-gpu":     (True, LgbBenchmark, metrics,
                     dict(lgb_common_params, device="gpu")),

    "cat-cpu":      (True, CatBenchmark, catMetrics,
                     dict(cat_common_params, thread_count=nthreads)),
    "cat-gpu":      (False, CatBenchmark, catMetrics,
                     dict(cat_common_params, task_type="GPU")),
}
