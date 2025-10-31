#pragma once

#include <TArrayC.h>
#include <TArrayD.h>
#include <TArrayF.h>
#include <TArrayI.h>
#include <TArrayL.h>
#include <TArrayS.h>
#include <TObjArray.h>
#include <TObject.h>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

class TObjInObjArray : public TObject {
  private:
    // STL
    std::string m_str;
    std::vector<int> m_vec_int;
    std::map<int, float> m_map_if;
    std::map<std::string, double> m_map_sd;
    std::map<int, std::string> m_map_is;
    std::map<int, std::vector<int>> m_map_vec_int;
    std::map<int, std::map<int, float>> m_map_map_if;

    // TArray
    TArrayI m_tarr_i{ 0 };
    TArrayC m_tarr_c{ 0 };
    TArrayS m_tarr_s{ 0 };
    TArrayL m_tarr_l{ 0 };
    TArrayF m_tarr_f{ 0 };
    TArrayD m_tarr_d{ 0 };

    // TString
    TString m_tstr;

    // CStyle array
    int m_carr_int[3]{ 0, 0, 0 };
    std::vector<int> m_carr_vec_int[2];

    // basic types
    bool m_bool{ false };
    int8_t m_int8{ 0 };
    int16_t m_int16{ 0 };
    int32_t m_int32{ 0 };
    int64_t m_int64{ 0 };
    uint8_t m_uint8{ 0 };
    uint16_t m_uint16{ 0 };
    uint32_t m_uint32{ 0 };
    uint64_t m_uint64{ 0 };
    float m_float{ 0.0 };
    double m_double{ 0.0 };

    ClassDef( TObjInObjArray, 1 );

  public:
    TObjInObjArray( int val = 0 )
        : TObject()
        , m_bool( val % 2 == 0 )
        , m_int8( val )
        , m_int16( val * 2 )
        , m_int32( val * 3 )
        , m_int64( val * 4 )
        , m_uint8( val + 10 )
        , m_uint16( val * 2 + 10 )
        , m_uint32( val * 3 + 10 )
        , m_uint64( val * 4 + 10 )
        , m_float( val * 1.1 )
        , m_double( val * 1.1 * 2 )
        , m_str( "str_" + std::to_string( val ) )
        , m_tstr( "tstr_" + std::to_string( val ) )
        , m_tarr_i( val % 5 )
        , m_tarr_c( val % 5 )
        , m_tarr_s( val % 5 )
        , m_tarr_l( val % 5 )
        , m_tarr_f( val % 5 )
        , m_tarr_d( val % 5 ) {
        for ( int i = 0; i < val % 5; i++ ) m_vec_int.push_back( val + i );
        for ( int i = 0; i < val % 5; i++ ) m_map_if[i] = val + i * 0.1f;
        for ( int i = 0; i < val % 5; i++ )
            m_map_sd["key_" + std::to_string( i )] = val + i * 0.1;
        for ( int i = 0; i < val % 5; i++ ) m_map_is[i] = "val_" + std::to_string( val + i );
        for ( int i = 0; i < val % 5; i++ ) m_map_vec_int[i] = { val + i, val + i + 10 };
        for ( int i = 0; i < val % 5; i++ )
            m_map_map_if[i] = { { i, val + i * 0.1f }, { i + 10, val + ( i + 10 ) * 0.1f } };

        for ( int i = 0; i < val % 5; i++ ) m_tarr_i.SetAt( val + i, i );
        for ( int i = 0; i < val % 5; i++ ) m_tarr_c.SetAt( val + i, i );
        for ( int i = 0; i < val % 5; i++ ) m_tarr_s.SetAt( val + i, i );
        for ( int i = 0; i < val % 5; i++ ) m_tarr_l.SetAt( val + i, i );
        for ( int i = 0; i < val % 5; i++ ) m_tarr_f.SetAt( val + i * 0.1f, i );
        for ( int i = 0; i < val % 5; i++ ) m_tarr_d.SetAt( val + i * 0.1, i );

        for ( int i = 0; i < 3; i++ ) m_carr_int[i] = val + i;
        for ( int i = 0; i < 2; i++ ) m_carr_vec_int[i] = { val + i, val + i + 10 };
    }
};

class TObjWithObjArray : public TObject {
  private:
    TObjArray m_obj_array;

    ClassDef( TObjWithObjArray, 1 );

  public:
    TObjWithObjArray( int val = 0 )
        : TObject()
        , m_obj_array() // preallocate space for 5 elements
    {
        for ( int i = 0; i < val % 5; i++ )
        { m_obj_array.Add( new TObjInObjArray( val + i ) ); }
    }
};
