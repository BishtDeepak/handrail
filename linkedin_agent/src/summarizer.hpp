#pragma once
#include <optional>
#include <string>
#include <vector>

#include "model.hpp"

namespace la {

struct ClaudeConfig {
    std::string api_key;
    std::string model = "claude-opus-5-5";
    std::string effort = "medium";
};

// Asks Claude for a themed digest of the posts. Returns nullopt on refusal/empty output so
// the caller can fall back to the plain listing; throws HttpError on transport/API errors.
std::optional<std::string> summarize_posts(const ClaudeConfig& cfg, const std::vector<Post>& posts);

}  // namespace la
