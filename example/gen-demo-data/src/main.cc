#include <TFile.h>
#include <TTree.h>

#include "TOverrideStreamer.hh"

int main() {
    TFile f( "demo-data.root", "RECREATE" );
    TTree t( "my_tree", "tree" );

    TOverrideStreamer ovrd_steamer;

    t.Branch( "override_streamer", &ovrd_steamer );

    for ( int i = 0; i < 10; i++ )
    {
        ovrd_steamer = TOverrideStreamer( i );
        t.Fill();
    }

    t.Write();
    f.Close();
}