// Optional MiPlay launch helper. Loaded by dyld before Wine enters the game.
// The normal five-component renderer does not depend on this library.
#import <Foundation/Foundation.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern void MTLSetShaderCachePath(NSString *path);
extern NSString *MTLGetShaderCachePath(void);

__attribute__((constructor)) static void initialize_isolated_metal_cache(void) {
  const char *strict = getenv("DXMT_REQUIRE_ISOLATED_CACHE");
  if (!strict || strcmp(strict, "1") != 0)
    return;
  @autoreleasepool {
    const char *value = getenv("DXMT_METAL_CACHE_PATH");
    NSString *path = value ? [NSString stringWithUTF8String:value] : nil;
    NSError *error = nil;
    if (![path hasPrefix:@"/"] ||
        ![[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES
                                                   attributes:nil error:&error]) {
      fprintf(stderr, "[dxmt-cache-bootstrap] Invalid/unwritable isolated cache path\n");
      _exit(78);
    }
    // Do not call the getter first: its first access also fixes the cache path.
    MTLSetShaderCachePath(path);
    NSString *actual = MTLGetShaderCachePath();
    if (![actual isEqualToString:path]) {
      fprintf(stderr, "[dxmt-cache-bootstrap] Cache isolation rejected: requested=%s actual=%s\n",
              path.UTF8String, actual ? actual.UTF8String : "(nil)");
      _exit(78);
    }
    fprintf(stderr, "[dxmt-cache-bootstrap] Isolated Metal cache configured\n");
  }
}
