#pragma once
#include <chrono>
#include <string>

namespace la {

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;

struct Post {
    std::string activity_urn;     // urn:li:activity:<id>
    std::string author;
    std::string author_headline;
    std::string author_url;
    std::string text;
    std::string url;              // permalink
    TimePoint posted_at{};
    bool is_company = false;
    bool via_network_activity = false;  // surfaced because a connection liked/commented
};

struct ProfileView {
    std::string name;             // empty when the viewer is private/anonymous
    std::string headline;
    std::string profile_url;
    TimePoint viewed_at{};
    bool anonymous() const { return name.empty(); }
};

}  // namespace la
