#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Use filebench to test manycore VFS performance.
"""

import os
import sys
sys.path.append('..')
import mfsbase
from collections import Counter
from multiprocessing import Process, Queue
from subprocess import Popen, PIPE
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
        mfsbase.mount(disk_path, os.path.join(mntdir, 'ram{}'.format(nram)))
        for dir_num in range(ndirs):
            dirpath = os.path.join(mntdir, 'ram{}'.format(nram),
                                   'test{}'.format(dir_num))
            os.makedirs(dirpath)


def filebench_task(queue, workload, testdir, nfiles, nproc, nthread, iosize):
    """Run filebench in a separate process.
    """
    conf = """
load {}
set $dir={}
set $nfiles={}
set $nprocesses={}
set $nthreads={}
set $iosize={}
set $meanappendsize=4k
run 10\n""".format(workload, testdir, nfiles, nproc, nthread, iosize)
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
    """
    """
    start_filebench(workload=args.workload,
                    ndisks=args.ndisks,
                    ndirs=args.ndirs,
                    basedir=args.basedir)


def start_filebench(**kwargs):
    """Run filebench in multiple processes.
    """
    workload = kwargs.get('workload', 'fileserver')
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    basedir = kwargs.get('basedir', 'ramdisks')

    q = Queue()
    tasks = []
    for disk in range(ndisks):
        for testdir in range(ndirs):
            testdir_path = os.path.join(basedir, 'ram{}'.format(disk),
                                        'test{}'.format(testdir))
            task = Process(target=filebench_task,
                           args=(q, workload, testdir_path, 1000, 1, 1, '4k'))
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
    return counters


def run_filebench(workload, **kwargs):
    """Run filebench results.
    """
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    basedir = kwargs.get('basedir', 'ramdisks')
    output = kwargs.get('output', 'filebench')

    lockstat = mfsbase.LockstatProfiler()
    procstat = mfsbase.ProcStatProfiler()
    perf = mfsbase.PerfProfiler(perf=PERF)
    lockstat.start()
    procstat.start()

    cmd = '{} run --disks {} --dirs {} -b {}' \
          .format(__file__, ndisks, ndirs, basedir)
    perf.start(cmd)

    procstat.stop()
    lockstat.stop()
    perf.stop()

    procstat.dump(output + '_cpustat.txt')
    lockstat.dump(output + '_lockstat.txt')

    mfsbase.umount_all('ramdisks')


def split_comma_fields(value):
    return value.split(',')


def test_scalability(args):
    prepare_disks()


def test_numa(args):
    """Test how NUMA architecture affects the filebench performance.
    """
    for fs in args.formats.split(','):
        prepare_disks('ramdisks', 4, 1, fs=fs)
        run_filebench('varmail')


def main():
    """Filebench tests
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--formats', metavar='FS,FS,..',
                        default=FILE_SYSTEMS,
                        help='sets testing file systems (default: {}).'
                        .format(FILE_SYSTEMS))
    parser.add_argument('-w', '--workloads', metavar='NAME,NAME,..',
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

    subs = parser.add_subparsers()

    parser_scale = subs.add_parser('scale', help='Test Scalability')
    parser_scale.set_defaults(func=test_scalability)

    parser_numa = subs.add_parser('numa', help='Test NUMA architecture')
    parser_numa.set_defaults(func=test_numa)

    parser_run = subs.add_parser('run', help='Test run filebench directly.')
    parser_run.add_argument('-n', '--disks', type=int, metavar='NUM',
                            default=4, help='set the number of disks to run.')
    parser_run.add_argument('-N', '--dirs', type=int, metavar='NUM',
                            default=1,
                            help='set the number of directories in each disk.')
    parser_run.add_argument('-b', '--basedir', metavar='DIR',
                            default='ramdisks',
                            help='set base dir to mount disks and run '
                                 'the test.')
    parser_run.add_argument('-w', '--workload', metavar='STR',
                            default='varmail',
                            help='set workload to run.')
    parser_run.set_defaults(func=test_run)

    args = parser.parse_args()
    if not 'func' in args:
        parser.print_help()
        sys.exit(1)

    global PERF
    PERF = args.perf
    mfsbase.check_root_or_exit()
    args.func(args)


if __name__ == '__main__':
    main()
