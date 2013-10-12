#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Use filebench to test manycore VFS performance.
"""

import os
import sys
sys.path.append('..')
import mfsbase
import set_cpus
from collections import Counter
from multiprocessing import Process, Queue
from subprocess import Popen, PIPE
from datetime import datetime
import shutil
import argparse
import re

FILE_SYSTEMS = 'ext4,btrfs'
WORKLOADS = 'varmail,fileserver,oltp,webserver,webproxy'
PERF = 'perf'


def prepare_disks(mntdir, ndisks, ndirs, **kwargs):
    """Prepare disks
    """
    fs = kwargs.get('fs', 'ext4')
    print('Preparing directories...{}'.format(mntdir))
    if not os.path.exists(mntdir):
        os.makedirs(mntdir)
    mfsbase.umount_all(mntdir)

    for nram in range(ndisks):

        disk_path = '/dev/ram{}'.format(nram)
        mntpnt = os.path.join(mntdir, 'ram{}'.format(nram))
        if not os.path.exists(mntpnt):
            os.makedirs(mntpnt)
        mfsbase.mount(disk_path, os.path.join(mntdir, 'ram{}'.format(nram)),
                      format=fs)
        for dir_num in range(ndirs):
            dirpath = os.path.join(mntdir, 'ram{}'.format(nram),
                                   'test{}'.format(dir_num))
            os.makedirs(dirpath)


def filebench_task(queue, workload, testdir, nfiles, nproc, nthread, iosize,
                   **kwargs):
    """Run filebench in a separate process.
    """
    runtime = kwargs.get('runtime', 60)
    conf = """
load {}
set $dir={}
set $nfiles={}
set $nprocesses={}
set $nthreads={}
set $iosize={}
set $meanappendsize=4k
run ${}\n""".format(workload, testdir, nfiles, nproc, nthread, iosize, runtime)
    p = Popen('filebench', stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate(conf.encode('utf-8'))
    output = stdout.decode('utf-8')
    for line in output.split('\n'):
        if not 'Summary:' in line:
            continue
        fields = line.split()
        iops = float(fields[6])
        tp_num = re.search(r'\d+(\.\d+)?', fields[10]).group()
        throughput = float(tp_num)
        ret = {'iops': iops, 'throughput': throughput}
        queue.put(ret)
        break


def test_run(args):
    """Run a single filebench test.
    """
    start_filebench(workload=args.workload,
                    ndisks=args.disks,
                    ndirs=args.dirs,
                    nprocs=args.process,
                    nthreads=args.thread,
                    basedir=args.basedir,
                    output=args.output)


def start_filebench(**kwargs):
    """Run filebench in multiple processes.
    """
    workload = kwargs.get('workload', 'fileserver')
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    nprocs = kwargs.get('nprocs', 1)
    nthreads = kwargs.get('nthreads', 1)
    basedir = kwargs.get('basedir', 'ramdisks')
    output = kwargs.get('output', None)

    q = Queue()
    tasks = []
    for disk in range(ndisks):
        for testdir in range(ndirs):
            testdir_path = os.path.join(basedir, 'ram{}'.format(disk),
                                        'test{}'.format(testdir))
            task = Process(target=filebench_task,
                           args=(q, workload, testdir_path, 1000, nprocs,
                                 nthreads, '4k'))
            task.start()
            tasks.append(task)
    for task in tasks:
        task.join()
    counters = Counter()
    while not q.empty():
        rst = q.get()
        counters['iops'] += rst['iops']
        counters['throughput'] += rst['throughput']
    print(counters)
    if output:
        with open(output, 'w+') as fobj:
            fobj.write('{} {}\n'.format(counters['iops'],
                                        counters['throughput']))
    return counters


def run_filebench(workload, **kwargs):
    """Run filebench results.
    """
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    basedir = kwargs.get('basedir', 'ramdisks')
    cpus = kwargs.get('cpus', '')
    nprocs = kwargs.get('nprocs', 1)
    nthreads = kwargs.get('nthreads', 1)
    output = kwargs.get('output', 'filebench')

    if cpus:
        set_cpus.set_cpus(cpus)

    lockstat = mfsbase.LockstatProfiler()
    procstat = mfsbase.ProcStatProfiler()
    perf = mfsbase.PerfProfiler(perf=PERF, **kwargs)
    lockstat.start()
    procstat.start()

    result_file = output + '_results.txt'
    cmd = '{} run --disks {} --dirs {} -b {} -p {} -t {} -o {}' \
          .format(__file__, ndisks, ndirs, basedir, nprocs, nthreads,
                  result_file)
    print(cmd)
    perf.start(cmd)
    procstat.stop()
    lockstat.stop()
    perf.stop()

    if cpus:
        set_cpus.reset()

    procstat.dump(output + '_cpustat.txt')
    lockstat.dump(output + '_lockstat.txt')
    perf.dump(output + '_perf.txt')

    mfsbase.umount_all('ramdisks')
    return True


def split_comma_fields(value):
    return value.split(',')


def test_scalability(args):
    """Test scalability of manycore
    """
    ndisks = 1
    ndirs = 1

    now = datetime.now()
    output_dir = 'filebench_scale_' + now.strftime('%Y_%m_%d_%H_%M')
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for nproc in range(4, 96, 12):
                for i in range(args.iteration):
                    print('Run scalability test')
                    output_prefix = '{}/scale_{}_{}_{}_{}_{}_{}'.format(
                        output_dir, fs, wl, ndisks, ndirs, nproc, i)
                    prepare_disks('ramdisks', ndisks, ndirs, fs=fs)
                    if not run_filebench(wl, ndisks=ndisks, ndirs=ndirs,
                                         nthreads=nproc, output=output_prefix,
                                         events=args.events,
                                         vmlinux=args.vmlinux,
                                         kallsyms=args.kallsyms):
                        print('Failed to execute run_filebench')
                        return False
    return True


def test_numa(args):
    """Test how NUMA architecture affects the filebench performance.
    """
    CPU_CONFS = ['0-23', '0-11,24-35', '0-5,12-17,24-29,36-41',
                 '0-2,6-8,12-14,18-20,24-26,30-32,36-38,42-44']
    ndisks = args.disks
    ndirs = args.dirs

    # Prepare output disk
    now = datetime.now()
    output_dir = 'filebench_numa_' + now.strftime('%Y_%m_%d_%H_%M')
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for cpus in CPU_CONFS:
                for i in range(args.iteration):
                    output_prefix = '{}/numa_{}_{}_{}_{}_{}_{}'.format(
                        output_dir, fs, wl, ndisks, ndirs, cpus, i)
                    print('Run NUMA test on CPUs {} for iteration {}'
                          .format(cpus, i))
                    prepare_disks('ramdisks', ndisks, ndirs, fs=fs)
                    if not run_filebench(wl, cpus=cpus, output=output_prefix):
                        print('Failed to execute run_filebench')
                        return False
    return True


def main():
    """Filebench tests
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--formats', metavar='FS,FS,..',
                        default=FILE_SYSTEMS,
                        help='sets testing file systems (default: {}).'
                        .format(FILE_SYSTEMS))
    parser.add_argument('-w', '--workloads', metavar='NAME,NAME,..',
                        default=WORKLOADS,
                        help='set workloads, separated by comma. (default: {})'
                        .format(WORKLOADS))
    parser.add_argument('-i', '--iteration', metavar='NUM', type=int,
                        default=1, help='set iteration, default: 1')
    parser.add_argument('-s', '--iosize', metavar='NUM', type=int,
                        default=1024, help='set IOSIZE (default: 1024)')
    parser.add_argument('-r', '--run', metavar='NUM', type=int,
                        default=60, help='set run time (default: 60)')
    parser.add_argument('--perf', default='perf',
                        help='set the location of "perf"')
    parser.add_argument('-e', '--events', default='cycles', metavar='EVT,..',
                        help='set the events to monitor by perf '
                             '(default: cycles)')
    parser.add_argument('-k', '--vmlinux', default=None, metavar='FILE',
                        help='set vmlinux pathname for perf (optional)')
    parser.add_argument('-S', '--kallsyms', default=None, metavar='FILE',
                        help='set kallsyms pathname for perf (optional)')


    subs = parser.add_subparsers()

    parser_scale = subs.add_parser('scale', help='Test Scalability')
    parser_scale.set_defaults(func=test_scalability)

    parser_numa = subs.add_parser('numa', help='Test NUMA architecture')
    parser_numa.add_argument('-n', '--disks', type=int, metavar='NUM',
                             default=4, help='set the number of disks to run.')
    parser_numa.add_argument(
        '-N', '--dirs', type=int, metavar='NUM', default=1,
        help='set the number of directories in each disk.')
    parser_numa.set_defaults(func=test_numa)

    parser_run = subs.add_parser('run', help='Test run filebench directly.')
    parser_run.add_argument('-n', '--disks', type=int, metavar='NUM',
                            default=4, help='set the number of disks to run.')
    parser_run.add_argument('-N', '--dirs', type=int, metavar='NUM',
                            default=1,
                            help='set the number of directories in each disk.')
    parser_run.add_argument('-p', '--process', type=int, metavar='NUM',
                            default=0, help='set the number of processes.')
    parser_run.add_argument('-t', '--thread', type=int, metavar='NUM',
                            default=1, help='set the number of threads.')
    parser_run.add_argument(
        '-b', '--basedir', metavar='DIR', default='ramdisks',
        help='set base dir to mount disks and run the test.')
    parser_run.add_argument(
        '-w', '--workload', metavar='STR', default='varmail',
        help='set workload to run.')
    parser_run.add_argument('-o', '--output', metavar='FILE', default=None,
                            help='set the output file.')
    parser_run.set_defaults(func=test_run)

    args = parser.parse_args()
    if not 'func' in args:
        parser.print_help()
        sys.exit(1)

    global PERF
    PERF = args.perf
    mfsbase.check_root_or_exit()
    return args.func(args)

if __name__ == '__main__':
    main()
