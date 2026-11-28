#pragma once

#include <map>
#include <string>
#include <utility>
#include <vector>

#include <TNamed.h>
#include <TObject.h>
#include <TString.h>

/**
 * @brief Members declared as pointers to STL containers (`kSTLp`).
 *
 * A `TStreamerSTL` element whose type name ends in `*` is `kSTLp`: ROOT writes
 * it as the container itself, with no pointer tag and no null marker, and only
 * the frame version at which the value class's version follows differs
 * (`Collections.md` §11.3).  A null pointer is a count of 0, which entry 0
 * covers.
 *
 * The four scalar members differ in what the value class costs to read: `int`
 * needs no column, `TNamed` is read member-wise, the map's value is a
 * collection, and the `std::string` has no value class at all.  The fifth is a
 * fixed array of pointers, which shares one frame and one value-class version
 * across its two collections (`Collections.md` §11.1).
 */
class TSTLPointer {

  public:
    TSTLPointer() = default;

    TSTLPointer( const TSTLPointer& )            = delete;
    TSTLPointer& operator=( const TSTLPointer& ) = delete;

    ~TSTLPointer() { release(); }

    /// Fill one entry: entry 0 leaves every pointer null.
    void fill( int i ) {
        release();

        if ( i == 0 ) { return; }

        m_pvec       = new std::vector<int>;
        m_pvecnamed  = new std::vector<TNamed>;
        m_pmap       = new std::map<std::string, std::vector<std::string>>;
        m_pstr       = new std::string( "s" + std::to_string( i ) );
        m_pvecarr[0] = new std::vector<int>;
        m_pvecarr[1] = new std::vector<int>;

        // The count differs per entry, so a reader that reused the previous
        // entry's count would show up as a wrong second entry.
        for ( int k = 0; k < 1 + i % 3; k++ )
        {
            m_pvec->push_back( 100 * i + k );
            m_pvecnamed->emplace_back( Form( "n%d_%d", i, k ), "" );
            ( *m_pmap )["k" + std::to_string( k )].push_back( "v" +
                                                              std::to_string( 100 * i + k ) );
        }

        // The two collections of the array hold different counts, and the
        // second is empty for every third entry, so a reader that took one
        // count for the whole run would show up here.
        for ( int k = 0; k < 1 + i % 2; k++ ) { m_pvecarr[0]->push_back( 1000 * i + k ); }
        for ( int k = 0; k < i % 3; k++ ) { m_pvecarr[1]->push_back( 2000 * i + k ); }
    }

  private:
    void release() {
        delete m_pvec;
        delete m_pvecnamed;
        delete m_pmap;
        delete m_pstr;
        delete m_pvecarr[0];
        delete m_pvecarr[1];

        m_pvec       = nullptr;
        m_pvecnamed  = nullptr;
        m_pmap       = nullptr;
        m_pstr       = nullptr;
        m_pvecarr[0] = nullptr;
        m_pvecarr[1] = nullptr;
    }

    /// A pointer to a sequence of basic types.
    std::vector<int>* m_pvec = nullptr;

    /// A pointer to a sequence whose value class is read member-wise.
    std::vector<TNamed>* m_pvecnamed = nullptr;

    /// A pointer to a map whose value is a collection.
    std::map<std::string, std::vector<std::string>>* m_pmap = nullptr;

    /// A pointer to a string (a collection with no value class).
    std::string* m_pstr = nullptr;

    /// A fixed array of pointers to a sequence, which shares one frame
    /// (`Collections.md` §11.1).
    std::vector<int>* m_pvecarr[2] = { nullptr, nullptr };

    ClassDef( TSTLPointer, 1 );
};
