from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent


class MinimizeSymbolTests(unittest.TestCase):
    def test_actual_candidate_wins_over_an_unrelated_display_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);source=path/'check.cpp';binary=path/'check'
            source.write_text('''#include "symbols.hpp"
#include <cassert>
int main() {
 const std::string add="_ZN6Render11CRenderPass3addEON9Hyprutils6Memory14CUniquePointerI12IPassElementEE";
 const std::string remove="_ZN6Render11CRenderPass15removeAllOfTypeERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE";
 assert(Minimize::symbolMatches(add,"CRenderPass::add("));
 assert(!Minimize::symbolMatches(add,"CRenderPass::removeAllOfType("));
 assert(!Minimize::symbolMatches(remove,"CRenderPass::add("));
 assert(!Minimize::symbolMatches("invalid-symbol","CRenderPass::add("));
}
''')
            subprocess.run(['g++','-std=c++17','-I'+str(ROOT/'native'),str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
