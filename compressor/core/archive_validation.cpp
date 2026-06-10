#include "archive_validation.h"
#include <algorithm>

namespace huffcore {

static const std::string ZIP_OFFICE_EXTENSIONS[] = {".docx", ".pptx", ".xlsx"};
static const std::string HIGH_ENTROPY_EXTENSIONS[] = {
    ".zip", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".gif",
    ".mp4", ".mp3", ".pdf"
};

bool is_high_entropy_extension(const std::string& extension) {
    std::string lower = extension;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    for (const auto& ext : HIGH_ENTROPY_EXTENSIONS) {
        if (lower == ext) {
            return true;
        }
    }
    return false;
}

bool is_zip_based_office_extension(const std::string& extension) {
    std::string lower = extension;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    for (const auto& ext : ZIP_OFFICE_EXTENSIONS) {
        if (lower == ext) {
            return true;
        }
    }
    return false;
}

} // namespace huffcore
