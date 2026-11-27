#pragma once

#include <map>
#include <vector>

#include <TNamed.h>
#include <TObject.h>
#include <TString.h>

/**
 * @brief One object with a fixed array of every framing family.
 *
 * The point of this class is that it is stored inside a collection, so ROOT
 * writes its members as *columns*: one header for the whole run of objects, or
 * one per object, is the question the fixture answers.  The accessors exist so
 * a ROOT program can print the values the writer put in, which is the reference
 * the reader is checked against.
 */
class TArrayInObject : public TObject {

  public:
    TArrayInObject() : TObject() {
        for ( int k = 0; k < 2; k++ )
        {
            m_int[k] = 0;
            m_tstr[k] = "";
            m_vec[k].clear();
            m_mapvec[k].clear();
        }
    }

    /// Fill one object: @p i is the entry, @p j the position in the collection.
    void fill( int i, int j ) {
        for ( int k = 0; k < 2; k++ )
        {
            m_int[k] = 100 * i + 10 * j + k;
            m_tstr[k] = Form( "t%d_%d_%d", i, j, k );

            m_vec[k].clear();
            m_vec[k].push_back( 100 * i + 10 * j + k );

            m_mapvec[k].clear();
            m_mapvec[k][k] = m_vec[k];

            m_tnamed[k].SetName( Form( "n%d_%d_%d", i, j, k ) );
            m_tnamed[k].SetTitle( "" );
        }
    }

    int int_at( int k ) const { return m_int[k]; }
    const TString &tstr_at( int k ) const { return m_tstr[k]; }
    const std::vector<int> &vec_at( int k ) const { return m_vec[k]; }
    const std::map<int, std::vector<int>> &mapvec_at( int k ) const { return m_mapvec[k]; }
    const TNamed &tnamed_at( int k ) const { return m_tnamed[k]; }

  private:
    /// 21–39: bare values.
    int m_int[2]{};

    /// 85: one shared header, then two strings.
    TString m_tstr[2]{};

    /// 500: one shared header, then two complete collections.
    std::vector<int> m_vec[2]{};

    /// 82: no header, each collection bare.
    std::map<int, std::vector<int>> m_mapvec[2]{};

    /// 87: one shared header, then objects that frame themselves.
    TNamed m_tnamed[2]{};

    ClassDef( TArrayInObject, 1 );
};

/**
 * @brief The tree object: a collection of `TArrayInObject`.
 */
class TArrayInObjectHolder : public TObject {

  public:
    TArrayInObjectHolder() : TObject() {}

    /// Fill one entry with @p n objects.
    void fill( int i, int n ) {
        m_objs.clear();
        for ( int j = 0; j < n; j++ )
        {
            TArrayInObject obj;
            obj.fill( i, j );
            m_objs.push_back( obj );
        }
    }

    std::size_t size() const { return m_objs.size(); }
    const TArrayInObject &at( int j ) const { return m_objs.at( j ); }

  private:
    std::vector<TArrayInObject> m_objs;

    ClassDef( TArrayInObjectHolder, 1 );
};
