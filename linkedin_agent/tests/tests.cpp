// Minimal self-contained tests (no network): parsers, freshness filter, rendering, mail framing.
#include <fstream>
#include <iostream>

#include "linkedin.hpp"
#include "mailer.hpp"
#include "report.hpp"

namespace {

int failures = 0;
#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            ++failures;                                                          \
            std::cerr << __FILE__ << ':' << __LINE__ << ": CHECK(" #cond ")\n"; \
        }                                                                        \
    } while (0)

using namespace la;
using namespace std::chrono;

const TimePoint kNow{milliseconds{1790856000000}};  // 2026-10-01T12:00:00Z (matches fixtures)

nlohmann::json load(const char* name) {
    std::ifstream f(std::string(LA_FIXTURES) + "/" + name);
    return nlohmann::json::parse(f);
}

void test_activity_time() {
    const std::uint64_t ms = 1790856000000;
    auto t = activity_time("urn:li:activity:" + std::to_string(ms << 22 | 12345));
    CHECK(t && *t == TimePoint{milliseconds{ms}});
    CHECK(!activity_time("urn:li:sponsoredContent:1"));
    CHECK(!activity_time("urn:li:activity:12x"));
    CHECK(!activity_time("urn:li:activity:"));
}

void test_feed() {
    auto all = parse_feed(load("feed.json"));
    CHECK(all.size() == 4);  // sponsored dropped, duplicate collapsed

    auto fresh = filter_posts(all, {kNow - hours{24}});
    CHECK(fresh.size() == 2);
    CHECK(fresh[0].author == "Alice Chen");  // newest first
    CHECK(fresh[1].is_company);
    CHECK(fresh[0].url.starts_with("https://www.linkedin.com/feed/update/urn:li:activity:"));

    auto with_net = filter_posts(all, {kNow - hours{24}, true});
    CHECK(with_net.size() == 3);
}

void test_views() {
    auto views = parse_profile_views(load("views.json"));
    CHECK(views.size() == 3);
    CHECK(views[0].name == "Dana Wu");
    CHECK(views[0].profile_url == "https://www.linkedin.com/in/danawu/");
    CHECK(views[1].anonymous());
    CHECK(views[2].name == "Eve Old");
}

void test_render_and_mail() {
    Report r{kNow, kNow - hours{24}, {}, filter_posts(parse_feed(load("feed.json")), {kNow - hours{24}}), {}};
    r.views = parse_profile_views(load("views.json"));
    std::erase_if(r.views, [&](const ProfileView& v) { return v.viewed_at < r.since; });

    auto subject = render_subject(r);
    CHECK(subject == "LinkedIn daily summary 2026-10-01: 2 posts, 2 profile views");
    auto body = render_text(r);
    CHECK(body.find("Dana Wu - Staff Engineer at Example (4h ago)") != std::string::npos);
    CHECK(body.find("Private viewer (6h ago)") != std::string::npos);
    CHECK(body.find("Raft vs Paxos in production: lessons learned.") != std::string::npos);
    CHECK(body.find("Stale post") == std::string::npos);

    auto msg = build_message({"smtps://x", "u", "p", "me@x", "you@y"}, subject, "a\nb\r\nc");
    CHECK(msg.find("To: you@y\r\n") != std::string::npos);
    CHECK(msg.find("\r\n\r\na\r\nb\r\nc\r\n") != std::string::npos);
}

}  // namespace

int main() {
    test_activity_time();
    test_feed();
    test_views();
    test_render_and_mail();
    std::cout << (failures ? "FAILED: " : "OK ") << failures << '\n';
    return failures ? 1 : 0;
}
