#pragma once
#include <string>

namespace la {

struct SmtpConfig {
    std::string url;   // e.g. smtps://smtp.gmail.com:465
    std::string user;
    std::string pass;  // Gmail: an App Password, not the account password
    std::string from;
    std::string to;
};

std::string build_message(const SmtpConfig& cfg, const std::string& subject, const std::string& body);
void send_mail(const SmtpConfig& cfg, const std::string& subject, const std::string& body);

}  // namespace la
