project('dxmt-regression', 'cpp', default_options: ['cpp_std=c++20', 'warning_level=2', 'b_ndebug=false'])

inc = include_directories('../../src/util', '../../src/winemetal',
                          '../../include/native/windows', '../../include/native/directx')
threads = dependency('threads')
test('cache-isolation', executable('cache-isolation', 'cache_isolation.cpp'))
test('scheduler-lifetime', executable('scheduler-lifetime', 'scheduler_lifetime.cpp',
     include_directories: inc, dependencies: threads), timeout: 30)
test('reference-ownership', executable('reference-ownership', 'reference_ownership.cpp',
     include_directories: inc))
test('shader-bitcode-cleanup', executable('shader-bitcode-cleanup', 'shader_bitcode_cleanup.cpp',
     include_directories: [inc, include_directories('../../src/airconv')]))
if host_machine.system() == 'darwin'
  add_languages('objcpp', 'objc')
  foundation = dependency('appleframeworks', modules: ['Foundation'])
  metal = dependency('appleframeworks', modules: ['Foundation', 'Metal'])
  bootstrap = shared_library('cache-bootstrap', '../../src/winemetal/unix/cache_bootstrap.m', dependencies: metal)
  test('cache-bootstrap', executable('cache-bootstrap-test', 'cache_bootstrap.mm', dependencies: metal),
       args: [bootstrap.full_path()], depends: [bootstrap], timeout: 30)
  test('error-ownership', executable('error-ownership', 'error_ownership.mm',
       include_directories: inc, dependencies: foundation))
endif
