/**
 * \brief simply creating files in one directory.
 * Copyright 2012 (c) Lei Xu <eddyxu@gmail.com>
 */

#include <getopt.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
#include <vector>
#include "vobla/timer.h"

using std::string;
using std::thread;
using std::vector;
using vobla::Timer;

const int DEFAULT_NUM_FILES = 10000;
const char* program = NULL;

struct config {
  bool debug;
  int num_files;
  string prefix;
  string test_dir;
} config;

void usage() {
  fprintf(stderr, "Usage: %s [options] DIR\n"
          "Options:\n"
          "  -h, --help\t\tdisplay this help\n"
          "  -n, --num NUM\t\tset the total number of created files (10000)\n"
          "  -p, --prefix STR\tset the prefix of each file name\n", program);
}

const int BUFSIZE = 512;

struct FileCreator {
  FileCreator(const string& dir, int nfiles, const string& pre = "")
      : test_dir(dir), num_files(nfiles), prefix(pre) {
  }

  void operator()() {
    char filename[BUFSIZE];
  }

  string test_dir;
  int num_files;
  string prefix;
};

int create_files() {
  char filename[BUFSIZE];
  Timer timer;
  timer.start();
  for (int i = 0; i < config.num_files; ++i) {
    snprintf(filename, BUFSIZE, "%s/%s-%d", config.test_dir.c_str(),
             config.prefix.c_str(), i);
    int fd = open(filename, O_WRONLY|O_CREAT, 0x700);
    close(fd);
  }
  timer.stop();
  // Output the throughput
  printf("Throughput %0.2f files/sec.\n",
         config.num_files / timer.get_in_second());
  return 0;
}

int main(int argc, char* const* argv) {
  program = argv[0];
  config.debug = false;
  config.num_files = DEFAULT_NUM_FILES;

  static struct option longopts[] = {
    { "help", no_argument, NULL, 'h' },
    { "debug", no_argument, NULL, 1 },
    { "num", required_argument, NULL, 'n' },
    { "prefix", required_argument, NULL, 'p' },
    { NULL, 0, NULL, 0 }
  };
  const char shortopts[] = "hn:p:";
  char ch;
  while ((ch = getopt_long(argc, argv, shortopts, longopts, NULL)) != -1) {
    switch (ch) {
    case 1:
      config.debug = true;
      break;
    case 'n':
      config.num_files = atoi(optarg);
      break;
    case 'p':
      config.prefix = optarg;
      break;
    case 'h':
    default:
      usage();
      exit(1);
    }
  }
  argc -= optind;
  argv += optind;

  if (argc != 1 || config.prefix.empty()) {
    usage();
    exit(1);
  }
  config.test_dir = argv[0];
  create_files();
  return 0;
}
