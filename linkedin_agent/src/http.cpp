#include "http.hpp"

#include <curl/curl.h>

#include <memory>

namespace la {
namespace {

struct CurlDeleter { void operator()(CURL* c) const noexcept { curl_easy_cleanup(c); } };
struct SlistDeleter { void operator()(curl_slist* s) const noexcept { curl_slist_free_all(s); } };
using CurlPtr = std::unique_ptr<CURL, CurlDeleter>;
using SlistPtr = std::unique_ptr<curl_slist, SlistDeleter>;

size_t write_cb(char* ptr, size_t size, size_t n, void* user) {
    static_cast<std::string*>(user)->append(ptr, size * n);
    return size * n;
}

HttpResponse perform(const std::string& url, const std::string* post_body, const RequestOptions& opt) {
    CurlPtr curl{curl_easy_init()};
    if (!curl) throw HttpError("curl_easy_init failed");

    SlistPtr headers;
    for (const auto& h : opt.headers) {
        curl_slist* next = curl_slist_append(headers.get(), h.c_str());
        if (!next) throw HttpError("curl_slist_append failed");
        headers.release();
        headers.reset(next);
    }

    HttpResponse resp;
    CURL* c = curl.get();
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, headers.get());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &resp.body);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, static_cast<long>(opt.timeout.count()));
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 0L);  // a redirect means the session expired
    curl_easy_setopt(c, CURLOPT_ACCEPT_ENCODING, "");  // let curl negotiate gzip/br
    if (!opt.cookie.empty()) curl_easy_setopt(c, CURLOPT_COOKIE, opt.cookie.c_str());
    if (post_body) {
        curl_easy_setopt(c, CURLOPT_POSTFIELDS, post_body->data());
        curl_easy_setopt(c, CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(post_body->size()));
    }

    if (CURLcode rc = curl_easy_perform(c); rc != CURLE_OK)
        throw HttpError(std::string("HTTP request failed: ") + curl_easy_strerror(rc));
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &resp.status);
    return resp;
}

}  // namespace

CurlGlobal::CurlGlobal() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) throw HttpError("curl_global_init failed");
}
CurlGlobal::~CurlGlobal() { curl_global_cleanup(); }

HttpResponse http_get(const std::string& url, const RequestOptions& opt) { return perform(url, nullptr, opt); }

HttpResponse http_post(const std::string& url, const std::string& body, const RequestOptions& opt) {
    return perform(url, &body, opt);
}

}  // namespace la
