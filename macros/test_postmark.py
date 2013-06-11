#!/usr/bin/env python
#
# Author: Lei Xu

"""Test running postmark different numa configurations"""

from subprocess import call
import optparse
import os
import sys
import StringIO
from itertools import product
sys.path.append('..')
from fsbench import utils as benchutils
from numa_utils import NumaRamDiskTest

DEFAULT_ITERATION = 3
options = None

class PostMarkTest(NumaRamDiskTest):
    """Filebench numa test
    """
    def __init__(self, output_dir, fstype, num_disks, num_dirs):
        """
        @param output_dir the output directory for result
        @param fstype ram disk file system type
        @param num_disks how many ram disks to mount
        @param num_dirs how many directories in one disk
        @param num_threads how many threads on each directory
        """
        super(PostMarkTest, self).__init__(fstype, num_disks)
        self.num_dirs = num_dirs
        self.output_dir = output_dir
        self.configurations = []

    def pre_test(self):
        """Pre test operations
        """
        benchutils.prepare_dir(self.output_dir)
        super(PostMarkTest, self).pre_test()

    def prepare_configurations(self):
        """
        """
        global options
        self.configurations = []
        for disk_id in xrange(self.num_disks):
            for dir_id in xrange(self.num_dirs):
                buffer = StringIO.StringIO()
                location = os.path.join(self.BASE_DIR, 'ram%d' % disk_id,
                        'test%d' % dir_id)
                if not os.path.exists(location):
                    os.makedirs(location)
                buffer.write('set number %d\n' % options.num)
                buffer.write('set location %s\n' % location)
                buffer.write('run\n')
                buffer.write('quit\n')
                self.configurations.append(buffer.getvalue())

    def run(self, numa_conf, iteration):
        """Run one iteration of this test
        """
        self.base_output_file = "%s_%d_%d_%s_%d" % \
            (self.fstype, self.num_disks, self.num_dirs, numa_conf, iteration)
        self.pre_test()
        self.prepare_configurations()
        command = "postmark"
        # Create several postmark process
        for thread_id in xrange(self.num_disks * self.num_dirs):
            core = self.get_cpu_id(numa_conf, thread_id)
            conf_content = self.configurations[thread_id]
            self.run_task_at_cpu(core, command, \
                    self.get_output_file('result_th_%d' % thread_id),
                    input=conf_content)
        self.post_test()

    def run_scalability(self, iteration):
        self.base_output_file = "scale_%s_%d_%d_%d" % \
                (self.fstype, self.num_disks, self.num_dirs, iteration)
        self.pre_test()
        self.prepare_configurations()
        command = "postmark"
        for thread_id in xrange(self.num_disks * self.num_dirs):
            conf_content = self.configurations[thread_id]
            self.run_task_at_cpu(thread_id, command,
                    self.get_output_file('scale_result'), input=conf_content)
        self.post_test()

def run_one_test(postmark):
    global options
    for numa_conf, i in product(['die', 'package', 'near', 'far'],
            range(options.iteration)):
        postmark.run(numa_conf, i)

def run_tests(output_dir, fstype):
    """Run test for the given fstype for several iterations
    """
    global options
    if options.debug:
       print "Run NUMA test"
    for num_disks in [2]:
        for num_dirs in range(1, 5):
            postmark = PostMarkTest(output_dir, fstype, num_disks, num_dirs)
            run_one_test(postmark)

def run_scalability_tests(output_dir, fstype):
    """Run scalability test: run 1 - 48 threads to one directory
    """
    global options
    if options.debug:
       print "Run scalability test"
    for num_disks in [1]:
        num_dirs = 1
        for num_threads in range(6, 49, 6):
            postmark = PostMarkTest(output_dir, fstype, num_disks, num_dirs)
            for i in xrange(options.iteration):
                print "Scalability test: %s, %d disks, %d threads, %d iteration" % \
                    (fstype, num_disks, num_threads, i)
                postmark.run_scalability(i)

def main():
    """Run postmark on a numa machine
    """
    parser = optparse.OptionParser()
    parser.add_option('--debug', action='store_true', default=False,
            help='run in debug mode')
    parser.add_option('-i', '--iteration', type=int, default=DEFAULT_ITERATION,
            metavar='NUM',
            help='set the number of iterations for each test (defualt:%d)' % \
                DEFAULT_ITERATION)
    parser.add_option('-f', '--fstypes', default='ext2,ext3,ext4,btrfs,xfs',
            type='string', metavar='TYPES', help='set the file systems to test')
    parser.add_option('-n', '--num', default=10000, type=int, metavar='NUM',
            help='set the number of file created')
    parser.add_option('-N', '--numa', action='store_true', default=False,
            help='run NUMA test')
    parser.add_option('-S', '--scalability', action='store_true', default=False,
            help='run scalability test')
    global options
    options, args = parser.parse_args()

    benchutils.check_root_or_die()
    suffix = ''
    if options.numa:
        suffix = 'numa'
    else:
        suffix = 'scale'
    output_dir = benchutils.get_output_directory(suffix=suffix, timestamp=True)
    fstypes = options.fstypes.split(',')
    for fs in fstypes:
        if options.numa:
            run_tests(output_dir, fs)
        elif options.scalability:
            run_scalability_tests(output_dir, fs)

if __name__ == '__main__':
    main()
