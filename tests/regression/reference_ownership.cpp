#include "Metal.hpp"
#include <cassert>
#include <unordered_map>
#include <utility>

static std::unordered_map<obj_handle_t, unsigned> refs;
static unsigned releases = 0;
extern "C" void NSObject_retain(obj_handle_t handle) {
  if (!handle) return;
  auto iter = refs.find(handle);
  // A retain after the final release is a use-after-free, even if handle values match.
  assert(iter != refs.end());
  ++iter->second;
}
extern "C" void NSObject_release(obj_handle_t handle) {
  if (!handle) return;
  auto iter = refs.find(handle);
  assert(iter != refs.end() && iter->second);
  ++releases;
  if (!--iter->second) refs.erase(iter);
}
static obj_handle_t make_object() {
  static obj_handle_t next = 1;
  refs.emplace(next, 1);
  return next++;
}

int main() {
  static_assert(std::is_nothrow_move_constructible_v<WMT::Reference<WMT::Object>>);
  static_assert(std::is_nothrow_move_assignable_v<WMT::Reference<WMT::Object>>);
  {
    WMT::Reference<WMT::Object> value(make_object());
    auto original = value.handle;
    auto &alias = value;
    value = alias;
    assert(value.handle == original && refs.at(original) == 1);
    value = WMT::Object{original};
    assert(refs.at(original) == 1);
    value = std::move(alias);
    assert(value.handle == original && refs.at(original) == 1);
    WMT::Reference<WMT::Object> copy(value);
    assert(refs.at(original) == 2);
    value = std::move(copy); // two owners of the same handle
    assert(!copy && refs.at(original) == 1);
    WMT::Reference<WMT::Object> moved(std::move(value));
    assert(!value && moved.handle == original);
    WMT::Reference<WMT::Object> replacement(make_object());
    auto other = replacement.handle;
    replacement = std::move(moved);
    assert(!moved && !refs.contains(other));
    replacement = nullptr;
    assert(!replacement && !refs.contains(original));
    WMT::Reference<WMT::Object> empty;
    empty = replacement;
    empty = std::move(replacement);
  }
  assert(refs.empty() && releases > 0);
}
