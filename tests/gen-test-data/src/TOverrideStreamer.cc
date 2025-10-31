#include "TOverrideStreamer.hh"
#include <TObject.h>

#include <iostream>

ClassImp( TOverrideStreamer );

void TOverrideStreamer::Streamer( TBuffer& b ) {
    if ( b.IsReading() )
    {
        TObject::Streamer( b ); // Call base class Streamer

        b >> m_int;

        unsigned int mask;
        b >> mask; // We additionally read a mask
        if ( mask != 0x12345678 )
        {
            std::cerr << "Error: Unexpected mask value: " << std::hex << mask << std::dec
                      << std::endl;
            return;
        }

        b >> m_double;
    }
    else
    {
        TObject::Streamer( b ); // Call base class Streamer
        b << m_int;
        unsigned int mask = 0x12345678; // Example mask
        b << mask;                      // Write the mask
        b << m_double;
    }
}
