#pragma once
#include <chrono>
#include <stdexcept>
#include <string>
#include <vector>

namespace la {

struct HttpResponse {
    long status = 0;
    std::string body;
};

class HttpError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// RAII for curl_global_init / curl_global_cleanup; create exactly one in main().
class CurlGlobal {
public:
    CurlGlobal();
    ~CurlGlobal();
    CurlGlobal(const CurlGlobal&) = delete;
    CurlGlobal& operator=(const CurlGlobal&) = delete;
};

struct RequestOptions {
    std::vector<std::string> headers;
    std::string cookie;
    std::chrono::seconds timeout{60};
};

HttpResponse http_get(const std::string& url, const RequestOptions& opt);
HttpResponse http_post(const std::string& url, const std::string& body, const RequestOptions& opt);

}  // namespace la
