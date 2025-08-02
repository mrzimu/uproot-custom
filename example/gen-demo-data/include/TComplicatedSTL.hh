#pragma once

#include <array>
#include <list>
#include <set>
#include <unordered_set>
#include <vector>

#include <map>
#include <unordered_map>

#include <TObject.h>
#include <TOverrideStreamer.hh>

using namespace std;

class TComplicatedSTL : public TObject {

  public:
    TComplicatedSTL() : TObject() {}

    void fill() {
        // Initialize 1 basic type element
        for ( int i = 0; i < 5; i++ )
        {
            vector<int> vec_int;
            list<int> list_int;
            set<int> set_int;
            unordered_set<int> uset_int;
            for ( int j = 0; j < 4; j++ )
            {
                vec_int.push_back( 10 * i + j );
                list_int.push_back( 10 * i + j );
                set_int.insert( 10 * i + j );
                uset_int.insert( 10 * i + j );
            }

            // sequence like containers
            m_arr_vec_int[i] = vec_int;
            m_vec_list_int.push_back( list_int );
            m_list_set_int.push_back( set_int );
            m_vec_uset_int.push_back( uset_int );

            // mapping<sequence> like containers
            m_map_vec_int[i]   = vec_int;
            m_umap_list_int[i] = list_int;
            m_map_set_int[i]   = set_int;
            m_umap_uset_int[i] = uset_int;

            /* ------------------------------------ */
            // mapping<sequence<object>> like containers
            vector<TComplicatedSTL> vec_obj;
            list<TComplicatedSTL*> list_objptr;
            for ( int j = 0; j < 3; j++ )
            {
                vec_obj.emplace_back();
                list_objptr.push_back( new TComplicatedSTL() );
            }
            m_map_vec_obj[i]     = vec_obj;
            m_map_list_objptr[i] = list_objptr;
        }
    }

  private:
    // sequence like containers
    array<vector<int>, 5> m_arr_vec_int;
    vector<list<int>> m_vec_list_int;
    list<set<int>> m_list_set_int;
    vector<unordered_set<int>> m_vec_uset_int;

    // mapping<sequence> like containers
    map<int, vector<int>> m_map_vec_int;
    unordered_map<int, list<int>> m_umap_list_int;
    map<int, set<int>> m_map_set_int;
    unordered_map<int, unordered_set<int>> m_umap_uset_int;

    // mapping<sequence<object>> like containers
    map<int, vector<TComplicatedSTL>> m_map_vec_obj;
    map<int, list<TComplicatedSTL*>> m_map_list_objptr;

    ClassDef( TComplicatedSTL, 1 );
};