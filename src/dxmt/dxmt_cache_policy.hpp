#pragma once
#include <string>

namespace dxmt {

// Strict isolation is opt-in. Existing applications keep their fallback policy.
template <typename SetPath>
bool configureMetalCache(const std::string &default_path, const std::string &override_path,
                         const std::string &air_path, bool air_disabled,
                         bool use_system_default, bool require_isolation, SetPath set_path) {
  if (use_system_default)
    return !require_isolation;
  if (!override_path.empty() && override_path.front() != '/')
    return false;
  if (require_isolation && (override_path.empty() ||
      (!air_disabled && (air_path.empty() || air_path.front() != '/'))))
    return false;
  bool configured = set_path(override_path.empty() ? default_path : override_path);
  return configured || !require_isolation;
}

} // namespace dxmt
