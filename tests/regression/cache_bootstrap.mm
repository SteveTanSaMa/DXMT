#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <cassert>
#include <cstdio>
extern "C" NSString *MTLGetShaderCachePath(void);

int main(int argc, const char **argv) {
  @autoreleasepool {
    if (argc == 3 && strcmp(argv[1], "child") == 0) {
      NSString *expected = [NSString stringWithUTF8String:argv[2]];
      // Initial getter and device creation must both see the injected path.
      assert([MTLGetShaderCachePath() isEqualToString:expected]);
      NSArray *devices = MTLCopyAllDevices();
      assert([MTLGetShaderCachePath() isEqualToString:expected]);
      [devices release];
      return 0;
    }
    assert(argc == 2);
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *path = [directory stringByAppendingPathComponent:@"Metal cache 测试"];
    for (NSString *value in @[path, @"relative", @""]) {
      NSTask *task = [[[NSTask alloc] init] autorelease];
      task.executableURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[0]]];
      task.arguments = @[@"child", path];
      NSMutableDictionary *env = [NSProcessInfo.processInfo.environment mutableCopy];
      env[@"DYLD_INSERT_LIBRARIES"] = [NSString stringWithUTF8String:argv[1]];
      env[@"DXMT_REQUIRE_ISOLATED_CACHE"] = @"1";
      env[@"DXMT_METAL_CACHE_PATH"] = value;
      task.environment = env;
      [env release];
      NSError *error = nil;
      assert([task launchAndReturnError:&error]);
      [task waitUntilExit];
      assert(task.terminationStatus == ([value isEqualToString:path] ? 0 : 78));
    }
    [[NSFileManager defaultManager] removeItemAtPath:directory error:nil];
  }
}
