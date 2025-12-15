#pragma once

#include <map>
#include <string>
#include <vector>

#include <RtypesCore.h>
#include <TArrayI.h>
#include <TObject.h>
#include <TString.h>

#include "TSimpleObject.hh"

using namespace std;

class TCStyleArray : public TObject {
  private:
    // --------- Simple types ---------
    bool m_bool[3]{ false, true, false };
    signed char m_schar[3]{ 1, 2, 3 };
    int m_int[2][3][4]{};

    // --------- Simple STL ---------
    string m_str[3]{ "Hello", "C-Style", "Array" };

    vector<double> m_vec_double[3]{ { 1.0, 2.0, 3.0 }, { 4.0, 5.0, 6.0 }, { 7.0, 8.0, 9.0 } };

    map<int, double> m_map_int_double[3]{
        { { 1, 1.0 }, { 2, 2.0 } }, { { 3, 3.0 }, { 4, 4.0 } }, { { 5, 5.0 }, { 6, 6.0 } } };

    map<string, string> m_map_str_str[3]{ { { "A", "Apple" }, { "B", "Banana" } },
                                          { { "C", "Cat" }, { "D", "Dog" } },
                                          { { "E", "Elephant" }, { "F", "Frog" } } };

    // --------- ROOT objects ---------
    TString m_tstr[3]{ "Hello", "C-Style", "Array" };
    TArrayI m_tarr_int[3]{ TArrayI( 3 ), TArrayI( 3 ), TArrayI( 3 ) };

    // --------- Custom objects ---------
    TSimpleObject m_simple_obj[3]{ TSimpleObject(), TSimpleObject(), TSimpleObject() };

  public:
    TCStyleArray() : TObject() {
        // fill int[2][3][4]
        int tmp_value = 1;
        for ( int i = 0; i < 2; i++ )
        {
            for ( int j = 0; j < 3; j++ )
            {
                for ( int k = 0; k < 4; k++ ) { m_int[i][j][k] = tmp_value++; }
            }
        }

        // fill TArray
        for ( int i = 0; i < 3; i++ )
        {
            for ( int j = 0; j < 3; j++ ) { m_tarr_int[i][j] = i * 10 + j; }
        }
    }

    ClassDef( TCStyleArray, 1 );
};
