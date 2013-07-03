#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

import argparse
import os
import matplotlib.pyplot as plt


def parse_filename(filename):
    fields = filename.split('_')
    return fields


def plot_numa_result(args):
    """Plot NUMA results.
    """
    files = os.listdir(args.dir)
    for filename in files:
        fields = parse_filename(filename)
        test = fields[0]
        fs = fields[1]
        workload = fields[2]
        cpus = fields[5]
        iteration = int(fields[6])
        result = fields[7]
        print(test, fs, workload, cpus, iteration, result)
        if result == 'results.txt':
            with open(os.path.join(args.dir, filename)) as fobj:
                line = fobj.readline()
            print(line)


def main():
    """Plots the results from filebench.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('dir', metavar='DIR',
                        help='Sets the filebench result directory.')
    parser.add_argument('-o', '--output', metavar='FILE', default=None,
                        help='Sets the output file.')
    args = parser.parse_args()

    plot_numa_result(args)


if __name__ == '__main__':
    main()