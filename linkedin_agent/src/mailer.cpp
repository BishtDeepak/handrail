#include "mailer.hpp"

#include <curl/curl.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <format>
#include <memory>
#include <string_view>

#include "http.hpp"

namespace la {
namespace {

size_t read_cb(char* buf, size_t size, size_t n, void* user) {
    auto* sv = static_cast<std::string_view*>(user);
    size_t len = std::min(size * n, sv->size());
    std::memcpy(buf, sv->data(), len);
    sv->remove_prefix(len);
    return len;
}

std::string to_crlf(std::string_view in) {
    std::string out;
    out.reserve(in.size() + in.size() / 40);
    for (size_t i = 0; i < in.size(); ++i) {
        if (in[i] == '\n' && (i == 0 || in[i - 1] != '\r')) out += '\r';
        out += in[i];
    }
    return out;
}

}  // namespace

std::string build_message(const SmtpConfig& cfg, const std::string& subject, const std::string& body) {
    auto now = std::chrono::floor<std::chrono::seconds>(std::chrono::system_clock::now());
    return std::format("Date: {:%a, %d %b %Y %H:%M:%S} +0000\r\n"
                       "From: {}\r\nTo: {}\r\nSubject: {}\r\n"
                       "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\n"
                       "Content-Transfer-Encoding: 8bit\r\n\r\n{}\r\n",
                       now, cfg.from, cfg.to, subject, to_crlf(body));
}

void send_mail(const SmtpConfig& cfg, const std::string& subject, const std::string& body) {
    const std::string msg = build_message(cfg, subject, body);
    std::string_view cursor = msg;

    std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl{curl_easy_init(), curl_easy_cleanup};
    if (!curl) throw HttpError("curl_easy_init failed");
    std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> rcpt{
        curl_slist_append(nullptr, ("<" + cfg.to + ">").c_str()), curl_slist_free_all};

    CURL* c = curl.get();
    const std::string from = "<" + cfg.from + ">";
    curl_easy_setopt(c, CURLOPT_URL, cfg.url.c_str());
    curl_easy_setopt(c, CURLOPT_USE_SSL, static_cast<long>(CURLUSESSL_ALL));
    curl_easy_setopt(c, CURLOPT_USERNAME, cfg.user.c_str());
    curl_easy_setopt(c, CURLOPT_PASSWORD, cfg.pass.c_str());
    curl_easy_setopt(c, CURLOPT_MAIL_FROM, from.c_str());
    curl_easy_setopt(c, CURLOPT_MAIL_RCPT, rcpt.get());
    curl_easy_setopt(c, CURLOPT_READFUNCTION, read_cb);
    curl_easy_setopt(c, CURLOPT_READDATA, &cursor);
    curl_easy_setopt(c, CURLOPT_UPLOAD, 1L);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 60L);

    if (CURLcode rc = curl_easy_perform(c); rc != CURLE_OK)
        throw HttpError(std::string("SMTP send failed: ") + curl_easy_strerror(rc));
}

}  // namespace la
