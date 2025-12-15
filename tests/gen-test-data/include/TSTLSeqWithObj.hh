#pragma once

#include "TSimpleObject.hh"
#include <vector>

#include <TBasicTypes.hh>
#include <TCStyleArray.hh>
#include <TObject.h>
#include <TRootObjects.hh>
#include <TSTLArray.hh>
#include <TSTLMap.hh>
#include <TSTLSequence.hh>
#include <TSTLString.hh>

using namespace std;

class TSTLSeqWithObj : public TObject {
  private:
    vector<TBasicTypes> m_vec_basic_types;
    vector<TSTLString> m_vec_stl_string;
    vector<TSTLSequence> m_vec_stl_sequence;
    vector<TSTLMap> m_vec_stl_map;
    vector<TRootObjects> m_vec_root_objects;
    vector<TCStyleArray> m_vec_cstyle_array;
    vector<TSTLArray> m_vec_stl_array;
    vector<TSimpleObject> m_vec_simple_object;

  public:
    TSTLSeqWithObj() : TObject() {
        for ( int i = 0; i < 3; i++ )
        {
            m_vec_basic_types.push_back( TBasicTypes() );
            m_vec_stl_string.push_back( TSTLString() );
            m_vec_stl_sequence.push_back( TSTLSequence() );
            m_vec_stl_map.push_back( TSTLMap() );
            m_vec_root_objects.push_back( TRootObjects() );
            m_vec_cstyle_array.push_back( TCStyleArray() );
            m_vec_stl_array.push_back( TSTLArray() );
            m_vec_simple_object.push_back( TSimpleObject() );
        }
    }

    ClassDef( TSTLSeqWithObj, 1 );
};
