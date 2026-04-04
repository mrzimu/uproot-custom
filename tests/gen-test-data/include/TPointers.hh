#pragma once

#include <TObject.h>

#include <vector>

using namespace std;

struct TestPointerStruct : public TObject {
    int m_int{ 42 };
    double m_double{ 3.14 };

    TestPointerStruct() = default;
    TestPointerStruct( int i ) : m_int( i ), m_double( 3.14 * i ) {}

    ClassDef( TestPointerStruct, 1 );
};

class TPointers : public TObject {
  private:
    vector<TestPointerStruct*> m_vec_ptr;

  public:
    TPointers() {
        for ( int i = 0; i < 3; i++ ) { m_vec_ptr.push_back( new TestPointerStruct( i ) ); }
        for ( int i = 0; i < 3; i++ ) { m_vec_ptr.push_back( m_vec_ptr[i] ); }
    }

    TPointers( int i ) {
        for ( int j = 0; j < 3; j++ )
        { m_vec_ptr.push_back( new TestPointerStruct( i * 10 + j ) ); }
        for ( int j = 0; j < 3; j++ ) { m_vec_ptr.push_back( m_vec_ptr[j] ); }
    }

    ClassDef( TPointers, 1 );
};
