#include "report.hpp"

#include <format>
#include <iterator>

namespace la {
namespace {

std::string ago(TimePoint now, TimePoint t) {
    using namespace std::chrono;
    auto m = duration_cast<minutes>(now - t).count();
    if (m < 60) return std::format("{}m ago", std::max<long long>(m, 0));
    return std::format("{}h ago", m / 60);
}

std::string snippet(const std::string& s, size_t max = 240) {
    std::string out;
    for (char ch : s) out += (ch == '\n' || ch == '\r') ? ' ' : ch;
    if (out.size() <= max) return out;
    size_t cut = max;
    while (cut > 0 && (static_cast<unsigned char>(out[cut]) & 0xC0) == 0x80) --cut;  // UTF-8 safe
    return out.substr(0, cut) + "...";
}

}  // namespace

std::string render_subject(const Report& r) {
    return std::format("LinkedIn daily summary {:%Y-%m-%d}: {} posts, {} profile views",
                       std::chrono::floor<std::chrono::days>(r.now), r.posts.size(), r.views.size());
}

std::string render_text(const Report& r) {
    std::string out;
    auto o = std::back_inserter(out);
    std::format_to(o, "LinkedIn daily summary - window {:%Y-%m-%d %H:%M} to {:%Y-%m-%d %H:%M} UTC\n\n",
                   std::chrono::floor<std::chrono::minutes>(r.since),
                   std::chrono::floor<std::chrono::minutes>(r.now));

    std::format_to(o, "== Profile views ({}) ==\n", r.views.size());
    if (r.views.empty()) out += "No profile views in this window.\n";
    for (const auto& v : r.views) {
        if (v.anonymous())
            std::format_to(o, "- Private viewer ({})\n", ago(r.now, v.viewed_at));
        else
            std::format_to(o, "- {} - {} ({}) {}\n", v.name, v.headline, ago(r.now, v.viewed_at),
                           v.profile_url);
    }

    if (r.digest) std::format_to(o, "\n== Digest ==\n{}\n", *r.digest);

    std::format_to(o, "\n== All posts from people you follow ({}) ==\n", r.posts.size());
    if (r.posts.empty()) out += "No new posts in this window.\n";
    for (const auto& p : r.posts)
        std::format_to(o, "\n* {} ({})\n  {}\n  {}\n", p.author, ago(r.now, p.posted_at),
                       snippet(p.text), p.url);
    return out;
}

}  // namespace la
