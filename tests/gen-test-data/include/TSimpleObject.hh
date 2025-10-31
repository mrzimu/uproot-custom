#pragma once

#include <array>
#include <map>
#include <string>
#include <vector>

#include <RtypesCore.h>
#include <TArrayI.h>
#include <TObject.h>
#include <TString.h>

using namespace std;

class TSimpleObject : public TObject {
  private:
    // --------- Simple types ---------
    int m_int{ 32 };

    // --------- Simple STL ---------
    string m_str{ "Hello, ROOT!" };

    // std::array
    array<int, 5> m_arr_int{ 100, 101, 102, 103, 104 };

    // Sequence like containers
    vector<double> m_vec_double{ 1.0, 2.0, 3.0 };

    // Mapping like containers
    map<int, double> m_map_int_double{ { 1, 1.0 }, { 2, 2.0 }, { 3, 3.0 } };
    map<string, TString> m_map_str_str{ { "A", "Apple" }, { "B", "Banana" }, { "C", "Cat" } };

    // --------- ROOT objects ---------
    TString m_tstr{ "Hello, ROOT!" };
    TArrayI m_tarr_int{ 5 };

  public:
    TSimpleObject() : TObject() {
        for ( int i = 0; i < m_tarr_int.GetSize(); i++ ) m_tarr_int[i] = i * 10;
    }

    ClassDef( TSimpleObject, 1 );
};
