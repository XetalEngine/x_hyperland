// SPDX-License-Identifier: GPL-2.0-or-later
#include "math.hpp"
#include <cassert>
#include <iostream>
int main() {
    using namespace Cube;
    std::vector<Workspace> all = {{1, 10}, {2, 20}, {3, 10}, {-1337, 20}, {-99, 10, true}};
    assert((faces(all, 10, 1) == std::vector<int64_t>{1, 3, 0, 0}));
    assert((faces(all, 20, 2) == std::vector<int64_t>{-1337, 2, 0, 0}));
    assert(unusedID(all) == 4);
    for (int n = 4; n <= 128; n++) {
        assert(std::isfinite(distance(n)) && distance(n) > 0);
        for (int face = 0; face < n; face++)
            for (int turns = -20; turns < 20; turns++) {
                double angle = turns * (2 * PI / n);
                assert(selected(angle, face, n) == ((face - turns) % n + n) % n);
                assert(std::abs(snap(angle + .01, n) - angle) < 1e-8);
            }
    }
    assert(std::abs(distance(4) - .5) < 1e-8);
    assert(std::abs(radius(4) - std::sqrt(.5)) < 1e-8);
    auto r = rotate({0, 0, .5}, PI / 2, 0);
    assert(std::abs(r.x - .5) < 1e-8 && std::abs(r.z) < 1e-8);
    for (int count = 1; count < 500; count++) {
        double base = baseScale(count, 60, 10);
        assert(base >= .6 && base <= 1);
        double previous = base;
        for (int rank = 0; rank < count; rank++) {
            double scale = windowScale(rank, count, base);
            assert(scale >= previous && scale <= 1.000001);
            previous = scale;
            assert(thickness(1, count, base) <= scale - base + .000001);
        }
        assert(std::abs(previous - 1) < 1e-8);
    }
    assert(smooth(-1) == 0 && smooth(2) == 1 && smooth(.5) == .5);
    std::cout << "Per-monitor faces, selection, Compiz geometry and 3D spacing: PASS\n";
}
