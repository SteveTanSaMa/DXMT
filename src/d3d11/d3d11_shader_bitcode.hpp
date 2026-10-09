#pragma once

#include "airconv_public.h"

namespace dxmt {

// sm50_bitcode_t is a pointer on 64-bit and a pointer wrapper on WoW64.
// Keep the owner in that representation rather than converting to void*.
class CompiledBitcode {
public:
  explicit CompiledBitcode(sm50_bitcode_t bitcode) : bitcode_(bitcode) {}
  CompiledBitcode(const CompiledBitcode &) = delete;
  CompiledBitcode &operator=(const CompiledBitcode &) = delete;
  ~CompiledBitcode() {
    if (bitcode_)
      SM50DestroyBitcode(bitcode_);
  }

private:
  sm50_bitcode_t bitcode_;
};

} // namespace dxmt
