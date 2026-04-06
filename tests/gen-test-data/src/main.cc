#include <TFile.h>
#include <TTree.h>
#include <iostream>

#include "TBasicTypes.hh"
#include "TCStyleArray.hh"
#include "TComplicatedSTL.hh"
#include "TNestedSTL.hh"
#include "TPointers.hh"
#include "TRootObjects.hh"
#include "TSTLArray.hh"
#include "TSTLMap.hh"
#include "TSTLMapWithObj.hh"
#include "TSTLSeqWithObj.hh"
#include "TSTLSequence.hh"
#include "TSTLString.hh"
#include "TSimpleObject.hh"

using namespace std;

const char* TREE_NAME = "tree";
const int NUM_ENTRIES = 10;

void gen_primitive() {
    TFile f( "test_primitive.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TBasicTypes basic_types;
    t.Branch( "branch", &basic_types );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        basic_types = TBasicTypes();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLString() {
    TFile f( "test_stl_string.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLString stl_string;
    t.Branch( "branch", &stl_string );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_string = TSTLString();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLSequence() {
    TFile f( "test_stl_sequence.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLSequence stl_sequence;
    t.Branch( "branch", &stl_sequence );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_sequence = TSTLSequence();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLMap() {
    TFile f( "test_stl_map.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLMap stl_map;
    t.Branch( "branch", &stl_map );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_map = TSTLMap();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_RootObjects() {
    TFile f( "test_root_objects.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TRootObjects root_objects;
    t.Branch( "branch", &root_objects );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        root_objects = TRootObjects();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_CStyleArray() {
    TFile f( "test_cstyle_array.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TCStyleArray cstyle_array;
    t.Branch( "branch", &cstyle_array );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        cstyle_array = TCStyleArray();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLArray() {
    TFile f( "test_stl_array.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLArray stl_array;
    t.Branch( "branch", &stl_array );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_array = TSTLArray();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLSeqWithObj() {
    TFile f( "test_stl_seq_with_obj.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLSeqWithObj stl_seq_with_obj;
    t.Branch( "branch", &stl_seq_with_obj );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_seq_with_obj = TSTLSeqWithObj();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLMapWithObj() {
    TFile f( "test_stl_map_with_obj.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSTLMapWithObj stl_map_with_obj;
    t.Branch( "branch", &stl_map_with_obj );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        stl_map_with_obj = TSTLMapWithObj();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLNested() {
    TFile f( "test_stl_nested.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TNestedSTL nested_stl;
    t.Branch( "branch", &nested_stl );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        nested_stl = TNestedSTL();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_SimpleObject() {
    TFile f( "test_simple_obj.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TSimpleObject simple_obj;
    t.Branch( "branch", &simple_obj );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        simple_obj = TSimpleObject();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_STLComplicated() {
    TFile f( "test_stl_complicated.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TComplicatedSTL complicated_stl;
    t.Branch( "branch", &complicated_stl );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        complicated_stl = TComplicatedSTL();
        t.Fill();
    }

    t.Write();
    f.Close();
}

void gen_Pointers() {
    TFile f( "test_pointers.root", "RECREATE" );
    TTree t( TREE_NAME, "tree" );

    TPointers pointers;
    t.Branch( "branch", &pointers );

    for ( int i = 0; i < NUM_ENTRIES; i++ )
    {
        pointers = TPointers( i );
        t.Fill();
    }

    t.Write();
    f.Close();
}

int main() {
    cout << "Generating primitive data..." << endl;
    gen_primitive();

    cout << "Generating STL string data..." << endl;
    gen_STLString();

    cout << "Generating STL sequence data..." << endl;
    gen_STLSequence();

    cout << "Generating STL map data..." << endl;
    gen_STLMap();

    cout << "Generating ROOT objects data..." << endl;
    gen_RootObjects();

    cout << "Generating C-style array data..." << endl;
    gen_CStyleArray();

    cout << "Generating STL array data..." << endl;
    gen_STLArray();

    cout << "Generating STL sequence with object data..." << endl;
    gen_STLSeqWithObj();

    cout << "Generating STL map with object data..." << endl;
    gen_STLMapWithObj();

    cout << "Generating nested STL data..." << endl;
    gen_STLNested();

    cout << "Generating simple object data..." << endl;
    gen_SimpleObject();

    cout << "Generating complicated STL data..." << endl;
    gen_STLComplicated();

    cout << "Generating pointers data..." << endl;
    gen_Pointers();

    return 0;
}
