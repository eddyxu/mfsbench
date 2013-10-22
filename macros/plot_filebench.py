#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

import argparse
import os
import matplotlib.pyplot as plt
import sys
sys.path.append('../pyro')
from pyro import analysis, perftest


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
    files = os.listdir(args.dir)
    fb_result = analysis.Result()  # filebench result
    for filename in files:
        fields = parse_filename(filename)
        test = fields[0]
        fs = fields[1]
        workload = fields[2]
        cpus = fields[5]
        #iteration = int(fields[6])
        result = fields[7]
        #print(test, fs, workload, cpus, iteration, result)
        if result == 'results.txt':
            with open(os.path.join(args.dir, filename)) as fobj:
                line = fobj.readline()
            iops, throughput = map(float, line.split())
            #print(iops, throughput)
            if not fb_result[fs, workload, cpus]:
                fb_result[fs, workload, cpus] = {"iops": [], "throughput": []}
            fb_result[fs, workload, cpus, "iops"].append(iops)
            fb_result[fs, workload, cpus, "throughput"].append(throughput)
    print(fb_result)
    print(fb_result.keys())

    output_prefix = args.dir
    plt.figure()
    for fs in fb_result:
        print(fs, fb_result[fs])
    plt.savefig(output_prefix + "_iops.pdf")


def plot_scale_result(args):
    """Plots performance results for scalability test.
    """
    outdir = output_dir(args.dir)
    files = os.listdir(args.dir)
    fb_result = analysis.Result()
    for filename in files:
        fields = parse_filename(filename)
        fs = fields[1]
        workload = fields[2]
        nproc = int(fields[5])
        result = fields[7]
        if result == 'results.txt':
            iops, throughput = read_result_file(
                os.path.join(args.dir, filename))
            if not fb_result[fs, workload, nproc]:
                fb_result[fs, workload, nproc] = {"iops": [], "throughput": []}
            fb_result[fs, workload, nproc, "iops"].append(iops)
            fb_result[fs, workload, nproc, "throughput"].append(throughput)

    # Plot IOPS results
    output_prefix = os.path.join(outdir, os.path.basename(args.dir))
    plt.figure()
    for fs in fb_result:
        for wl in fb_result[fs]:
            processes = sorted(fb_result[fs, wl].keys())
            iops = []
            for proc in processes:
                iops.append(fb_result[fs, wl, proc, "iops"])
            print(fb_result[fs, wl])
            plt.plot(processes, iops, label='%s (%s)' % (wl, fs))

    plt.ylim(0)
    plt.legend()
    plt.xlabel('Threads')
    plt.ylabel('IOPS')
    plt.title('Filebench Scalability Test')
    plt.savefig(output_prefix + '_iops.' + args.ext)

    # Plot Throughput results
    plt.figure()
    for fs in fb_result:
        for wl in fb_result[fs]:
            processes = sorted(fb_result[fs, wl].keys())
            iops = []
            for proc in processes:
                iops.append(fb_result[fs, wl, proc, "throughput"])
            plt.plot(processes, iops, label='%s (%s)' % (wl, fs))

    plt.ylim(0)
    plt.legend()
    plt.xlabel('Threads')
    plt.ylabel('Throughput (MB/s)')
    plt.title('Filebench Scalability Test')
    plt.savefig(output_prefix + '_throughput.' + args.ext)


def plot_perf_result(args):
    """Plot outputs generated from perf (linux kernel performance tool).
    """
    outdir = output_dir(args.dir)
    files = os.listdir(args.dir)
    result = analysis.Result()
    for filename in files:
        fields = parse_filename(filename)
        if fields[7] != 'perf.txt':
            continue
        fs = fields[1]
        workload = fields[2]
        nproc = int(fields[5])
        perf_file = os.path.join(args.dir, filename)
        perf_data = perftest.parse_perf_data(perf_file)
        for event in perf_data:
            result[fs, workload, event, nproc] = \
                {x[2]: x[0] for x in perf_data[event]}
        #print(filename)
        #print(result)

    output_prefix = os.path.join(outdir, os.path.basename(args.dir))
    for fs in result:  # filesystem
        for wl in result[fs]:  # Workload
            for event in result[fs, wl]:
                outfile = output_prefix + \
                    '_%s_%s_%s_perf.%s' % (fs, wl, event, args.ext)
                perftest.plot_top_perf_functions(
                    result[fs, wl], event, 10, outfile, threshold=0.02)


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
    elif fields[1] == 'scale':
        plot_scale_result(args)
    plot_perf_result(args)


if __name__ == '__main__':
    main()
