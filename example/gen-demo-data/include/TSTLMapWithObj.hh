#pragma once

#include "TSimpleObject.hh"
#include <map>
#include <string>

#include <TBasicTypes.hh>
#include <TCStyleArray.hh>
#include <TObject.h>
#include <TRootObjects.hh>
#include <TSTLArray.hh>
#include <TSTLMap.hh>
#include <TSTLSequence.hh>
#include <TSTLString.hh>

using namespace std;

class TSTLMapWithObj : public TObject {
  private:
    map<string, TBasicTypes> m_map_basic_types;
    map<string, TSTLString> m_map_stl_string;
    map<string, TSTLSequence> m_map_stl_sequence;
    map<string, TSTLMap> m_map_stl_map;
    map<string, TRootObjects> m_map_root_objects;
    map<string, TCStyleArray> m_map_cstyle_array;
    map<string, TSTLArray> m_map_stl_array;
    map<string, TSimpleObject> m_map_simple_object;

  public:
    TSTLMapWithObj() : TObject() {
        for ( int i = 0; i < 3; i++ )
        {
            m_map_basic_types[to_string( i )]   = TBasicTypes();
            m_map_stl_string[to_string( i )]    = TSTLString();
            m_map_stl_sequence[to_string( i )]  = TSTLSequence();
            m_map_stl_map[to_string( i )]       = TSTLMap();
            m_map_root_objects[to_string( i )]  = TRootObjects();
            m_map_cstyle_array[to_string( i )]  = TCStyleArray();
            m_map_stl_array[to_string( i )]     = TSTLArray();
            m_map_simple_object[to_string( i )] = TSimpleObject();
        }
    }

    ClassDef( TSTLMapWithObj, 1 );
};