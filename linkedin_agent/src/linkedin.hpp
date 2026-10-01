#pragma once
#include <nlohmann/json.hpp>

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "model.hpp"

namespace la {

// Session = cookies copied from a logged-in browser (DevTools > Application > Cookies).
// Headless password login is deliberately unsupported: LinkedIn answers it with
// CAPTCHA / e-mail PIN challenges, and keeping the password on disk is worse.
struct Session {
    std::string li_at;       // long-lived auth cookie (~1 year)
    std::string jsessionid;  // "ajax:123..." (quotes optional); doubles as CSRF token
};

class SessionExpired : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Activity IDs are Snowflake-style: the top 41 bits are ms since the Unix epoch.
std::optional<TimePoint> activity_time(std::string_view urn);

// Pure parsers over Voyager JSON (normalized or not); unit-tested against fixtures.
std::vector<Post> parse_feed(const nlohmann::json& doc);
std::vector<ProfileView> parse_profile_views(const nlohmann::json& doc);

struct FeedFilter {
    TimePoint since;
    bool include_network_activity = false;  // "X liked this" items from non-followed authors
};
std::vector<Post> filter_posts(std::vector<Post> posts, const FeedFilter& f);

// Thin client over LinkedIn's internal web API ("Voyager"). Undocumented: endpoints and
// shapes change without notice, and automated access is against LinkedIn's User Agreement.
// Use for your own account only, at human-like volume.
class LinkedInClient {
public:
    explicit LinkedInClient(Session s);

    void verify_session() const;  // throws SessionExpired
    std::vector<Post> recent_posts(TimePoint since, int max_pages) const;
    std::vector<ProfileView> profile_views() const;

private:
    nlohmann::json get_json(const std::string& path) const;
    Session s_;
    std::string csrf_;
};

}  // namespace la
