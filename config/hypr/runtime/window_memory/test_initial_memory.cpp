#include "initial_memory.hpp"
#include <cassert>
#include <iostream>

int main(int argc, char** argv) {
    using namespace InitialMemory;
    if (argc == 4 && std::string(argv[1]) == "read") return read(argv[2], argv[3]) ? 0 : 2;
    if (argc == 7 && std::string(argv[1]) == "identity") {
        std::cout << identity(argv[2], argv[3], std::string(argv[4]) == "1",
                             std::string(argv[5]) == "1", std::string(argv[6]) == "1");
        return 0;
    }
    assert(argc == 2);
    const auto record = read(argv[1], std::string(32, 'a'));
    assert(record && record->normalSize && record->position);
    assert(record->floating && record->fullscreen == 1 && record->clientFullscreen == 1);
    assert(record->normalSize->w == 850 && record->normalSize->h == 600);
    assert(!read(argv[1], "missing"));
    assert(!read(argv[1], std::string(32, 'b'))); // malformed record cannot become geometry
    assert(!read(std::string(argv[1]) + "-missing", std::string(32, 'a')));
    const auto legacy = read(argv[1], std::string(32, 'c'));
    assert(legacy && !legacy->normalSize); // never turn a maximized size into a normal one
    auto restore = plan(*record, false, false);
    assert(restore.restoreMode && restore.floating);
    for (bool floating : {false, true}) {
        restore = plan(*record, true, floating);
        assert(!restore.restoreMode && restore.floating == floating);
    }
    auto modeOnly = *record; modeOnly.modeSaved = false;
    assert(!plan(modeOnly, false, false).restoreMode && !plan(modeOnly, false, false).floating);
    auto rect = fit(*record, {-1920, 240, 1920, 1040}, {-1800, 340, 800, 600});
    assert(rect.x == -1800 && rect.y == 340 && rect.w == 850 && rect.h == 600);
    rect = fit(*record, {0, -460, 960, 500}, {0, 0, 800, 600});
    assert(rect.x == 110 && rect.y == -444 && rect.w == 850 && rect.h == 484);
    rect = fit(*record, {0, 40, 1920, 1040}, {0, 40, 800, 600}, {900, 650}, {1000, 700});
    assert(rect.w == 900 && rect.h == 650);
    auto edge = *record; edge.position = std::array<int,2>{0, 0};
    rect = fit(edge, {0, 40, 1920, 1040}, {0, 40, 800, 600}, {}, {}, false, {2, 32, 2, 2});
    assert(rect.x == 2 && rect.y == 72); // keep the titlebar above content on-screen
    rect = fit(*record, {0, 40, 500, 300}, {0, 40, 800, 600}, {}, {}, true);
    assert(rect.w == 800 && rect.h == 600 && rect.x == 0 && rect.y == 40);
    auto tiny = *record; tiny.normalSize = Size{1, 2};
    rect = fit(tiny, {0, 0, 1920, 1080}, {0, 0, 800, 600});
    assert(rect.w == 1 && rect.h == 2);
    std::cout << "Initial geometry, ownership, mode priority, bounds and legacy state passed\n";
}
