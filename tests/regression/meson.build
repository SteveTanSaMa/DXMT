project('dxmt-regression', 'cpp', default_options: ['cpp_std=c++20', 'warning_level=2'])

inc = include_directories('../../src/util', '../../src/winemetal',
                          '../../include/native/windows', '../../include/native/directx')
threads = dependency('threads')
test('scheduler-lifetime', executable('scheduler-lifetime', 'scheduler_lifetime.cpp',
     include_directories: inc, dependencies: threads), timeout: 30)
