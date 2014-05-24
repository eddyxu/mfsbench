#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Use filebench to test manycore VFS performance.
"""

import os
import sys
sys.path.append('..')
sys.path.append('../pyro')
from collections import Counter
from datetime import datetime
from multiprocessing import Process, Queue
from pyro import osutil, checkpoint
from subprocess import Popen, PIPE
import argparse
import mfsbase
import re
import set_cpus
import shutil

FILE_SYSTEMS = 'ext2,ext4,btrfs,xfs'
WORKLOADS = None
PERF = 'perf'


def avail_workloads():
    """List all available local workloads.
    """
    workloads = sorted([os.path.splitext(workload)[0] for
                        workload in os.listdir('workloads')])
    return workloads

WORKLOADS = avail_workloads()


def prepare_disks(mntdir, ndisks, ndirs, **kwargs):
    """Prepare disks
    """
    fs = kwargs.get('fs', 'ext4')
    no_journal = kwargs.get('no_journal', False)
    # mount options.
    options = ''
    if fs == 'ext4':
        options = 'noatime,nodiratime'

    print('Preparing directories...{}'.format(mntdir))
    if not os.path.exists(mntdir):
        os.makedirs(mntdir)
    osutil.umount_all(mntdir)

    for nram in range(ndisks):
        disk_path = '/dev/ram{}'.format(nram)
        mntpnt = os.path.join(mntdir, 'ram{}'.format(nram))
        if not os.path.exists(mntpnt):
            os.makedirs(mntpnt)
        osutil.mount(disk_path,
                     os.path.join(mntdir, 'ram{}'.format(nram)),
                     format=fs, no_journal=no_journal, options=options)
        for dir_num in range(ndirs):
            dirpath = os.path.join(mntdir, 'ram{}'.format(nram),
                                   'test{}'.format(dir_num))
            os.makedirs(dirpath)


def filebench_task(queue, workload, testdir, nfiles, nproc, nthread, iosize,
                   kwargs):
    """Run filebench in a separate process.
    """
    runtime = kwargs.get('runtime', 60)
    cpus = kwargs.get('cpus', '')

    conf = """
load workloads/{}
set $dir={}
set $nfiles={}
set $nprocesses={}
set $nthreads={}
set $iosize={}
set $meanappendsize=4k
run {}\n""".format(workload, testdir, nfiles, nproc, nthread, iosize, runtime)
    print('Filebench confs: {}'.format(conf))
    cmd = 'filebench'
    if cpus:
        cmd = 'taskset -c %s filebench' % cpus
    cmd = cmd.split()
    p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate(conf.encode('utf-8'))
    output = stdout.decode('utf-8')
    print(output)
    for line in output.split('\n'):
        if 'Summary:' not in line:
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
    return start_filebench(workload=args.workload,
                           ndisks=args.disks,
                           ndirs=args.dirs,
                           nprocs=args.process,
                           nthreads=args.thread,
                           basedir=args.basedir,
                           output=args.output,
                           timeout=args.timeout,
                           affinity=args.affinity)


def start_filebench(**kwargs):
    """Run filebench in multiple processes.

    Optional params
    @param workload the filebench workload name.
    @param basedir the base directory to mount ramdisk.
    @param output the output file.
    @param ndisks the number of (RAM) disks.
    @param ndirs the number of dirs in one disk.
    @param nprocs the number of processes running in one filebench.
    @param nthreads the number of threads running in one filebench process.
    @param timeout the time to wait sub filebench process to finish.

    @return True if filebench successfully finished.
    """
    workload = kwargs.get('workload', 'fileserver')
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    nprocs = kwargs.get('nprocs', 1)
    nthreads = kwargs.get('nthreads', 1)
    basedir = kwargs.get('basedir', 'ramdisks')
    output = kwargs.get('output', None)
    iosize = kwargs.get('iosize', '4k')
    # the process should finish in 20 minutes
    join_timeout = kwargs.get('timeout', 1200)
    affinity = kwargs.get('affinity', False)

    q = Queue()
    tasks = []
    i = 0
    for disk in range(ndisks):
        for testdir in range(ndirs):
            testdir_path = os.path.join(basedir, 'ram{}'.format(disk),
                                        'test{}'.format(testdir))
            args = {'cpus': ''}
            if affinity:
                args['cpus'] = i % 48
                i += 1
            for i in range(nprocs):
                task = Process(target=filebench_task,
                               args=(q, workload, testdir_path, 10000, 1,
                                     nthreads, iosize, args))
                task.start()
                tasks.append(task)
    for task in tasks:
        task.join(join_timeout)
        if task.is_alive():
            # Terminate all tasks and return the benchmark.
            for t in tasks:
                if t.is_alive():
                    t.terminate()
            return False

    counters = Counter()
    while not q.empty():
        rst = q.get()
        # print(rst)
        counters['iops'] += rst['iops']
        counters['throughput'] += rst['throughput']
    print(counters)
    if output:
        with open(output, 'w+') as fobj:
            fobj.write('{} {}\n'.format(counters['iops'],
                                        counters['throughput']))
    return True


def run_filebench(workload, **kwargs):
    """Run filebench.
    """
    ndisks = kwargs.get('ndisks', 4)
    ndirs = kwargs.get('ndirs', 1)
    basedir = kwargs.get('basedir', 'ramdisks')
    cpus = kwargs.get('cpus', '')
    nprocs = kwargs.get('nprocs', 1)
    nthreads = kwargs.get('nthreads', 1)
    output = kwargs.get('output', 'filebench')
    no_profile = kwargs.get('no_profile', False)
    affinity = kwargs.get('affinity', False)

    if cpus:
        set_cpus.set_cpus(cpus)

    lockstat = None
    procstat = None
    perf = None
    if not no_profile:
        lockstat = mfsbase.LockstatProfiler()
        procstat = mfsbase.ProcStatProfiler()
        perf = mfsbase.PerfProfiler(perf=PERF, **kwargs)
    else:
        lockstat = mfsbase.NonProfiler()
        procstat = mfsbase.NonProfiler()
        perf = mfsbase.NonProfiler()

    lockstat.start()
    procstat.start()

    result_file = output + '_results.txt'
    cmd = '{} run -w {} --disks {} --dirs {} -b {} -p {} -t {} -o {}' \
          .format(__file__, workload, ndisks, ndirs, basedir, nprocs, nthreads,
                  result_file)
    if affinity:
        cmd += ' --affinity'
    print(cmd)

    perf.start(cmd)
    procstat.stop()
    lockstat.stop()

    # Move PerfProfile.stop() to the last because it generates hunders of MBs
    # logs, which has significant impact to procstat and lockstat accuracy.
    perf.stop()

    if cpus:
        set_cpus.reset()

    procstat.dump(output + '_cpustat.txt')
    lockstat.dump(output + '_lockstat.txt')
    perf.dump(output + '_perf.txt')

    osutil.umount_all('ramdisks')
    return True


def split_comma_fields(value):
    return value.split(',')


class SplitCommaAction(argparse.Action):
    """Split the comma separated values and returns as int list.
    """
    def __call__(self, parser, namespace, values, option_string=None):
        print(namespace, values, option_string)
        int_fields = map(int, split_comma_fields(values))
        setattr(namespace, self.dest, int_fields)


def create_checkpoint(filename, outdir_pre):
    """Creates a Checkpoint instance with output directory appropriated set up.
    """
    check_point = checkpoint.Checkpoint(filename)
    output_dir = ''
    if check_point.outdir:
        output_dir = check_point.outdir
    else:
        now = datetime.now()
        output_dir = outdir_pre + '_' + now.strftime('%Y_%m_%d_%H_%M')
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        check_point.set_outdir(output_dir)
    return check_point


def test_scalability(args):
    """Test scalability of manycore

    @return True if all tasks are finished.
    """
    ndisks = 1
    ndirs = 1
    no_journal = args.no_journal

    check_point = checkpoint.Checkpoint('scale_checkpoint.log')
    output_dir = ''
    if check_point.outdir:
        output_dir = check_point.outdir
    else:
        now = datetime.now()
        output_dir = 'filebench_scale_' + now.strftime('%Y_%m_%d_%H_%M')
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        check_point.set_outdir(output_dir)

    test_conf = {
        'test': 'scale',
        'filesystems': args.formats,
        'workloads': args.workloads,
        'iteration': args.iteration,
        'processes': str(list(range(4, 96, 12))),
        'ndisks': ndisks,
        'ndirs': ndirs,
        'mount_options': 'noatime,nodirtime',
    }
    mfsbase.dump_configure(test_conf, os.path.join(output_dir, 'testmeta.txt'))

    steps = 0
    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for nproc in map(int, args.nproc):
                for i in range(args.iteration):
                    steps += 1
                    if check_point.steps >= steps:
                        continue
                    check_point.start()
                    print('Run scalability test')
                    output_prefix = '{}/scale_{}_{}_{}_{}_{}_{}'.format(
                        output_dir, fs, wl, ndisks, ndirs, nproc, i)
                    prepare_disks('ramdisks', ndisks, ndirs, fs=fs,
                                  no_journal=no_journal)
                    if not run_filebench(wl, ndisks=ndisks, ndirs=ndirs,
                                         nprocs=nproc,
                                         threads=1, output=output_prefix,
                                         events=args.events,
                                         vmlinux=args.vmlinux,
                                         kallsyms=args.kallsyms,
                                         no_profile=args.no_profile):
                        print('Failed to execute run_filebench')
                        return False
                    check_point.done()

    return True


def test_cpu_scale(args):
    """Run benchmark with different active CPUs.
    """
    ndisks = 1
    ndirs = 1
    no_journal = args.no_journal

    check_point = checkpoint.Checkpoint('cpu_checkpoint.log')
    output_dir = ''
    if check_point.outdir:
        output_dir = check_point.outdir
    else:
        now = datetime.now()
        output_dir = 'filebench_cpuscale_' + now.strftime('%Y_%m_%d_%H_%M')
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        check_point.set_outdir(output_dir)

    test_conf = {
        'test': 'cpu_scale',
        'filesystems': args.formats,
        'workloads': args.workloads,
        'iteration': args.iteration,
        'processes': str(list(range(4, 96, 12))),
        'ndisks': ndisks,
        'ndirs': ndirs,
        'mount_options': 'noatime,nodirtime',
    }
    mfsbase.dump_configure(test_conf, os.path.join(output_dir, 'testmeta.txt'))

    steps = 0
    nproc = args.process
    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for ncpus in map(int, args.cpus):
                cpus = "0-{}".format(ncpus - 1)
                print('CPU scale test: cpus: {}, fs: {}, workload: {}'.format(
                    cpus, fs, wl))
                set_cpus.set_cpus(cpus)
                for i in range(args.iteration):
                    steps += 1
                    if check_point.should_skip(steps):
                        continue
                    check_point.start()
                    retry = args.retry
                    print('Run CPU scalability test')
                    output_prefix = '{}/cpuscale_{}_{}_{}_{}_{}_{}'.format(
                        output_dir, fs, wl, ndisks, ndirs, ncpus, i)
                    while retry:
                        prepare_disks('ramdisks', ndisks, ndirs, fs=fs,
                                      no_journal=no_journal)
                        if not run_filebench(wl, ndisks=ndisks, ndirs=ndirs,
                                             nprocs=nproc,
                                             threads=1, output=output_prefix,
                                             events=args.events,
                                             vmlinux=args.vmlinux,
                                             kallsyms=args.kallsyms,
                                             no_profile=args.no_profile):
                            # set_cpus.reset()
                            print('Failed to execute run_filebench')
                            retry -= 1
                            continue
                        break
                    if retry > 0:
                        check_point.done()
                    else:
                        set_cpus.reset()
                        return False
                set_cpus.reset()
    return True


def test_numa(args):
    """Test how NUMA architecture affects the filebench performance.
    """
    CPU_CONFS = ['0-23', '0-11,24-35', '0-5,12-17,24-29,36-41',
                 '0-2,6-8,12-14,18-20,24-26,30-32,36-38,42-44']
    ndisks = args.disks
    ndirs = args.dirs
    nproc = 48

    # Prepare output disk
    check_point = create_checkpoint('numa_checkpoint.log', 'filebench_numa')
    test_conf = {
        'test': 'numa',
        'filesystems': args.formats,
        'workloads': args.workloads,
        'iteration': args.iteration,
        'ndisks': ndisks,
        'ndirs': ndirs,
        'mount_options': 'noatime,nodirtime',
    }
    mfsbase.dump_configure(test_conf,
                           os.path.join(check_point.outdir, 'testmeta.txt'))

    steps = 0
    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for cpus in CPU_CONFS:
                set_cpus.set_cpus(cpus)
                for i in range(args.iteration):
                    steps += 1
                    if check_point.should_skip(steps):
                        continue
                    check_point.start()
                    output_prefix = '{}/numa_{}_{}_{}_{}_{}_{}'.format(
                        check_point.outdir, fs, wl, ndisks, ndirs, cpus, i)
                    print('Run NUMA test on CPUs {} for iteration {}'
                          .format(cpus, i))
                    retry = args.retry
                    while retry:
                        prepare_disks('ramdisks', ndisks, ndirs, fs=fs,
                                      no_journal=args.no_journal)
                        if run_filebench(wl, ndisks=ndisks, ndirs=ndirs,
                                         nprocs=nproc,
                                         threads=1, output=output_prefix,
                                         events=args.events,
                                         vmlinux=args.vmlinux,
                                         kallsyms=args.kallsyms,
                                         no_profile=args.no_profile):
                            break
                        print('Failed to execute run_filebench')
                        retry -= 1
                    if not retry:
                        set_cpus.reset()
                        return False
                    check_point.done()
            set_cpus.reset()
    return True


def test_multi_filesystem(args):
    """Test on multiple file systems.
    """
    ndirs = 1
    nprocs = 96
    check_point = create_checkpoint('multifs_checkpoint.log',
                                    'filebench_multifs')

    test_conf = {
        'test': 'multi_filesystem',
        'filesystems': args.formats,
        'workloads': args.workloads,
        'iteration': args.iteration,
        'ndisks': args.ndisks,
        'ndirs': ndirs,
        'mount_options': 'noatime,nodirtime',
    }
    mfsbase.dump_configure(test_conf,
                           os.path.join(check_point.outdir, 'testmeta.txt'))

    steps = 0
    for fs in args.formats.split(','):
        for wl in args.workloads.split(','):
            for num_disks in args.ndisks:
                for num_dirs in range(1, ndirs + 1):
                    for i in range(args.iteration):
                        steps += 1
                        if check_point.should_skip(steps):
                            continue
                        check_point.start()
                        retry = args.retry
                        print("Run multi-filesystem test: " +
                              "{} disk {} dirs".format(num_disks, num_dirs))
                        output_prefix = '{}/multifs_{}_{}_{}_{}_{}_{}'.format(
                            check_point.outdir, fs, wl, num_disks, ndirs,
                            nprocs, i)
                        while retry:
                            prepare_disks('ramdisks', num_disks, num_dirs,
                                          fs=fs, no_journal=args.no_journal)
                            if not run_filebench(
                                    wl, ndisks=num_disks, ndirs=num_dirs,
                                    nprocs=nprocs, threads=1,
                                    output=output_prefix,
                                    events=args.events,
                                    vmlinux=args.vmlinux,
                                    kallsyms=args.kallsyms,
                                    no_profile=args.no_profile,
                                    affinity=True):
                                print('Failed to execute run_filebench')
                                retry -= 1
                                continue
                            break
                        if retry > 0:
                            check_point.done()
                        else:
                            return False
    return True


def main():
    """Filebench tests
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--formats', metavar='FS,..',
                        default=FILE_SYSTEMS,
                        help='sets testing file systems (default: {}).'
                        .format(FILE_SYSTEMS))
    parser.add_argument('-w', '--workloads', metavar='NAME,..',
                        default=WORKLOADS,
                        help='set workloads, separated by comma. (default: {})'
                        .format(','.join(WORKLOADS)))
    parser.add_argument('-i', '--iteration', metavar='NUM', type=int,
                        default=1, help='set iteration, default: 1')
    parser.add_argument('-s', '--iosize', metavar='NUM', type=int,
                        default=1024, help='set IOSIZE (default: 1024)')
    parser.add_argument('-r', '--run', metavar='NUM', type=int,
                        default=60, help='set run time (default: 60)')
    parser.add_argument('--no_profile', action='store_true', default=False,
                        help='disable running profiling tools')
    parser.add_argument('-j', '--no-journal', action='store_true',
                        default=False, help='turn off journaling on ext4.')
    parser.add_argument('--perf', default='perf',
                        help='set the location of "perf"')
    parser.add_argument('-e', '--events', default='cycles', metavar='EVT,..',
                        help='set the events to monitor by perf '
                             '(default: cycles)')
    parser.add_argument('-k', '--vmlinux', default=None, metavar='FILE',
                        help='set vmlinux pathname for perf (optional)')
    parser.add_argument('-S', '--kallsyms', default=None, metavar='FILE',
                        help='set kallsyms pathname for perf (optional)')
    parser.add_argument('-R', '--retry', type=int, metavar='NUM', default=5,
                        help='Retry hanging benchmark (default: %(default)d)')

    subs = parser.add_subparsers()

    parser_scale = subs.add_parser('scale', help='Test scalability by running'
                                   ' multiprocess on all CPUs.')
    parser.add_argument('-p', '--nproc', metavar='nproc',
                        action=SplitCommaAction, default=range(4, 61, 4),
                        help='sets the number of processes to test.')
    parser_scale.set_defaults(func=test_scalability)

    # Options for sub-command 'cpuscale'
    parser_cpuscale = subs.add_parser(
        'cpuscale', help='Test CPU scale test with different numbers of '
        'active CPUs.')
    parser_cpuscale.add_argument(
        '-c', '--cpus', metavar='cpus', action=SplitCommaAction,
        default=range(4, 49, 4),
        help='sets the number of activate CPUs to test.')
    parser_cpuscale.add_argument(
        '-p', '--process', type=int, metavar='NUM',
        default=128, help='set the number of processes (default: %(default)d)')
    parser_cpuscale.add_argument(
        '-t', '--thread', type=int, metavar='NUM',
        default=1, help='set the number of threads (default: %(default)d)')
    parser_cpuscale.set_defaults(func=test_cpu_scale)

    parser_numa = subs.add_parser('numa', help='Test NUMA architecture.')
    parser_numa.add_argument('-n', '--disks', type=int, metavar='NUM',
                             default=1, help='set the number of disks to run.')
    parser_numa.add_argument(
        '-N', '--dirs', type=int, metavar='NUM', default=1,
        help='set the number of directories in each disk.')
    parser_numa.set_defaults(func=test_numa)

    parser_multifs = subs.add_parser('multifs', help='Test multi-filesystem.')
    parser_multifs.add_argument('--ndisks', metavar='NUM',
                                action=SplitCommaAction, default=range(1, 5),
                                help='sets the number of disks to run')
    parser_multifs.set_defaults(func=test_multi_filesystem)

    parser_run = subs.add_parser('run', help='Test run filebench directly.')
    parser_run.add_argument('-n', '--disks', type=int, metavar='NUM',
                            default=4, help='set the number of disks to run.')
    parser_run.add_argument('-N', '--dirs', type=int, metavar='NUM',
                            default=1,
                            help='set the number of directories in each disk.')
    parser_run.add_argument('-p', '--process', type=int, metavar='NUM',
                            default=1, help='set the number of processes.')
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
    parser_run.add_argument(
        '--timeout', metavar='SEC', type=int, default=600,
        help="set the timeout of waiting process to finish, "
             "default: %(default)d seconds.")
    parser_run.add_argument('--affinity', action='store_true', default=False,
                            help='set CPU affinity for each group of threads')
    parser_run.set_defaults(func=test_run)

    args = parser.parse_args()
    if 'func' not in args:
        parser.print_help()
        sys.exit(1)

    global PERF
    PERF = args.perf
    osutil.check_root_or_exit()
    return args.func(args)

if __name__ == '__main__':
    if not main():
        sys.exit(1)
