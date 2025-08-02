#include <TFile.h>
#include <TTree.h>

#include "TComplicatedSTL.hh"
#include "TOverrideStreamer.hh"

int main() {
    TFile f( "demo-data.root", "RECREATE" );
    TTree t( "my_tree", "tree" );

    TOverrideStreamer ovrd_steamer;
    TComplicatedSTL complicated_stl;

    t.Branch( "override_streamer", &ovrd_steamer );
    t.Branch( "complicated_stl", &complicated_stl );

    for ( int i = 0; i < 10; i++ )
    {
        ovrd_steamer    = TOverrideStreamer( i );
        complicated_stl = TComplicatedSTL();
        complicated_stl.fill();
        t.Fill();
    }

    t.Write();
    f.Close();
}