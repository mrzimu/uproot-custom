#pragma once

#include <TBuffer.h>
#include <TObject.h>

class TOverrideStreamer : public TObject {
  public:
    TOverrideStreamer( int val = 0 )
        : TObject(), m_int( val ), m_double( (double)val * 3.14 ) {}

  private:
    int m_int{ 0 };
    double m_double{ 0.0 };

    ClassDef( TOverrideStreamer, 1 );
};
