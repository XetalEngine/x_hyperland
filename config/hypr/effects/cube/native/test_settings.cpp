// SPDX-License-Identifier: GPL-2.0-or-later
#include "settings.hpp"
#include <iostream>

int main(int argc, char **argv) {
    if (argc != 2)
        return 2;
    try {
        auto s = Cube::readSettings(argv[1]);
        std::cout << s.skyMode << ' ' << s.skyMotion << ' ' << s.skySpeed << ' ' << s.previewFps << '\n';
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
