#include "aphelion/types.h"

namespace aphelion {

// Shared engine types are intentionally header-only PODs and enum contracts.
// This translation unit gives the shared library a stable object file for
// build systems and binding targets that expect one source per public header.

} // namespace aphelion
