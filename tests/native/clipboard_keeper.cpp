// Exercise the production nonblocking transfers without a desktop connection.
#define main keeper_main
#include "../../config/hypr/clipboard/native/keeper.cpp"
#undef main
#include <cassert>

void begin(const std::string& mime = "text/plain") {
    capture = std::make_unique<Capture>(); capture->chosen = mime;
}
void input(const std::string& bytes, const std::string& mime = "text/plain") {
    int pipefd[2]; assert(pipe2(pipefd, O_CLOEXEC | O_NONBLOCK) == 0);
    assert(write(pipefd[1], bytes.data(), bytes.size()) == ssize_t(bytes.size())); close(pipefd[1]);
    auto read = std::make_unique<Read>(); read->fd = pipefd[0]; read->mime = mime;
    capture->reads.push_back(std::move(read)); receive(*capture->reads.back());
}
int main() {
    std::signal(SIGPIPE, SIG_IGN);
    begin(); input(std::string("URL\n\0raw", 8));
    assert(capture && capture->reads[0]->bytes == std::string("URL\n\0raw", 8));
    assert(capture->reads[0]->fd == -1);
    input("<b>URL</b>", "text/html");
    assert(capture->reads[1]->bytes == "<b>URL</b>");
    // Selection clear/newer copy invalidates every in-flight representation.
    auto revision = generation; selection(nullptr, nullptr, nullptr);
    assert(!capture && generation == revision + 1);
    // Enforce both per-format and aggregate memory bounds before publishing.
    begin(); capture->size = LIMIT; input("too much", "text/html"); assert(!capture);
    begin();
    int readfds[2]; assert(pipe2(readfds, O_CLOEXEC | O_NONBLOCK) == 0);
    auto read = std::make_unique<Read>(); read->fd = readfds[0]; read->mime = "text/plain";
    read->bytes.assign(TEXT_LIMIT, 'x'); capture->reads.push_back(std::move(read));
    assert(write(readfds[1], "!", 1) == 1); close(readfds[1]); receive(*capture->reads[0]); assert(!capture);
    // Large pastes require multiple nonblocking writes and survive source exit.
    Source source{}; source.formats["text/plain"] = std::make_shared<const std::string>(200000, 'x');
    int fds[2]; assert(pipe2(fds, O_CLOEXEC | O_NONBLOCK) == 0);
    send(&source, nullptr, "text/plain", fds[1]); source.formats.clear();
    transmit(*writes.at(fds[1])); assert(writes.contains(fds[1]));
    std::string received; char chunk[8192];
    while (writes.contains(fds[1])) {
        for (ssize_t n; (n = ::read(fds[0], chunk, sizeof(chunk))) > 0;) received.append(chunk, n);
        transmit(*writes.at(fds[1]));
    }
    for (ssize_t n; (n = ::read(fds[0], chunk, sizeof(chunk))) > 0;) received.append(chunk, n);
    close(fds[0]); assert(received == std::string(200000, 'x'));
    // A cancelled paste must neither SIGPIPE the service nor leak its fd.
    source.formats["text/plain"] = std::make_shared<const std::string>("retained");
    assert(pipe2(fds, O_CLOEXEC | O_NONBLOCK) == 0);
    send(&source, nullptr, "text/plain", fds[1]); close(fds[0]); transmit(*writes.at(fds[1])); assert(writes.empty());
    // Unadvertised formats close immediately instead of serving unrelated data.
    assert(pipe2(fds, O_CLOEXEC | O_NONBLOCK) == 0);
    send(&source, nullptr, "text/html", fds[1]); assert(::read(fds[0], chunk, sizeof(chunk)) == 0); close(fds[0]);
    std::vector<int> held;
    for (size_t i = 0; i < MAX_WRITES + 1; ++i) {
        assert(pipe2(fds, O_CLOEXEC | O_NONBLOCK) == 0); held.push_back(fds[0]);
        send(&source, nullptr, "text/plain", fds[1]);
        if (i == MAX_WRITES) assert(::read(fds[0], chunk, sizeof(chunk)) == 0);
    }
    assert(writes.size() == MAX_WRITES); writes.clear(); for (int fd : held) close(fd);
    Offer offer{}; format(&offer, nullptr, "text/plain"); format(&offer, nullptr, "text/plain");
    assert(offer.formats.size() == 1);
    format(&offer, nullptr, std::string(256, 'x').c_str()); assert(offer.overflow);
    puts("PASS native clipboard transfers, bounds, cancellation and backpressure");
}
