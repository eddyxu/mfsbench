/**
 * \file directio.cpp
 * \brief Tests the difference with direct IOs and cached IO on SCM (RAM disks).
 *
 * Copyright 2012 (c) Lei Xu <eddyxu@gmail.com>
 */

#define _XOPEN_SOURCE 600

#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <gflags/gflags.h>
#include <glog/logging.h>
#include <sys/stat.h>
#include <unistd.h>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <memory>
#include <numeric>
#include <string>
#include <vector>
#include <thread>  // NOLINT
#include "vobla/sysinfo.h"
#include "vobla/timer.h"

using std::array;
using std::string;
using std::thread;
using std::unique_ptr;
using std::vector;
using vobla::Timer;
using vobla::SysInfo;

DEFINE_int32(num_threads, 48, "Defines the number of threads to run.");
DEFINE_int32(num_requests, 1000, "Numbers of requests for each threads.");
DEFINE_double(read_ratio, 0.4, "Ratio of read requests in all requests.");
DEFINE_bool(debug, false, "Run in debug mode.");
DEFINE_bool(directio, false, "Perform direct IO.");
DEFINE_bool(ramio, false, "Perform I/O in RAM.");
DEFINE_int32(iosize, 4096, "I/O size in bytes.");
DEFINE_string(io_type, "",
              "Set I/O type ('sequential', 'random', 'random_block')");

typedef vector<string> PathVector;
typedef vector<off_t> SizeVector;
typedef vector<double> ResultVector;

enum {
  IO_SEQUENTIAL,
  IO_RANDOM,
  IO_RANDOM_BLOCK,
};

PathVector files;
SizeVector sizes;
ResultVector results;
double total_time;
int io_type;

unsigned int seed;

class Worker {
 public:
  Worker(int thd_id, int file_desc, off_t fsize)
      : thread_id(thd_id), fd(file_desc), file_size(fsize), cur_offset(0),
    ram_file(0) {
    if (posix_memalign(&buffer, 4096, FLAGS_iosize) < 0) {
      perror("Buffer allocation");
    }
  }

  Worker(int thd_id, char* ram, off_t buf_size)
    : thread_id(thd_id), fd(0), file_size(buf_size), cur_offset(0),
      ram_file(ram) {
    if (posix_memalign(&buffer, 4096, FLAGS_iosize) < 0) {
      perror("Buffer allocation");
    }
  }

  ~Worker() {
    free(buffer);
  }

  void operator()() {
    Timer timer;
    timer.start();
    for (int i = 0; i < FLAGS_num_requests; i++) {
      if (FLAGS_ramio) {
        perform_ram_io();
      } else {
        perform_real_io();
      }
    }
    timer.stop();
    results[thread_id] = timer.get_in_ms();
  }

 private:
  // Only perform pure-RAM IOs
  void perform_ram_io() {
    off_t offset = next_offset();
    bool reading = is_read();
    if (reading) {
      memcpy(buffer, ram_file + offset, FLAGS_iosize);
    } else {
      memcpy(ram_file + offset, buffer, FLAGS_iosize);
    }
  }

  void perform_real_io() {
    ssize_t ret = 0;
    off_t offset = next_offset();
    bool reading = is_read();
    if (reading) {
      ret = pread(fd, buffer, FLAGS_iosize, offset);
    } else {
      ret = pwrite(fd, buffer, FLAGS_iosize, offset);
    }
    if (ret == -1) {
      LOG(ERROR) << "Failed to perform IO: "
          << "is_read: " << reading
          << ", offset: " << offset
          << ", size: " << FLAGS_iosize
          << " in thread " << thread_id
          << ": " << strerror(errno);
    }
  }

  off_t next_offset() {
    const int block_size = 4096;
    off_t ret = 0;
    switch (io_type) {
      case IO_SEQUENTIAL:
        ret = cur_offset;
        cur_offset = (cur_offset + FLAGS_iosize) % file_size;
        break;
      case IO_RANDOM:
        ret = static_cast<off_t>(
            static_cast<double>(rand_r(&seed)) / RAND_MAX *
                  (file_size - FLAGS_iosize));
        break;
      case IO_RANDOM_BLOCK:
        ret = static_cast<off_t>(
            static_cast<double>(rand_r(&seed)) / RAND_MAX *
                    (file_size - FLAGS_iosize) / block_size) * block_size;
        break;
    }
    ret = ret / 1024 * 1024;
    return ret;
  }

  bool is_read() const {
    double possibility = static_cast<double>(rand_r(&seed)) / RAND_MAX;
    return possibility <= FLAGS_read_ratio;
  }

  int thread_id;
  int fd;
  off_t file_size;
  off_t cur_offset;
  void* buffer;
  char* ram_file;
};

void report() {
  double avg_latency = 0;
  avg_latency = accumulate(results.begin(), results.end(), avg_latency) /
      results.size() / FLAGS_num_requests;
  double iops = 1000000.0 * FLAGS_num_requests * results.size() / total_time;
  printf("# THREADS REQUESTS IOPS AVG_LATENCY\n");
  printf("%8d %8d %8f %8f\n", FLAGS_num_threads, FLAGS_num_requests,
         iops, avg_latency);
}

int main(int argc, char* argv[]) {
  string usage("Usage: ");
  usage += string(argv[0]) + string(" [options] FILE [FILE ...]");
  google::SetUsageMessage(usage);
  google::ParseCommandLineFlags(&argc, &argv, true);

  if (FLAGS_io_type == "sequential") {
    io_type = IO_SEQUENTIAL;
  } else if (FLAGS_io_type == "random") {
    io_type = IO_RANDOM;
  } else if (FLAGS_io_type == "random_block") {
    io_type = IO_RANDOM_BLOCK;
  } else {
    LOG(FATAL) << "Wrong io type: " << FLAGS_io_type;
  }

  if (!FLAGS_ramio && !argc) {
    LOG(FATAL) << "Missing parameters!\n";
  }

  results.resize(FLAGS_num_threads);
  seed = time(0);

  if (FLAGS_ramio) {
    const int RAMFILE_SIZE = 512 * 1024 * 1024;
    char* ram_file = new char[RAMFILE_SIZE];
    vector<Worker> workers;
    workers.reserve(FLAGS_num_threads);
    vector<thread> threads;
    for (int i = 0; i < FLAGS_num_threads; i++) {
      workers.emplace_back(i, ram_file, RAMFILE_SIZE);
      threads.emplace_back(std::ref(workers.back()));
    }
    for (auto &thd : threads) {  // NOLINT
      thd.join();
    }

    delete[] ram_file;
    report();
    return 0;
  }

  for (int i = 1; i < argc; i++) {
    files.push_back(argv[i]);
    off_t file_size = SysInfo::get_size(argv[i]);
    CHECK_GT(file_size, 0);
    sizes.push_back(file_size);
  }

  int fd = 0;
  if (FLAGS_directio) {
#if defined(__linux__)
    fd = open(files[0].c_str(), O_RDWR | O_DIRECT);
#elif defined(__APPLE__)
    fd = open(files[0].c_str(), O_RDWR);
#endif
  } else {
    fd = open(files[0].c_str(), O_RDWR);
  }
  if (fd < 0) {
    perror("Failed to open file");
    return -1;
  }
#if defined(__APPLE__)
  // fcntl(fd, F_NOCACHE, 1);
#endif

  vector<Worker> workers;
  workers.reserve(FLAGS_num_threads);
  vector<thread> threads;
  for (int i = 0; i < FLAGS_num_threads; i++) {
    workers.emplace_back(i, fd, sizes[0]);
  }

  Timer total_timer;
  total_timer.start();
  for (int i = 0; i < FLAGS_num_threads; i++) {
    threads.emplace_back(std::ref(workers.back()));
  };
  for (auto &thd : threads) {  // NOLINT
    thd.join();
  }
  total_timer.stop();
  total_time = total_timer.get_in_ms();
  close(fd);

  report();
  return 0;
}
