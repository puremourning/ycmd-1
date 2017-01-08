#include <boost/python.hpp>
#include <benchmark/benchmark.h>

int main( int argc, char** argv )
{
  Py_Initialize();
  // Necessary because of usage of the ReleaseGil class
  PyEval_InitThreads();

  benchmark::Initialize( &argc, argv );
  benchmark::RunSpecifiedBenchmarks();
}
