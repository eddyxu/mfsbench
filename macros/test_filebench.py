#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Use filebench to test manycore VFS performance.
"""

import os
import sys
sys.path.append('..')
import mfsbase
import argparse
from subprocess import call
from multiprocessing import Process

FILE_SYSTEMS = 'ext4,btrfs'
WORKLOADS = 'varmail,fileserver,oltp,webserver,webproxy'


def prepare_disks(**kwargs):
    """Prepare disks
    """
    fs = kwargs.get('fs', 'ext4')
    num_subdirs = 4

    basedir = 'ramdisks'
    print('Preparing directories...{}'.format(basedir))
    if not os.path.exists(basedir):
        os.makedirs(basedir)
    mfsbase.umount_all(basedir)

    for nram in range(num_subdirs):
        disk_path = '/dev/ram{}'.format(nram)
        mntpnt = os.path.join(basedir, 'ram{}'.format(nram))
        if not os.path.exists(mntpnt):
            os.makedirs(mntpnt)
        mfsbase.mount(disk_path, 'ramdisks/ram{}'.format(nram))


def filebench_task(workload, testdir, nfiles, nproc, nthread, iosize):
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
run 60""".format(workload, testdir, nfiles, nproc, nthread, iosize)
    print(conf)

def run_filebench(fs, workload, **kwargs):
    """Run filebench results.
    """
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    basedir = kwargs.get('basedir', 'ramdisks')

    for disk in range(ndisks):
        for testdir in range(ndirs):
            testdir_path = os.path.join(basedir, 'ram{}'.format(disk),
                                        'test{}'.format(testdir))
            os.makedirs(testdir_path)

    lockstat = mfsbase.LockstatProfiler()
    procstat = mfsbase.ProcStatProfiler()
    lockstat.start()
    procstat.start()

    tasks = []
    for disk in range(ndisks):
        for testdir in range(ndirs):
            testdir_path = os.path.join(basedir, 'ram{}'.format(disk),
                                        'test{}'.format(testdir))
            task = Process(target=filebench_task,
                           args=('varmail', testdir_path, 1000, 1, 1, '4k'))
            task.start()
            tasks.append(task)
    for task in tasks:
        task.join()

    procstat.stop()
    lockstat.stop()
    mfsbase.umount_all('ramdisks')
    print(lockstat.report())
    print(procstat.report())


def test_scalability(args):
    prepare_disks()


def test_numa(args):
    prepare_disks()
    run_filebench('ext4', 'varmail')


def main():
    """Filebench tests
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--formats', metavar='FS,FS,..',
                        help='sets testing file systems (default: {}).'
                        .format(FILE_SYSTEMS))
    parser.add_argument('-w', '--workloads', metavar='NAME,NAME,..',
                        help='set workloads, separated by comma. (default: {})'
                        .format(WORKLOADS))
    parser.add_argument('-i', '--iteration', metavar='NUM', type=int,
                        default=1, help='set iteration, default: 1')
    parser.add_argument('-s', '--iosize', metavar='NUM', type=int,
                        default=1024, help='set IOSIZE (default: 1024)')

    subs = parser.add_subparsers()

    parser_scale = subs.add_parser('scale', help='Test Scalability')
    parser_scale.set_defaults(func=test_scalability)

    parser_numa = subs.add_parser('numa', help='Test NUMA architecture')
    parser_numa.set_defaults(func=test_numa)

    args = parser.parse_args()
    if not 'func' in args:
        parser.print_help()
        sys.exit(1)

    mfsbase.check_root_or_exit()
    args.func(args)


if __name__ == '__main__':
    main()
