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

class TSTLArray : public TObject {
  private:
    // --------- Simple types ---------
    array<bool, 3> m_arr_bool{ { false, true, false } };
    array<signed char, 3> m_arr_schar{ { 1, 2, 3 } };
    array<int, 3> m_arr_int{ { 1, 2, 3 } };

    // --------- Simple STL ---------
    array<string, 3> m_arr_str{ { "Hello", "STD", "Array" } };

    array<vector<int>, 3> m_arr_vec_int{ { { 1, 2, 3 }, { 4, 5, 6 }, { 7, 8, 9 } } };

    array<map<int, double>, 3> m_arr_map_int_double{ { { { 1, 1.0 }, { 2, 2.0 } },
                                                       { { 3, 3.0 }, { 4, 4.0 } },
                                                       { { 5, 5.0 }, { 6, 6.0 } } } };

    array<map<string, string>, 3> m_arr_map_str_str{
        { { { "A", "Apple" }, { "B", "Banana" } },
          { { "C", "Cat" }, { "D", "Dog" } },
          { { "E", "Elephant" }, { "F", "Frog" } } } };

    // --------- ROOT objects ---------
    array<TString, 3> m_arr_tstr{ { "Hello", "STD", "Array" } };
    array<TArrayI, 3> m_arr_tarr_int{ { TArrayI( 3 ), TArrayI( 3 ), TArrayI( 3 ) } };

  public:
    TSTLArray() : TObject() {
        for ( int i = 0; i < 3; i++ )
        {
            for ( int j = 0; j < 3; j++ ) { m_arr_tarr_int[i][j] = i * 10 + j; }
        }
    }

    ClassDef( TSTLArray, 1 );
};
