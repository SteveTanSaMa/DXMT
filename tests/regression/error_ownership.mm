#import <Foundation/Foundation.h>
#include "Metal.hpp"
#include <cassert>

static unsigned live_errors = 0;
static bool fail = true;
@interface TrackedError : NSError
@end
@implementation TrackedError
- (instancetype)init {
  self = [super initWithDomain:@"DXMTRegression" code:1 userInfo:nil];
  if (self) ++live_errors;
  return self;
}
- (void)dealloc {
  --live_errors;
  [super dealloc];
}
@end

extern "C" void NSObject_retain(obj_handle_t handle) { [(id)handle retain]; }
extern "C" void NSObject_release(obj_handle_t handle) { [(id)handle release]; }
static obj_handle_t result(obj_handle_t *error) {
  *error = fail ? (obj_handle_t)[[[TrackedError alloc] init] autorelease] : 0;
  return fail ? 0 : (obj_handle_t)[[NSObject alloc] init];
}
extern "C" obj_handle_t MTLDevice_newLibrary(obj_handle_t, obj_handle_t, obj_handle_t *error) {
  return result(error);
}
extern "C" obj_handle_t MTLDevice_newComputePipelineState(
    obj_handle_t, const WMTComputePipelineInfo *, obj_handle_t *error) { return result(error); }
extern "C" void MTLBinaryArchive_serialize(obj_handle_t, const char *, obj_handle_t *error) {
  auto object = result(error);
  NSObject_release(object);
}

int main() {
  WMT::Device device;
  WMT::Reference<WMT::Error> error;
  WMTComputePipelineInfo info{};
  // The wrapper must keep the borrowed NSError alive after its pool drains.
  @autoreleasepool {
    assert(!device.newLibrary(WMT::DispatchData{}, error));
    assert(error && live_errors == 1);
  }
  assert(error && live_errors == 1);
  @autoreleasepool {
    assert(!device.newComputePipelineState(info, error));
    assert(error && live_errors == 1); // old error released on replacement
  }
  assert(live_errors == 1);
  fail = false;
  @autoreleasepool {
    assert(device.newLibrary(WMT::DispatchData{}, error));
    assert(!error && live_errors == 0); // success clears the previous error
  }
  fail = true;
  @autoreleasepool { WMT::BinaryArchive{}.serialize("unused", error); }
  assert(error && live_errors == 1);
  error = nullptr;
  assert(live_errors == 0);
}
