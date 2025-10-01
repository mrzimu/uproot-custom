#pragma once

#include <TString.h>
#include <map>
#include <unordered_map>

#include <TObject.h>

using namespace std;

class TSTLMap : public TObject {
  private:
    map<int, double> m_map_int_double{ { 1, 1.0 }, { 2, 2.0 }, { 3, 3.0 } };
    unordered_map<int, double> m_umap_int_double{ { 1, 1.0 }, { 2, 2.0 }, { 3, 3.0 } };
    multimap<int, double> m_mmap_int_double{ { 1, 1.0 }, { 1, 1.1 }, { 2, 2.0 } };
    unordered_multimap<int, double> m_ummap_int_double{ { 1, 1.0 }, { 1, 1.1 }, { 2, 2.0 } };

    map<string, TString> m_map_str_tstr{ { "A", "Apple" }, { "B", "Banana" }, { "C", "Cat" } };

    ClassDef( TSTLMap, 1 );
};
