#include "../../src/d3d11/d3d11_shader_bitcode.hpp"
#include <cassert>
#include <stdexcept>

static unsigned destroyed = 0;
extern "C" void SM50DestroyBitcode(sm50_bitcode_t bitcode) {
  ++destroyed;
  delete static_cast<int *>(bitcode);
}
static void compile(bool library_failed, bool throw_on_cache_write) {
  auto bitcode = new int(42);
  dxmt::CompiledBitcode owned(bitcode);
  if (library_failed) return;
  if (throw_on_cache_write) throw std::runtime_error("cache write");
}
int main() {
  static_assert(!std::is_copy_constructible_v<dxmt::CompiledBitcode>);
  compile(true, false);
  assert(destroyed == 1);
  compile(false, false);
  assert(destroyed == 2);
  try { compile(false, true); } catch (const std::runtime_error &) {}
  assert(destroyed == 3);
  { dxmt::CompiledBitcode empty(nullptr); }
  assert(destroyed == 3);
}
