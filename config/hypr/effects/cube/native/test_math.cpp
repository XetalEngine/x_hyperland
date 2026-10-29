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
    // Picture panning preserves aspect ratio and never samples outside the
    // image, including portrait outputs, wide artwork and repeated full turns.
    auto still = pictureUV(0, 1, 16.0 / 9, 32.0 / 9, 2, 1, false);
    assert(std::abs(still.u - .25) < 1e-8 && std::abs(still.v - 1) < 1e-8);
    auto center = pictureUV(.5, .5, 1, 1, 0, 0, true);
    auto turned = pictureUV(.5, .5, 1, 1, PI / 2, PI / 2, true);
    assert(turned.u > center.u && turned.v < center.v);
    for (double screen : {.5, 1.0, 16.0 / 9, 3.0})
        for (double image : {.4, 1.0, 2.0, 4.0})
            for (int step = -80; step <= 80; ++step) {
                double yaw = step * PI / 8, pitch = step * .017;
                auto tl = pictureUV(0, 0, screen, image, yaw, pitch, true);
                auto br = pictureUV(1, 1, screen, image, yaw, pitch, true);
                assert(tl.u >= -1e-8 && tl.v >= -1e-8 && br.u <= 1+1e-8 && br.v <= 1+1e-8);
                assert(std::abs((br.u-tl.u)/(br.v-tl.v)*image-screen) < 1e-8);
                auto repeat = pictureUV(0, 0, screen, image, yaw+2*PI, pitch, true);
                assert(std::abs(tl.u-repeat.u) < 1e-8 && tl.v == repeat.v);
            }
    std::cout << "Per-monitor faces, selection, Compiz geometry, 3D spacing and picture motion: PASS\n";
}
