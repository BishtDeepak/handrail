#include "linkedin.hpp"

#include <algorithm>
#include <charconv>
#include <iostream>
#include <random>
#include <set>
#include <thread>
#include <unordered_map>

#include "http.hpp"

namespace la {
namespace {

using nlohmann::json;
constexpr std::string_view kBase = "https://www.linkedin.com/voyager/api";
constexpr std::string_view kActivityPrefix = "urn:li:activity:";

// Safe nested lookup: returns nullptr instead of throwing on a missing key / wrong type.
const json* at(const json& j, std::initializer_list<std::string_view> path) {
    const json* cur = &j;
    for (auto key : path) {
        if (!cur->is_object()) return nullptr;
        auto it = cur->find(key);
        if (it == cur->end() || it->is_null()) return nullptr;
        cur = &*it;
    }
    return cur;
}

std::string str(const json& j, std::initializer_list<std::string_view> path) {
    const json* v = at(j, path);
    return v && v->is_string() ? v->get<std::string>() : std::string{};
}

// Visit every object in the document (top-level "data", "elements", "included", ...).
template <class F>
void for_each_object(const json& j, F&& f) {
    if (j.is_object()) {
        f(j);
        for (const auto& [_, v] : j.items()) for_each_object(v, f);
    } else if (j.is_array()) {
        for (const auto& v : j) for_each_object(v, f);
    }
}

std::optional<Post> to_post(const json& u) {
    std::string urn = str(u, {"updateMetadata", "urn"});
    auto ts = activity_time(urn);
    if (!ts) return std::nullopt;  // sponsored content, aggregated modules, etc.

    Post p;
    p.activity_urn = std::move(urn);
    p.posted_at = *ts;
    p.author = str(u, {"actor", "name", "text"});
    p.author_headline = str(u, {"actor", "description", "text"});
    p.author_url = str(u, {"actor", "navigationContext", "actionTarget"});
    p.text = str(u, {"commentary", "text", "text"});
    p.url = "https://www.linkedin.com/feed/update/" + p.activity_urn + "/";
    std::string actor_urn = str(u, {"actor", "urn"});
    p.is_company = actor_urn.find(":company:") != std::string::npos;
    p.via_network_activity = at(u, {"header"}) != nullptr;
    return p;
}

// Normalized responses reference entities as {"*field": "<entityUrn>"}; index them.
using UrnIndex = std::unordered_map<std::string, const json*>;

UrnIndex index_included(const json& doc) {
    UrnIndex idx;
    if (const json* inc = at(doc, {"included"}); inc && inc->is_array())
        for (const auto& e : *inc)
            if (auto u = str(e, {"entityUrn"}); !u.empty()) idx.emplace(std::move(u), &e);
    return idx;
}

// Depth-limited search for a mini-profile (has firstName) under `j`, following '*' refs.
const json* find_profile(const json& j, const UrnIndex& idx, int depth = 0) {
    if (depth > 8) return nullptr;
    if (j.is_object()) {
        if (j.contains("firstName")) return &j;
        for (const auto& [k, v] : j.items()) {
            if (!k.empty() && k.front() == '*' && v.is_string()) {
                if (auto it = idx.find(v.get<std::string>()); it != idx.end())
                    if (auto* p = find_profile(*it->second, idx, depth + 1)) return p;
            } else if (auto* p = find_profile(v, idx, depth + 1)) {
                return p;
            }
        }
    } else if (j.is_array()) {
        for (const auto& v : j)
            if (auto* p = find_profile(v, idx, depth + 1)) return p;
    }
    return nullptr;
}

}  // namespace

std::optional<TimePoint> activity_time(std::string_view urn) {
    if (!urn.starts_with(kActivityPrefix)) return std::nullopt;
    urn.remove_prefix(kActivityPrefix.size());
    std::uint64_t id{};
    auto [ptr, ec] = std::from_chars(urn.data(), urn.data() + urn.size(), id);
    if (ec != std::errc{} || ptr != urn.data() + urn.size()) return std::nullopt;
    return TimePoint{std::chrono::milliseconds{static_cast<std::int64_t>(id >> 22)}};
}

std::vector<Post> parse_feed(const json& doc) {
    std::vector<Post> out;
    std::set<std::string> seen;
    for_each_object(doc, [&](const json& o) {
        if (!at(o, {"updateMetadata"})) return;
        if (auto p = to_post(o); p && seen.insert(p->activity_urn).second) out.push_back(std::move(*p));
    });
    return out;
}

std::vector<ProfileView> parse_profile_views(const json& doc) {
    const UrnIndex idx = index_included(doc);
    std::vector<ProfileView> out;
    std::set<std::pair<std::string, std::int64_t>> seen;

    for_each_object(doc, [&](const json& o) {
        const json* va = at(o, {"viewedAt"});
        if (!va || !va->is_number_integer()) return;
        ProfileView v;
        v.viewed_at = TimePoint{std::chrono::milliseconds{va->get<std::int64_t>()}};
        if (const json* p = find_profile(o, idx)) {
            v.name = str(*p, {"firstName"});
            if (auto last = str(*p, {"lastName"}); !last.empty()) v.name += ' ' + last;
            v.headline = str(*p, {"occupation"});
            if (auto id = str(*p, {"publicIdentifier"}); !id.empty())
                v.profile_url = "https://www.linkedin.com/in/" + id + "/";
        }
        if (seen.emplace(v.name, va->get<std::int64_t>()).second) out.push_back(std::move(v));
    });
    std::ranges::sort(out, std::greater{}, &ProfileView::viewed_at);
    return out;
}

std::vector<Post> filter_posts(std::vector<Post> posts, const FeedFilter& f) {
    std::erase_if(posts, [&](const Post& p) {
        return p.posted_at < f.since || (p.via_network_activity && !f.include_network_activity);
    });
    std::ranges::sort(posts, std::greater{}, &Post::posted_at);
    return posts;
}

LinkedInClient::LinkedInClient(Session s) : s_(std::move(s)) {
    std::erase(s_.jsessionid, '"');
    csrf_ = s_.jsessionid;
}

json LinkedInClient::get_json(const std::string& path) const {
    RequestOptions opt;
    opt.cookie = "li_at=" + s_.li_at + "; JSESSIONID=\"" + s_.jsessionid + "\"";
    opt.headers = {
        "csrf-token: " + csrf_,
        "accept: application/vnd.linkedin.normalized+json+2.1",
        "x-restli-protocol-version: 2.0.0",
        "x-li-lang: en_US",
        "user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36",
    };
    auto r = http_get(std::string(kBase) + path, opt);
    if (r.status == 401 || r.status == 403 || (r.status >= 300 && r.status < 400))
        throw SessionExpired("LinkedIn rejected the session (HTTP " + std::to_string(r.status) +
                             "); copy fresh li_at/JSESSIONID cookies from your browser");
    if (r.status != 200)
        throw HttpError("GET " + path + " -> HTTP " + std::to_string(r.status));
    return json::parse(r.body);
}

void LinkedInClient::verify_session() const { (void)get_json("/me"); }

std::vector<Post> LinkedInClient::recent_posts(TimePoint since, int max_pages) const {
    constexpr int kCount = 50;
    std::mt19937 rng{std::random_device{}()};
    std::uniform_int_distribution<int> jitter_ms{1500, 4000};

    std::vector<Post> all;
    for (int page = 0; page < max_pages; ++page) {
        auto doc = get_json("/feed/updatesV2?q=feed&moduleKey=home-feed:desktop&sortOrder=RECENT"
                            "&count=" + std::to_string(kCount) + "&start=" + std::to_string(page * kCount));
        auto posts = parse_feed(doc);
        if (posts.empty()) break;
        // Feed is "mostly" chronological with RECENT; stop once the whole page is stale.
        bool any_fresh = std::ranges::any_of(posts, [&](const Post& p) { return p.posted_at >= since; });
        std::ranges::move(posts, std::back_inserter(all));
        if (!any_fresh) break;
        std::this_thread::sleep_for(std::chrono::milliseconds{jitter_ms(rng)});  // stay human-paced
    }
    return all;
}

std::vector<ProfileView> LinkedInClient::profile_views() const {
    return parse_profile_views(get_json("/identity/wvmpCards"));
}

}  // namespace la
