#pragma once
#include <optional>
#include <string>
#include <vector>

#include "model.hpp"

namespace la {

struct Report {
    TimePoint now;
    TimePoint since;
    std::vector<ProfileView> views;  // already filtered to the window
    std::vector<Post> posts;         // already filtered to the window
    std::optional<std::string> digest;  // Claude digest, if available
};

std::string render_subject(const Report& r);
std::string render_text(const Report& r);

}  // namespace la
