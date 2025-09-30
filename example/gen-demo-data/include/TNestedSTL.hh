#pragma once

#include <map>
#include <vector>

#include <TObject.h>
#include <TSimpleObject.hh>

using namespace std;

class TNestedSTL : public TObject {
  private:
    map<int, map<int, map<int, string>>> m_map3_str;
    vector<vector<vector<TSimpleObject>>> m_vec3_obj;
    map<int, vector<TSimpleObject>> m_map_vec_obj;
    map<string, vector<string>> m_map_vec_str;
    vector<map<int, TSimpleObject>> m_vec_map_obj;

  public:
    TNestedSTL() : TObject() {
        for ( auto i = 0; i < 2; i++ )
        {
            vector<TSimpleObject> tmp_vec_obj;
            vector<string> tmp_vec_str;
            map<int, TSimpleObject> tmp_map_obj;

            for ( auto j = 0; j < 3; j++ )
            {
                for ( auto k = 0; k < 2; k++ )
                {
                    m_map3_str[i][j][k] =
                        string( "val: " ) + to_string( i * 100 + j * 10 + k );
                }

                tmp_vec_obj.push_back( TSimpleObject() );
                tmp_vec_str.push_back( string( "val: " ) + to_string( i * 10 + j ) );
                tmp_map_obj[i * 10 + j] = TSimpleObject();
            }

            m_map_vec_obj[i]              = tmp_vec_obj;
            m_map_vec_str[to_string( i )] = tmp_vec_str;
            m_vec_map_obj.push_back( tmp_map_obj );
        }
    }

    ClassDef( TNestedSTL, 1 );
};