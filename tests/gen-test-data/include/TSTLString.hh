#pragma once

#include <string>

#include <TObject.h>

using namespace std;

class TSTLString : public TObject {
  private:
    string m_str{ "Hello, STL String!" };

    ClassDef( TSTLString, 1 );
};
