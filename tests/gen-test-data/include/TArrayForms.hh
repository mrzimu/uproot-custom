#pragma once

#include <array>
#include <map>
#include <string>
#include <vector>

#include <TObject.h>
#include <TNamed.h>
#include <TString.h>

/**
 * @brief The array forms of one element type, side by side.
 *
 * A fixed C array and a `std::array` of the same element type are the same
 * bytes on disk (`Collections.md` §11): `std::array` is mapped to a C array by
 * `TStreamerInfo::Build`, and the framing of the run is decided by the element
 * class alone (`ElementTypes.md` §7.2).  Each member below therefore appears
 * twice, once in each spelling, and both must read back identically.
 */
class TArrayForms : public TObject {

  public:
    TArrayForms() : TObject() {
        for ( int i = 0; i < 2; i++ )
        {
            m_carr_int[i] = 0;
            m_arr_int[i]  = 0;

            m_carr_tstr[i] = "";
            m_arr_tstr[i]  = "";

            m_carr_str[i] = "";
            m_arr_str[i]  = "";

            m_carr_vec[i].clear();
            m_arr_vec[i].clear();

            m_carr_mapvec[i].clear();
            m_arr_mapvec[i].clear();
        }
    }

    /// Fill one entry; every value depends on @p i so entries are distinct.
    void fill( int i ) {
        for ( int j = 0; j < 2; j++ )
        {
            m_carr_int[j] = i * 10 + j;
            m_arr_int[j]  = i * 10 + 100 + j;

            m_carr_tstr[j] = Form( "ct%d_%d", j, i );
            m_arr_tstr[j]  = Form( "at%d_%d", j, i );

            m_carr_str[j] = "cs" + std::to_string( j ) + "_" + std::to_string( i );
            m_arr_str[j]  = "as" + std::to_string( j ) + "_" + std::to_string( i );

            m_carr_vec[j].clear();
            m_carr_vec[j].push_back( i * 10 + j );
            m_carr_vec[j].push_back( i * 10 + j + 1 );

            m_arr_vec[j].clear();
            m_arr_vec[j].push_back( i * 10 + 100 + j );

            m_carr_mapvec[j].clear();
            m_carr_mapvec[j][j] = m_carr_vec[j];

            m_arr_mapvec[j].clear();
            m_arr_mapvec[j][j] = m_arr_vec[j];
        }
    }

  private:
    /// 65 + kOffsetL: one shared `fNBytes+fVersion` header, then two strings.
    TString m_carr_tstr[2]{};
    std::array<TString, 2> m_arr_tstr{};

    /// 500: one shared header, then two complete collections.
    std::string m_carr_str[2]{};
    std::array<std::string, 2> m_arr_str{};

    std::vector<int> m_carr_vec[2]{};
    std::array<std::vector<int>, 2> m_arr_vec{};

    /// 82: no outer header, each collection bare.
    std::map<int, std::vector<int>> m_carr_mapvec[2]{};
    std::array<std::map<int, std::vector<int>>, 2> m_arr_mapvec{};

    /// 86: one shared header, then bare `TObject`s.
    TObject m_carr_tobj[2];
    std::array<TObject, 2> m_arr_tobj;

    /// 87: one shared header, then objects that frame themselves.
    TNamed m_carr_tnamed[2]{};
    std::array<TNamed, 2> m_arr_tnamed{};

    /// n = fArrayLength, from 21 to 39 with `kOffsetL`: bare values.
    int m_carr_int[2]{};
    std::array<int, 2> m_arr_int{};

    ClassDef( TArrayForms, 1 );
};
