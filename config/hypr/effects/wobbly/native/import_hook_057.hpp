#pragma once

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <link.h>
#include <sys/mman.h>
#include <unistd.h>

namespace Wobbly {
// Hyprland's function trampolines are allocated near its executable and cannot
// reach libxcb under ASLR. Replace only the executable's resolved import slot;
// the shared library and other libraries' imports keep their original behavior.
// This adapter is x86-64 only and is guarded by the exact Hyprland build hash.
class ImportHook {
    void** slot_ = nullptr;
    void* original_ = nullptr;
    void* replacement_ = nullptr;
    void* page_ = nullptr;
    size_t pageSize_ = 0;
    int protection_ = 0;

    struct Search {
        const char* name;
        void** slot = nullptr;
        int protection = 0;
        bool ambiguous = false;
    };

    static int find(dl_phdr_info* image, size_t, void* opaque) {
        if (image->dlpi_name && *image->dlpi_name) return 0;
        auto& search = *static_cast<Search*>(opaque);
        const ElfW(Dyn)* dynamic = nullptr;
        for (size_t i = 0; i < image->dlpi_phnum; ++i)
            if (image->dlpi_phdr[i].p_type == PT_DYNAMIC)
                dynamic = reinterpret_cast<const ElfW(Dyn)*>(image->dlpi_addr + image->dlpi_phdr[i].p_vaddr);
        if (!dynamic) return 1;
        const ElfW(Sym)* symbols = nullptr;
        const char* names = nullptr;
        const ElfW(Rela)* relocations = nullptr;
        const ElfW(Rela)* jumps = nullptr;
        size_t relocationBytes = 0, jumpBytes = 0;
        bool relaJumps = false;
        // Linux's dynamic loader has already relocated these table pointers.
        for (auto entry = dynamic; entry->d_tag != DT_NULL; ++entry) {
            switch (entry->d_tag) {
                case DT_SYMTAB: symbols = reinterpret_cast<const ElfW(Sym)*>(entry->d_un.d_ptr); break;
                case DT_STRTAB: names = reinterpret_cast<const char*>(entry->d_un.d_ptr); break;
                case DT_RELA: relocations = reinterpret_cast<const ElfW(Rela)*>(entry->d_un.d_ptr); break;
                case DT_RELASZ: relocationBytes = entry->d_un.d_val; break;
                case DT_JMPREL: jumps = reinterpret_cast<const ElfW(Rela)*>(entry->d_un.d_ptr); break;
                case DT_PLTRELSZ: jumpBytes = entry->d_un.d_val; break;
                case DT_PLTREL: relaJumps = entry->d_un.d_val == DT_RELA; break;
            }
        }
        if (!symbols || !names) return 1;
        auto scan = [&](const ElfW(Rela)* table, size_t bytes) {
            if (!table) return;
            for (size_t i = 0; i < bytes / sizeof(*table); ++i) {
                const auto& entry = table[i];
                auto type = ELF64_R_TYPE(entry.r_info);
                if (type != R_X86_64_GLOB_DAT && type != R_X86_64_JUMP_SLOT) continue;
                if (std::strcmp(names + symbols[ELF64_R_SYM(entry.r_info)].st_name, search.name)) continue;
                auto slot = reinterpret_cast<void**>(image->dlpi_addr + entry.r_offset);
                if (search.slot && search.slot != slot) search.ambiguous = true;
                search.slot = slot;
            }
        };
        scan(relocations, relocationBytes);
        if (relaJumps) scan(jumps, jumpBytes);
        auto address = reinterpret_cast<uintptr_t>(search.slot);
        for (size_t i = 0; i < image->dlpi_phnum; ++i) {
            const auto& segment = image->dlpi_phdr[i];
            auto start = image->dlpi_addr + segment.p_vaddr;
            if (segment.p_type == PT_LOAD && address >= start && address + sizeof(void*) <= start + segment.p_memsz)
                search.protection = ((segment.p_flags & PF_R) ? PROT_READ : 0) |
                                    ((segment.p_flags & PF_W) ? PROT_WRITE : 0) |
                                    ((segment.p_flags & PF_X) ? PROT_EXEC : 0);
        }
        for (size_t i = 0; i < image->dlpi_phnum; ++i) {
            const auto& segment = image->dlpi_phdr[i];
            auto start = image->dlpi_addr + segment.p_vaddr;
            if (segment.p_type == PT_GNU_RELRO && address >= start && address < start + segment.p_memsz)
                search.protection &= ~PROT_WRITE;
        }
        return 1;
    }

public:
    ImportHook() = default;
    ImportHook(const ImportHook&) = delete;
    ImportHook& operator=(const ImportHook&) = delete;

    bool install(const char* name, void* expected, void* replacement) {
        if (slot_) return false;
        Search search{name};
        dl_iterate_phdr(find, &search);
        if (!search.slot || search.ambiguous || !(search.protection & PROT_READ) || *search.slot != expected) return false;
        auto size = sysconf(_SC_PAGESIZE);
        if (size <= 0) return false;
        pageSize_ = static_cast<size_t>(size);
        page_ = reinterpret_cast<void*>(reinterpret_cast<uintptr_t>(search.slot) & ~(pageSize_ - 1));
        protection_ = search.protection;
        if (mprotect(page_, pageSize_, protection_ | PROT_WRITE) != 0) return false;
        *search.slot = replacement;
        if (mprotect(page_, pageSize_, protection_) != 0) {
            *search.slot = expected;
            mprotect(page_, pageSize_, protection_);
            return false;
        }
        slot_ = search.slot; original_ = expected; replacement_ = replacement;
        return true;
    }

    bool remove() {
        if (!slot_) return true;
        if (*slot_ != replacement_ || mprotect(page_, pageSize_, protection_ | PROT_WRITE) != 0) return false;
        *slot_ = original_;
        bool restored = mprotect(page_, pageSize_, protection_) == 0;
        slot_ = nullptr;
        return restored;
    }
};
}
