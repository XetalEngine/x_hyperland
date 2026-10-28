// SPDX-License-Identifier: GPL-2.0-or-later
// Burn and particles ported from Compiz animationaddon (2006):
// Erkin Bahceci <erkinbah@gmail.com>, Dennis Kasprzyk <onestone@compiz.org>.
// See COPYING and README.md. Integration copyright (c) 2026 XetalEngine.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <random>
#include <vector>

namespace Burn {
struct Settings {
    bool enabled = false;
    int duration = 200, time_step_intense = 30, fire_particles = 1000;
    float fire_size = 5, fire_slowdown = 0.5, fire_life = 0.7;
    std::array<uint16_t, 4> fire_color{65535, 13107, 1365, 65535};
    int fire_direction = 0;
    bool fire_constant_speed = false, fire_smoke = false, fire_mystical = false;
};
struct Rect { float x = 0, y = 0, w = 0, h = 0; };
struct Particle {
    float life = 0, fade = 0, width = 0, height = 0, w_mod = 0, h_mod = 0;
    float x = 0, y = 0, xo = 0, xi = 0, yi = 0, xg = 0, yg = 0;
    float r = 0, g = 0, b = 0, a = 0;
};

// A separate generator avoids changing Hyprland's global random state. Like
// Compiz, all random particle values use uniformly distributed 8-bit samples.
class Engine {
  public:
    Settings settings;
    Rect window;
    std::vector<Particle> smoke, fire;
    float total = 0, remaining = 0, progress = 0;
    int direction = 0;

    Engine(Settings s, Rect box, float anchorX, float anchorY, uint32_t seed)
        : settings(s), window(box), smoke(s.fire_particles / 10), fire(s.fire_particles), rng(seed) {
        total = remaining = s.duration * (s.fire_constant_speed ? box.h / 500.F : 1.F);
        direction = s.fire_direction;
        if (direction == 4) direction = rng() % 4;
        if (direction == 5) {
            const float x = (box.x + box.w / 2 - anchorX) / std::max(box.w, 1.F);
            const float y = (box.y + box.h / 2 - anchorY) / std::max(box.h, 1.F);
            direction = std::abs(y) > std::abs(x) ? (y > 0 ? 1 : 0) : (x > 0 ? 2 : 3);
        }
    }

    static void update(std::vector<Particle>& particles, float time, float slowdownSetting) {
        const float speed = time / 50.F;
        const float slowdown = slowdownSetting * (1.F - std::max(0.99F, time / 1000.F)) * 1000.F;
        for (auto& p : particles) if (p.life > 0) {
            p.x += p.xi / slowdown;
            p.y += p.yi / slowdown;
            p.xi += p.xg * speed;
            p.yi += p.yg * speed;
            p.life -= p.fade * speed;
        }
    }

    // Original order: particlesPrePrepPaintScreen, then fxBurnAnimStep.
    void step() {
        const float dt = settings.time_step_intense;
        update(smoke, dt, settings.fire_slowdown / 2.F);
        update(fire, dt, settings.fire_slowdown);
        if (remaining > 0) {
            // Compiz divides by duration - timestep. Handle its undefined case
            // (a timestep >= the duration) as a single, complete burn step.
            const float denom = std::max(total - dt, 1.F);
            const float old = 1.F - remaining / denom;
            remaining = std::max(0.F, remaining - dt);
            progress = std::clamp(1.F - remaining / denom, 0.F, 1.F);
            if (remaining > 0) {
                const float delta = progress - old;
                Rect strip = window;
                float size = window.w / 40.F;
                switch (direction) {
                    case 1: strip.y += (1 - progress) * window.h; strip.h = delta * window.h; break;
                    case 2: strip.x += (1 - progress) * window.w; strip.w = delta * window.w; size = window.h / 40.F; break;
                    case 3: strip.x += progress * window.w; strip.w = delta * window.w; size = window.h / 40.F; break;
                    default: strip.y += progress * window.h; strip.h = delta * window.h; break;
                }
                // Compiz's generator arguments are integers.
                strip = {float(int(strip.x)), float(int(strip.y)), float(int(strip.w)), float(int(strip.h))};
                if (settings.fire_smoke) {
                    auto s = strip;
                    if (direction < 2) s.h = 1;
                    spawn(smoke, s, size, dt, true);
                }
                spawn(fire, strip, size, dt, false);
            }
        }
        for (auto& p : smoke) p.xg = (p.x < p.xo ? 1 : -1) * window.w / 40.F;
        for (auto& p : fire) p.xg = p.x < p.xo ? 1 : -1;
    }

    Rect visible() const {
        if (remaining <= 0) return {};
        Rect r = window;
        switch (direction) {
            case 1: r.h *= 1 - progress; break;
            case 2: r.w *= 1 - progress; break;
            case 3: r.x += progress * r.w; r.w *= 1 - progress; break;
            default: r.y += progress * r.h; r.h *= 1 - progress; break;
        }
        return r;
    }

    bool done() const {
        const auto alive = [](const Particle& p) { return p.life > 0; };
        return remaining <= 0 && !std::ranges::any_of(fire, alive) && !std::ranges::any_of(smoke, alive);
    }

  private:
    std::mt19937 rng;
    float randomByte() { return float(rng() & 255) / 255.F; }
    void spawn(std::vector<Particle>& particles, Rect r, float size, float time, bool isSmoke) {
        float count = particles.size() * (time / 50.F) * (1.05F - settings.fire_life);
        count = std::min(count, float(isSmoke ? particles.size() : particles.size() / 5));
        for (auto& p : particles) {
            if (count <= 0) break;
            if (p.life > 0) continue;
            p.life = 1;
            p.fade = randomByte() * (1 - settings.fire_life) + 0.2F * (1.01F - settings.fire_life);
            if (isSmoke) {
                p.width = p.height = settings.fire_size * size * 5;
                p.w_mod = p.h_mod = -0.8F;
            } else {
                p.width = settings.fire_size; p.height = p.width * 1.5F;
                p.w_mod = p.h_mod = size * randomByte();
            }
            const float rx = randomByte(), ry = randomByte();
            p.x = p.xo = r.x + (r.w > 1 ? rx * r.w : 0);
            p.y = r.y + (r.h > 1 ? ry * r.h : 0);
            p.xi = randomByte() * 20 - 10;
            p.yi = isSmoke ? (randomByte() + 0.2F) * -size : randomByte() * 20 - 15;
            if (isSmoke) {
                p.r = p.g = p.b = randomByte() / 4.F;
                p.a = 0.5F + randomByte() / 2.F;
            } else {
                if (settings.fire_mystical) { p.r = randomByte(); p.g = randomByte(); p.b = randomByte(); }
                else {
                    const float f = 1 - randomByte() / 1.7F;
                    p.r = settings.fire_color[0] / 65535.F * f;
                    p.g = settings.fire_color[1] / 65535.F * f;
                    p.b = settings.fire_color[2] / 65535.F * f;
                }
                p.a = settings.fire_color[3] / 65535.F;
            }
            p.xg = (p.x < p.xo ? 1 : -1) * (isSmoke ? size : 1);
            p.yg = isSmoke ? -size : -3;
            --count;
        }
    }
};
}
