#pragma once

#include <array>
#include <list>
#include <set>
#include <unordered_set>
#include <vector>

#include <map>
#include <unordered_map>

#include <TObject.h>

using namespace std;

class TComplicatedSTL : public TObject {

  public:
    TComplicatedSTL() : TObject() {
        // Initialize 1 basic type element
        for ( int i = 0; i < 5; i++ )
        {
            vector<int> vec_int;
            map<int, double> map_int_double;
            list<int> list_int;
            set<int> set_int;
            unordered_set<int> uset_int;
            for ( int j = 0; j < 4; j++ )
            {
                vec_int.push_back( 10 * i + j );
                list_int.push_back( 10 * i + j );
                set_int.insert( 10 * i + j );
                uset_int.insert( 10 * i + j );
                map_int_double[10 * i + j] = 0.1 * ( 10 * i + j );
            }

            // std::array
            m_arr_int[i]     = 100 + i;
            m_arr_vec_int[i] = vec_int;
            m_arr_str[i]     = "Hello, " + to_string( i );

            // c-style array
            m_carr_int[i]            = 10 + i;
            m_carr_vec_int[i]        = vec_int;
            m_carr_map_int_double[i] = map_int_double;
            m_carr_str[i]            = "World, " + to_string( i );

            // sequence like containers
            m_vec_list_int.push_back( list_int );
            m_list_set_int.push_back( set_int );
            m_vec_uset_int.push_back( uset_int );

            // mapping<sequence> like containers
            m_map_vec_int[i]   = vec_int;
            m_umap_list_int[i] = list_int;
            m_map_set_int[i]   = set_int;
            m_umap_uset_int[i] = uset_int;

            // nested containers
            vector<list<set<int>>> vec_list_set_int;
            for ( int j = 0; j < 2; j++ )
            {
                list<set<int>> list_set_int;
                for ( int k = 0; k < 2; k++ )
                {
                    set<int> set_int;
                    for ( int l = 0; l < 3; l++ )
                    { set_int.insert( 100 * i + 10 * j + 2 * k + l ); }
                    list_set_int.push_back( set_int );
                }
                vec_list_set_int.push_back( list_set_int );
            }
            m_map_vec_list_set_int[i] = vec_list_set_int;
        }
    }

  private:
    int m_marker{ 114514 }; // just a marker

    // c-style array
    int m_carr_int[5]{};
    vector<int> m_carr_vec_int[5]{};
    map<int, double> m_carr_map_int_double[5]{};
    string m_carr_str[5]{};

    // std::array
    array<int, 5> m_arr_int;
    array<vector<int>, 5> m_arr_vec_int;
    array<string, 5> m_arr_str;
    // ROOT-6.32.02 does not support std::array of map

    // sequence like containers
    vector<list<int>> m_vec_list_int;
    list<set<int>> m_list_set_int;
    vector<unordered_set<int>> m_vec_uset_int;

    // mapping<sequence> like containers
    map<int, vector<int>> m_map_vec_int;
    unordered_map<int, list<int>> m_umap_list_int;
    map<int, set<int>> m_map_set_int;
    unordered_map<int, unordered_set<int>> m_umap_uset_int;

    // nested containers
    map<int, vector<list<set<int>>>> m_map_vec_list_set_int;

    ClassDef( TComplicatedSTL, 1 );
};
