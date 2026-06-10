#pragma once

#include <string>

namespace huffcore {

bool is_high_entropy_extension(const std::string& extension);
bool is_zip_based_office_extension(const std::string& extension);

} // namespace huffcore
