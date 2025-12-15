#include <TFile.h>
#include <TTree.h>

#include "TBasicTypes.hh"
#include "TCStyleArray.hh"
#include "TComplicatedSTL.hh"
#include "TNestedSTL.hh"
#include "TRootObjects.hh"
#include "TSTLArray.hh"
#include "TSTLMap.hh"
#include "TSTLMapWithObj.hh"
#include "TSTLSeqWithObj.hh"
#include "TSTLSequence.hh"
#include "TSTLString.hh"
#include "TSimpleObject.hh"

int main() {
    TFile f( "test-data.root", "RECREATE" );
    TTree t( "my_tree", "tree" );

    TBasicTypes basic_types;
    t.Branch( "basic_types", &basic_types );

    TSTLString stl_string;
    t.Branch( "stl_string", &stl_string );

    TSTLSequence stl_sequence;
    t.Branch( "stl_sequence", &stl_sequence );

    TSTLMap stl_map;
    t.Branch( "stl_map", &stl_map );

    TRootObjects root_objects;
    t.Branch( "root_objects", &root_objects );

    TCStyleArray ctyle_array;
    t.Branch( "cstyle_array", &ctyle_array );

    TSTLArray stl_array;
    t.Branch( "stl_array", &stl_array );

    TSTLSeqWithObj stl_seq_with_obj;
    t.Branch( "stl_seq_with_obj", &stl_seq_with_obj );

    TSTLMapWithObj stl_map_with_obj;
    t.Branch( "stl_map_with_obj", &stl_map_with_obj );

    TNestedSTL nested_stl;
    t.Branch( "nested_stl", &nested_stl );

    TSimpleObject simple_obj;
    t.Branch( "simple_obj", &simple_obj );

    TComplicatedSTL complicated_stl;
    t.Branch( "complicated_stl", &complicated_stl );

    for ( int i = 0; i < 10; i++ )
    {
        basic_types      = TBasicTypes();
        stl_string       = TSTLString();
        stl_sequence     = TSTLSequence();
        stl_map          = TSTLMap();
        root_objects     = TRootObjects();
        ctyle_array      = TCStyleArray();
        stl_array        = TSTLArray();
        stl_seq_with_obj = TSTLSeqWithObj();
        stl_map_with_obj = TSTLMapWithObj();
        nested_stl       = TNestedSTL();
        simple_obj       = TSimpleObject();
        complicated_stl  = TComplicatedSTL();

        t.Fill();
    }

    t.Write();
    f.Close();
}
