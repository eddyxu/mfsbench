#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

from __future__ import print_function

import argparse
import glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import sys
sys.path.append('../pyro')
from pyro import analysis, perftest, plot
import numpy as np


def parse_filename(filename):
    fields = filename.split('_')
    return fields


def read_result_file(filepath):
    """Read the result file and return the value.
    @return (iops, throughput)
    """
    with open(filepath) as fobj:
        line = fobj.readline()
    return map(float, line.split())


def output_dir(input_dir):
    """Returns the path of output directory.
    If the output directory is not existed, it creates a new directory.
    """
    abspath = os.path.abspath(input_dir)
    output_dir = abspath + "_plots"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir


def plot_numa_result(args):
    """Plot NUMA results.
    """
    outdir = output_dir(args.dir)
    files = glob.glob(args.dir + '/*_results.txt')
    fb_result = analysis.Result()  # filebench result
    for filename in files:
        fields = parse_filename(os.path.basename(filename))
        fs = fields[1]
        workload = fields[2]
        cpus = fields[5]
        # iteration = int(fields[6])
        result = fields[7]
        # print(test, fs, workload, cpus, iteration, result)
        if result == 'results.txt':
            with open(filename) as fobj:
                line = fobj.readline()
            iops, throughput = map(float, line.split())
            # print(iops, throughput)
            if not fb_result[fs, workload, cpus]:
                fb_result[fs, workload, cpus] = {"iops": [], "throughput": []}
            fb_result[fs, workload, cpus, "iops"].append(iops)
            fb_result[fs, workload, cpus, "throughput"].append(throughput)
    # print(fb_result)
    # print(fb_result.keys())

    plt.figure()
    numa_cpus = ['0-23', '0-11,24-35', '0-5,12-17,24-29,36-41',
                 '0-2,6-8,12-14,18-20,24-26,30-32,36-38,42-44']
    for fs in fb_result:
        for measure in ['iops', 'throughput']:
            bars = []
            plt.figure()
            for wl in fb_result[fs]:
                # print(fs, fb_result[fs])
                y_values = np.array(
                    [np.average(fb_result[fs, wl, cpus, measure])
                     for cpus in numa_cpus])
                y_values /= y_values[0]
                bars += list(y_values)
            num_wl = len(fb_result[fs])
            x_values = np.array([0.1 + i for i in range(num_wl)])
            width = 0.2
            hatches = ['', '/', 'x', '-']
            labels = ['a', 'b', 'c', 'd']
            for i, h, l in zip(range(len(numa_cpus)), hatches, labels):
                plt.bar(x_values, bars[i::len(numa_cpus)], width=width,
                        color='w', hatch=h, label=l)
                x_values += width
            xticks = [0.5 + i for i in range(num_wl)]
            plt.xticks(xticks, list(fb_result[fs].keys()))
            plt.ylim(0, 1.32)
            plt.legend(ncol=2, loc='best')
            if measure == 'iops':
                plt.ylabel('Relative IOPS')
            else:
                plt.ylabel('Relative Throughput')
            plt.title('Filebench NUMA Test (%s)' % fs)

            figure_file = os.path.join(
                outdir, 'numa_' + fs + '_' + measure + '.pdf')
            plt.savefig(figure_file)
            plt.close()


def plot_scale_figure(dirpath, result, field, xlabel, ext='pdf'):
    """
    @param field "iops" or "throughput"
    """
    outdir = output_dir(dirpath)
    output_prefix = os.path.join(outdir, os.path.basename(dirpath))
    workload_linestyles = ['-', '--', '-+', '*']
    colors = ['b', 'r', 'k', 'y']
    plt.figure()
    for fs, color in zip(result, colors):
        for wl, ls in zip(sorted(result[fs].keys()), workload_linestyles):
            x_values = sorted(result[fs, wl].keys())
            y_values = []
            for xval in x_values:
                y_values.append(result[fs, wl, xval, field])
            # print(result[fs, wl])
            plt.plot(x_values, y_values, ls, label='%s (%s)' % (wl[0], fs),
                     color=color)

    plt.ylim(0)
    plt.legend(ncol=2)
    plt.xlabel(xlabel)
    plt.ylabel(field)
    plt.title('Filebench Scalability Test')
    plt.savefig(output_prefix + '_' + field.lower() + '.' + ext)
    plt.close()

    if result:
        workloads = []
        for fs in result:
            workloads = sorted(result[fs].keys())
            break
        assert workloads
        for wl in workloads:
            plot_per_workload_scale_figure(dirpath, result, wl,
                                           field, xlabel, ext)


def plot_per_workload_scale_figure(dirpath, result, wl, field, xlabel, ext):
    """Draw figure for each workload
    """
    outdir = output_dir(dirpath)
    output_prefix = os.path.join(outdir, os.path.basename(dirpath))
    linestyles = ['-', '--', '-+', '-*']
    plt.figure()
    for fs, ls in zip(sorted(result.keys()), linestyles):
        x_values = sorted(result[fs, wl].keys())
        y_values = []
        for xval in x_values:
            y_values.append(result[fs, wl, xval, field])
            # print(result[fs, wl])
        plt.plot(x_values, y_values, ls, label='%s' % fs, color='k')

    plt.ylim(0)
    plt.legend(ncol=2, prop={'size': 20})
    plt.xlabel(xlabel)
    plt.ylabel(field)
    plt.title('Filebench Scalability Test (%s)' % wl)
    plt.savefig(output_prefix + '_' + wl + '_' + field.lower() + '.' + ext)
    plt.close()


def plot_scale_result(args):
    """Plots performance results for scalability test.
    """
    files = glob.glob(args.dir + '/*_results.txt')
    fb_result = analysis.Result()
    for filename in files:
        fields = parse_filename(os.path.basename(filename))
        fs = fields[1]
        workload = fields[2]
        nproc = int(fields[5])
        result = fields[7]
        if result == 'results.txt':
            iops, throughput = read_result_file(filename)
            if not fb_result[fs, workload, nproc]:
                fb_result[fs, workload, nproc] = {"IOPS": [], "Throughput": []}
            fb_result[fs, workload, nproc, "IOPS"].append(iops)
            fb_result[fs, workload, nproc, "Throughput"].append(throughput)

    plot_scale_figure(args.dir, fb_result, 'IOPS', 'Threads', args.ext)
    plot_scale_figure(args.dir, fb_result, 'Throughput', 'Threads', args.ext)


def plot_cpuscale_result(args):
    """Plot CPU-scale performance
    """
    files = glob.glob(args.dir + '/*_results.txt')
    fb_result = analysis.Result()
    for filename in files:
        fields = parse_filename(os.path.basename(filename))
        # print(fields)
        fs = fields[1]
        workload = fields[2]
        ncpus = int(fields[5])
        iops, throughput = read_result_file(filename)
        if not fb_result[fs, workload, ncpus]:
            fb_result[fs, workload, ncpus] = {"IOPS": [], "Throughput": []}
        fb_result[fs, workload, ncpus, "IOPS"].append(iops)
        fb_result[fs, workload, ncpus, "Throughput"].append(throughput)

    plot_scale_figure(args.dir, fb_result, 'IOPS', 'CPUs', ext=args.ext)
    plot_scale_figure(args.dir, fb_result, 'Throughput', 'CPUs', ext=args.ext)


def plot_perf_result(args):
    """Plot outputs generated from perf (linux kernel performance tool).
    """
    outdir = output_dir(args.dir)
    files = glob.glob(args.dir + '/*_perf.txt')
    result = analysis.Result()
    for filename in files:
        fields = parse_filename(os.path.basename(filename))
        if fields[7] != 'perf.txt':
            continue
        fs = fields[1]
        workload = fields[2]
        nproc = int(fields[5])
        perf_data = perftest.parse_perf_data(filename)
        for event in perf_data:
            result[fs, workload, event, nproc] = \
                {x[2]: x[0] for x in perf_data[event]}
        # print(filename)
        # print(result)

    output_prefix = os.path.join(outdir, os.path.basename(args.dir))
    for fs in result:  # filesystem
        for wl in result[fs]:  # Workload
            for event in result[fs, wl]:
                outfile = output_prefix + \
                    '_%s_%s_%s_perf.%s' % (fs, wl, event, args.ext)
                perftest.plot_top_perf_functions(
                    result[fs, wl], event, 5, outfile, threshold=0.02)


def plot_lock_result(args):
    """Plot lockstat results
    """
    def _merge_lock_data(curves_by_name, key, lc):
        if key not in curves_by_name:
            curves_by_name[key] = (lc[0], np.array(lc[1]), key)
        else:
            curves_by_name[key] = (lc[0], curves_by_name[key][1] + lc[1], key)

    outdir = output_dir(args.dir)
    files = glob.glob(args.dir + '/*_lockstat.txt')
    result = analysis.Result()
    for filename in files:
        fields = parse_filename(os.path.basename(filename))
        # print(fields)
        if fields[0] == 'ncpu':
            fs = fields[2]
            workload = fields[3]
            nproc = int(fields[6])
        else:
            fs = fields[1]
            workload = fields[2]
            nproc = int(fields[5])
        lock_data = perftest.parse_lockstat_data(filename)
        result[fs, workload, nproc] = lock_data

    xlabel = '# of cores'
    ylabel = 'Samples'
    output_prefix = os.path.join(outdir, os.path.basename(args.dir))
    for fs in result:
        for wl in result[fs]:
            plot_data = {}
            first_nproc = list(result[fs, wl].keys())[0]
            first_func = list(result[fs, wl, first_nproc].keys())[0]
            fields = list(result[fs, wl, first_nproc, first_func].keys())
            for nproc in result[fs, wl]:
                for field in fields:
                    if field not in plot_data:
                        plot_data[field] = {}
                    top_n = 10
                    top_lock_data = perftest.get_top_n_locks(
                        result[fs, wl, nproc], field, top_n)
                    # print(top_lock_data)
                    plot_data[field][nproc] = top_lock_data
            for field in plot_data:
                top_lock_curves = perftest.trans_top_data_to_curves(
                    plot_data[field], top_n=5)
                # if not top_lock_curves:
                #    continue
                top_curves_by_name = {}
                for lc in top_lock_curves:
                    if lc[2].startswith('cpufreq_'):
                        continue
                    if ')' in lc[2]:
                        lc = (lc[0], lc[1], lc[2].split(')')[0])

                    key = lc[2]
                    if lc[2].startswith('dentry->'):
                        key = key.split('.')[0]
                    elif lc[2].startswith('journal->j_state_lock'):
                        key = 'journal->j_state_lock'
                    elif key.startswith('type->i_mutex_dir_key'):
                        key = 'i_mutex_dir_key'
                    _merge_lock_data(top_curves_by_name, key, lc)
                top_curves = list(top_curves_by_name.values())
                # print(top_curves)
                if not top_curves:
                    continue
                outfile = output_prefix + \
                    '_%s_%s_%s_lockstat.%s' % (fs, wl, field, args.ext)
                plot.plot(top_curves, 'Lockstat (%s)' % field,
                          xlabel, ylabel, outfile)


def main():
    """Plots the results from filebench.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('dir', metavar='DIR',
                        help='Sets the filebench result directory.')
    parser.add_argument('-e', '--ext', metavar='EXT', default='pdf',
                        help='Sets the extension of output file (pdf)')
    args = parser.parse_args()

    fields = parse_filename(args.dir)
    if fields[1] == 'numa':
        plot_numa_result(args)
        return
    elif fields[1] == 'scale':
        plot_scale_result(args)
    elif fields[1] == 'cpuscale':
        plot_cpuscale_result(args)
    elif fields[1] == 'multifs':
        # plot_multifs_result(args)
        pass

    plot_perf_result(args)
    plot_lock_result(args)


if __name__ == '__main__':
    main()
