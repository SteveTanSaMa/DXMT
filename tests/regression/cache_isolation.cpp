#include "../../src/dxmt/dxmt_cache_policy.hpp"
#include <cassert>

int main() {
  std::string selected;
  unsigned calls = 0;
  auto setter = [&](const std::string &path) { selected = path; ++calls; return true; };
  assert(dxmt::configureMetalCache("legacy/cache", "", "", false, false, false, setter));
  assert(selected == "legacy/cache" && calls == 1);
  assert(dxmt::configureMetalCache("legacy", "/test/metal", "/test/air", false, false, true, setter));
  assert(selected == "/test/metal" && calls == 2);
  assert(!dxmt::configureMetalCache("legacy", "", "/test/air", false, false, true, setter));
  assert(!dxmt::configureMetalCache("legacy", "/test/metal", "relative/air", false, false, true, setter));
  assert(!dxmt::configureMetalCache("legacy", "relative/metal", "/test/air", false, false, true, setter));
  assert(!dxmt::configureMetalCache("legacy", "/test/metal", "/test/air", false, true, true, setter));
  assert(calls == 2);
  auto failed = [](const std::string &) { return false; };
  assert(!dxmt::configureMetalCache("legacy", "/test/metal", "/test/air", false, false, true, failed));
  assert(dxmt::configureMetalCache("legacy", "", "", false, false, false, failed));
  assert(dxmt::configureMetalCache("legacy", "/test/metal", "", true, false, true, setter));
}
