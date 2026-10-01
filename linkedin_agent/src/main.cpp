// linkedin_agent: daily summary of followed profiles' posts + profile views, sent by e-mail.
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>

#include "http.hpp"
#include "linkedin.hpp"
#include "mailer.hpp"
#include "report.hpp"
#include "summarizer.hpp"

namespace {

struct Args {
    int hours = 24;
    int max_pages = 10;
    bool dry_run = false;  // print instead of e-mailing
    bool include_network_activity = false;
    bool no_llm = false;
    std::string feed_json, views_json;  // offline mode: read Voyager JSON from files
    std::optional<std::int64_t> now_ms;  // pin "now" (offline/reproducible runs)
};

[[noreturn]] void usage(int rc) {
    std::cerr << "usage: linkedin_agent [--hours N] [--max-pages N] [--dry-run] [--no-llm]\n"
                 "                      [--include-network-activity]\n"
                 "                      [--feed-json FILE --views-json FILE [--now-ms MS]]\n"
                 "env: LI_AT, LI_JSESSIONID, ANTHROPIC_API_KEY (optional),\n"
                 "     SMTP_URL, SMTP_USER, SMTP_PASS, MAIL_FROM, MAIL_TO\n";
    std::exit(rc);
}

Args parse_args(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; ++i) {
        std::string_view k = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) usage(2);
            return argv[++i];
        };
        if (k == "--hours") a.hours = std::stoi(next());
        else if (k == "--max-pages") a.max_pages = std::stoi(next());
        else if (k == "--dry-run") a.dry_run = true;
        else if (k == "--no-llm") a.no_llm = true;
        else if (k == "--include-network-activity") a.include_network_activity = true;
        else if (k == "--feed-json") a.feed_json = next();
        else if (k == "--views-json") a.views_json = next();
        else if (k == "--now-ms") a.now_ms = std::stoll(next());
        else if (k == "-h" || k == "--help") usage(0);
        else usage(2);
    }
    return a;
}

std::string env(const char* name, bool required = true) {
    const char* v = std::getenv(name);
    if (!v || !*v) {
        if (required) throw std::runtime_error(std::string("missing env var ") + name);
        return {};
    }
    return v;
}

nlohmann::json load_json(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("cannot open " + path);
    return nlohmann::json::parse(f);
}

}  // namespace

int main(int argc, char** argv) try {
    using namespace la;
    const Args args = parse_args(argc, argv);
    CurlGlobal curl_global;

    const TimePoint now = args.now_ms ? TimePoint{std::chrono::milliseconds{*args.now_ms}} : Clock::now();
    const TimePoint since = now - std::chrono::hours{args.hours};

    std::vector<Post> posts;
    std::vector<ProfileView> views;
    if (!args.feed_json.empty() || !args.views_json.empty()) {
        if (!args.feed_json.empty()) posts = parse_feed(load_json(args.feed_json));
        if (!args.views_json.empty()) views = parse_profile_views(load_json(args.views_json));
    } else {
        LinkedInClient li{Session{env("LI_AT"), env("LI_JSESSIONID")}};
        li.verify_session();
        posts = li.recent_posts(since, args.max_pages);
        views = li.profile_views();
    }

    Report r{now, since, {}, filter_posts(std::move(posts), {since, args.include_network_activity}), {}};
    std::erase_if(views, [&](const ProfileView& v) { return v.viewed_at < since; });
    r.views = std::move(views);

    if (auto key = env("ANTHROPIC_API_KEY", false); !key.empty() && !args.no_llm) {
        try {
            r.digest = summarize_posts(ClaudeConfig{key}, r.posts);
        } catch (const std::exception& e) {
            std::cerr << "warn: digest skipped: " << e.what() << '\n';  // plain listing still goes out
        }
    }

    const std::string subject = render_subject(r), body = render_text(r);
    if (args.dry_run) {
        std::cout << "Subject: " << subject << "\n\n" << body;
        return 0;
    }
    send_mail(SmtpConfig{env("SMTP_URL"), env("SMTP_USER"), env("SMTP_PASS"), env("MAIL_FROM"),
                         env("MAIL_TO")},
              subject, body);
    std::cerr << "sent: " << subject << '\n';
    return 0;
} catch (const la::SessionExpired& e) {
    std::cerr << "error: " << e.what() << '\n';
    return 3;
} catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << '\n';
    return 1;
}
