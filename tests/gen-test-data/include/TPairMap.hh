#pragma once

#include <map>
#include <string>
#include <utility>
#include <vector>

#include <TNamed.h>
#include <TObject.h>

/**
 * @brief A map whose value is a collection, a map whose value is a class, and a
 * pair that stands on its own.
 *
 * ROOT stores a map as a run of `pair<K,V>` values and records a streamer info
 * for that pair, whose two elements `first` and `second` are the key and the
 * value (`TGenCollectionProxy::GetValueClass`).  A pair that is not part of a
 * map is read from that same streamer info, which is what `m_vecvecpair`
 * covers.
 *
 * Both `m_mapvstr` and `m_mapnamed` are fixed arrays, so the run of maps shares
 * one header per entry (`Collections.md` §11.1); both `m_vecmapvstr` and
 * `m_vecmapnamed` store the map object-wise, one map at a time.
 */
class TPairMap {

  public:
    /// Fill one entry: @p i is the entry number.
    void fill( int i )
    {
        for ( int k = 0; k < 2; k++ )
        {
            m_mapvstr[k].clear();
            m_mapvstr[k]["k" + std::to_string( k )].push_back( "v" + std::to_string( 100 * i + k ) );

            m_mapnamed[k].clear();
            m_mapnamed[k][k] = TNamed( Form( "n%d_%d", i, k ), "" );
        }

        m_vecmapvstr.clear();
        m_vecmapnamed.clear();
        m_vecvecpair.clear();

        // The three inner runs differ per entry, so a header that covered only
        // the first element of a run would show up as a wrong second entry.
        for ( int k = 0; k < 1 + i % 3; k++ )
        {
            std::map<std::string, std::vector<std::string>> vstr;
            vstr["k" + std::to_string( k )].push_back( "v" + std::to_string( 100 * i + k ) );
            m_vecmapvstr.push_back( vstr );

            std::map<int, TNamed> named;
            named[k] = TNamed( Form( "n%d_%d", i, k ), "" );
            m_vecmapnamed.push_back( named );

            m_vecvecpair.push_back( { std::make_pair( 100 * i + k, 0.5 * k ) } );
        }
    }

    const std::map<std::string, std::vector<std::string>> &mapvstr_at( int k ) const
    {
        return m_mapvstr[k];
    }
    const std::map<int, TNamed> &mapnamed_at( int k ) const { return m_mapnamed[k]; }
    const std::vector<std::map<std::string, std::vector<std::string>>> &vecmapvstr() const
    {
        return m_vecmapvstr;
    }
    const std::vector<std::map<int, TNamed>> &vecmapnamed() const { return m_vecmapnamed; }
    const std::vector<std::vector<std::pair<int, double>>> &vecvecpair() const
    {
        return m_vecvecpair;
    }

  private:
    /// A fixed array of maps whose value is a collection: one shared header.
    std::map<std::string, std::vector<std::string>> m_mapvstr[2];

    /// A fixed array of maps whose value is a class.
    std::map<int, TNamed> m_mapnamed[2];

    /// Object-wise maps whose value is a collection.
    std::vector<std::map<std::string, std::vector<std::string>>> m_vecmapvstr;

    /// Object-wise maps whose value is a class.
    std::vector<std::map<int, TNamed>> m_vecmapnamed;

    /// A pair as the element of a collection: ROOT's `pair<K,V>` streamer info.
    std::vector<std::vector<std::pair<int, double>>> m_vecvecpair;

    ClassDef( TPairMap, 1 );
};
