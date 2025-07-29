#pragma once

#include "proxy/proxy.h"
#include "proxy/v3/proxy.h"
#include <cstdint>
#include <memory>
#include <pybind11/cast.h>
#include <pybind11/detail/common.h>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>
#include <pybind11/stl.h>
#include <string>
#include <unistd.h>
#include <vector>

#ifdef PRINT_DEBUG_INFO
#    define PRINT_BUFFER( buffer )                                                            \
        {                                                                                     \
            std::cout << "[DEBUG] ";                                                          \
            for ( int i = 0; i < 40; i++ )                                                    \
            { std::cout << (int)( buffer.get_cursor()[i] ) << " "; }                          \
            std::cout << std::endl;                                                           \
        }

#    define PRINT_MSG( msg )                                                                  \
        { std::cout << "[DEBUG] " << msg << std::endl; }

#    include <iostream>
#else
#    define PRINT_BUFFER( buffer )
#    define PRINT_MSG( msg )
#endif

#if defined( _MSC_VER )
#    include <stdlib.h>
#    define bswap16( x ) _byteswap_ushort( x )
#    define bswap32( x ) _byteswap_ulong( x )
#    define bswap64( x ) _byteswap_uint64( x )
#elif defined( __GNUC__ ) || defined( __clang__ )
#    define bswap16( x ) __builtin_bswap16( x )
#    define bswap32( x ) __builtin_bswap32( x )
#    define bswap64( x ) __builtin_bswap64( x )
#else
#    error "Unsupported compiler!"
#endif

namespace py = pybind11;

const uint32_t kNewClassTag    = 0xFFFFFFFF;
const uint32_t kClassMask      = 0x80000000; // OR the class index with this
const uint32_t kByteCountMask  = 0x40000000; // OR the byte count with this
const uint32_t kMaxMapCount    = 0x3FFFFFFE; // last valid fMapCount and byte count
const uint16_t kByteCountVMask = 0x4000;     // OR the version byte count with this
const uint16_t kMaxVersion     = 0x3FFF;     // highest possible version number
const int32_t kMapOffset       = 2; // first 2 map entries are taken by null obj and self obj

class BinaryBuffer {
  public:
    BinaryBuffer( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets )
        : m_data( static_cast<uint8_t*>( data.request().ptr ) )
        , m_offsets( static_cast<uint32_t*>( offsets.request().ptr ) )
        , m_entries( offsets.request().size - 1 )
        , m_cursor( static_cast<uint8_t*>( data.request().ptr ) ) {}

    template <typename T>
    inline const T read() {
        const T value = *reinterpret_cast<const T*>( m_cursor );
        m_cursor += sizeof( T );

        switch ( sizeof( T ) )
        {
        case 1: return value; // no byte swap needed for 1 byte
        case 2: return (const T)bswap16( (uint16_t)value );
        case 4: return (const T)bswap32( (uint32_t)value );
        case 8: return (const T)bswap64( (uint64_t)value );
        default: throw std::runtime_error( "Unsupported type size for read operation" );
        }
    }

    const int16_t read_fVersion() { return read<int16_t>(); }

    const uint32_t read_fNBytes() {
        auto byte_count = read<uint32_t>();
        if ( !( byte_count & kByteCountMask ) )
            throw std::runtime_error( "Invalid byte count" );
        return byte_count & ~kByteCountMask;
    }

    const std::string read_null_terminated_string() {
        auto start = m_cursor;
        while ( *m_cursor != 0 ) { m_cursor++; }
        m_cursor++;
        return std::string( start, m_cursor );
    }

    const std::string read_obj_header() {
        read_fNBytes();
        auto fTag = read<uint32_t>();
        if ( fTag == kNewClassTag ) return read_null_terminated_string();
        else return std::string();
    }

    const uint8_t* get_cursor() const { return m_cursor; }
    const uint64_t entries() const { return m_entries; }

  private:
    uint8_t* m_cursor;
    const uint64_t m_entries;
    const uint8_t* m_data;
    const uint32_t* m_offsets;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

PRO_DEF_MEM_DISPATCH( MemRead, read );
PRO_DEF_MEM_DISPATCH( MemData, data );
PRO_DEF_MEM_DISPATCH( MemName, name );

struct _IElementReader : pro::facade_builder                                  //
                         ::add_convention<MemRead, void( BinaryBuffer& )>     //
                         ::add_convention<MemData, py::object() const>        //
                         ::add_convention<MemName, const std::string() const> //
                         ::support_copy<pro::constraint_level::nontrivial>    //
                         ::build {};                                          //

using IElementReader = pro::proxy<_IElementReader>;

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

template <typename ReaderType, typename... Args>
IElementReader CreateReader( Args... args ) {
    return pro::make_proxy_shared<_IElementReader, ReaderType>(
        std::forward<Args>( args )... );
}

template <typename ReaderType, typename... Args>
void register_reader( py::module& m, const char* name ) {
    m.def( name, &CreateReader<ReaderType, std::string, Args...> );
}

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

template <typename Sequence>
inline py::array_t<typename Sequence::value_type> make_array( Sequence&& seq ) {
    auto size                         = seq.size();
    auto data                         = seq.data();
    std::unique_ptr<Sequence> seq_ptr = std::make_unique<Sequence>( std::move( seq ) );
    auto capsule                      = py::capsule( seq_ptr.get(), []( void* p ) {
        std::unique_ptr<Sequence>( reinterpret_cast<Sequence*>( p ) );
    } );
    seq_ptr.release();
    return py::array( size, data, capsule );
}

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

template <typename T>
class BasicTypeReader {
  public:
    BasicTypeReader( std::string name ) : m_name( name ), m_data() {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) { m_data.push_back( buffer.read<T>() ); }

    py::object data() const { return make_array( std::move( m_data ) ); }

  private:
    std::string m_name;
    std::vector<T> m_data;
};

template <>
class BasicTypeReader<bool> {
  public:
    BasicTypeReader( std::string name ) : m_name( name ), m_data() {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) { m_data.push_back( buffer.read<uint8_t>() != 0 ); }

    py::object data() const { return make_array( std::move( m_data ) ); }

  private:
    std::string m_name;
    std::vector<uint8_t> m_data;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class TObjectReader {
    enum EStatusBits {
        kCanDelete = 1ULL << 0, ///< if object in a list can be deleted
        // 2 is taken by TDataMember
        kMustCleanup  = 1ULL << 3, ///< if object destructor must call RecursiveRemove()
        kIsReferenced = 1ULL << 4, ///< if object is referenced by a TRef or TRefArray
        kHasUUID      = 1ULL << 5, ///< if object has a TUUID (its fUniqueID=UUIDNumber)
        kCannotPick   = 1ULL << 6, ///< if object in a pad cannot be picked
        // 7 is taken by TAxis and TClass.
        kNoContextMenu = 1ULL << 8, ///< if object does not want context menu
        // 9, 10 are taken by TH1, TF1, TAxis and a few others
        // 12 is taken by TAxis
        kInvalidObject = 1ULL << 13 ///< if object ctor succeeded but object should not be used
    };

  public:
    TObjectReader( std::string name ) : m_name( name ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        // TODO: CanIgnoreTObjectStreamer() ?
        buffer.read_fVersion();
        auto fUniqueID = buffer.read<uint32_t>();
        auto fBits     = buffer.read<uint32_t>();
        if ( fBits & kIsReferenced ) auto pidf = buffer.read<uint16_t>();
    }

    py::object data() const { return py::none(); }

  private:
    const std::string m_name;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class TStringReader {
  public:
    TStringReader( std::string name ) : m_name( name ), m_data(), m_offsets( { 0 } ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        uint32_t fSize = buffer.read<uint8_t>();
        if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

        for ( int i = 0; i < fSize; i++ ) { m_data.push_back( buffer.read<uint8_t>() ); }
        m_offsets.push_back( m_data.size() );
    }

    py::object data() const {
        auto offsets_array = make_array( std::move( m_offsets ) );
        auto data_array    = make_array( std::move( m_data ) );
        return py::make_tuple( offsets_array, data_array );
    }

  private:
    const std::string m_name;

    std::vector<uint8_t> m_data;
    std::vector<uint32_t> m_offsets;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class STLSeqReader {
  public:
    STLSeqReader( std::string name, bool with_header, IElementReader element_reader )
        : m_name( name )
        , m_with_header( with_header )
        , m_element_reader( element_reader )
        , m_offsets( { 0 } ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        if ( m_with_header )
        {
            buffer.read_fNBytes();
            buffer.read_fVersion();
        }

        auto fSize = buffer.read<uint32_t>();
        m_offsets.push_back( m_offsets.back() + fSize );
        for ( auto i = 0; i < fSize; i++ ) m_element_reader->read( buffer );
    }

    py::object data() const {
        auto offsets_array = make_array( std::move( m_offsets ) );
        auto elements_data = m_element_reader->data();
        return py::make_tuple( offsets_array, elements_data );
    }

  private:
    const std::string m_name;
    const bool m_with_header;
    IElementReader m_element_reader;
    std::vector<uint32_t> m_offsets;
};

class STLMapReader {
  public:
    STLMapReader( std::string name, bool with_header, IElementReader key_reader,
                  IElementReader value_reader )
        : m_name( name )
        , m_with_header( with_header )
        , m_offsets( { 0 } )
        , m_key_reader( key_reader )
        , m_value_reader( value_reader ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        if ( m_with_header )
        {
            buffer.read_fNBytes();
            buffer.read_fVersion();
        }

        auto fSize = buffer.read<uint32_t>();
        m_offsets.push_back( m_offsets.back() + fSize );
        for ( auto i = 0; i < fSize; i++ )
        {
            m_key_reader->read( buffer );
            m_value_reader->read( buffer );
        }
    }

    py::object data() const {
        auto offsets_array     = make_array( std::move( m_offsets ) );
        py::object keys_data   = m_key_reader->data();
        py::object values_data = m_value_reader->data();
        return py::make_tuple( offsets_array, keys_data, values_data );
    }

  private:
    const std::string m_name;
    const bool m_with_header;

    std::vector<uint32_t> m_offsets;
    IElementReader m_key_reader;
    IElementReader m_value_reader;
};

class STLStringReader {
  public:
    STLStringReader( std::string name, bool with_header )
        : m_name( name ), m_with_header( with_header ), m_offsets( { 0 } ), m_data() {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        if ( m_with_header )
        {
            buffer.read_fNBytes();
            buffer.read_fVersion();
        }

        uint32_t fSize = buffer.read<uint8_t>();
        if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

        m_offsets.push_back( m_offsets.back() + fSize );
        for ( int i = 0; i < fSize; i++ ) { m_data.push_back( buffer.read<uint8_t>() ); }
    }

    py::object data() const {
        auto offsets_array = make_array( std::move( m_offsets ) );
        auto data_array    = make_array( std::move( m_data ) );

        return py::make_tuple( offsets_array, data_array );
    }

  private:
    const std::string m_name;
    const bool m_with_header;

    std::vector<uint32_t> m_offsets;
    std::vector<uint8_t> m_data;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

template <typename T>
class TArrayReader {
  public:
    TArrayReader( std::string name ) : m_name( name ), m_offsets( { 0 } ), m_data() {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        auto fSize = buffer.read<uint32_t>();
        m_offsets.push_back( m_offsets.back() + fSize );
        for ( auto i = 0; i < fSize; i++ ) { m_data.push_back( buffer.read<T>() ); }
    }

    py::object data() const {
        auto offsets_array = make_array( std::move( m_offsets ) );
        auto data_array    = make_array( std::move( m_data ) );
        return py::make_tuple( offsets_array, data_array );
    }

  private:
    const std::string m_name;

    std::vector<uint32_t> m_offsets;
    std::vector<T> m_data;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class ObjectReader {
  public:
    ObjectReader( std::string name, std::vector<IElementReader> element_readers )
        : m_name( name ), m_element_readers( element_readers ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
#ifdef PRINT_DEBUG_INFO
        std::cout << "BaseObjectReader " << m_name << "::read(): " << std::endl;
        for ( int i = 0; i < 40; i++ ) std::cout << (int)buffer.get_cursor()[i] << " ";
        std::cout << std::endl << std::endl;
#endif
        buffer.read_fNBytes();
        buffer.read_fVersion();
        for ( auto& reader : m_element_readers )
        {
#ifdef PRINT_DEBUG_INFO
            std::cout << "BaseObjectReader " << m_name << ": " << reader->name() << ":"
                      << std::endl;
            for ( int i = 0; i < 40; i++ ) std::cout << (int)buffer.get_cursor()[i] << " ";
            std::cout << std::endl << std::endl;
#endif
            reader->read( buffer );
        }
    }

    py::object data() const {
        py::list res;
        for ( auto& reader : m_element_readers ) { res.append( reader->data() ); }
        return res;
    }

  private:
    const std::string m_name;
    std::vector<IElementReader> m_element_readers;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class CArrayReader {
  public:
    CArrayReader( std::string name, bool is_obj, uint32_t flat_size,
                  IElementReader element_reader )
        : m_name( name )
        , m_is_obj( is_obj )
        , m_flat_size( flat_size )
        , m_element_reader( element_reader ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& buffer ) {
        if ( m_is_obj )
        {
            buffer.read_fNBytes();
            buffer.read_fVersion();
        }
        for ( auto i = 0; i < m_flat_size; i++ ) m_element_reader->read( buffer );
    }

    py::object data() const { return m_element_reader->data(); }

  private:
    const std::string m_name;

    bool m_is_obj;
    uint32_t m_flat_size;
    IElementReader m_element_reader;
};

/*
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
-----------------------------------------------------------------------------
*/

class EmptyReader {
  public:
    EmptyReader( std::string name ) : m_name( name ) {}

    const std::string name() const { return m_name; }

    void read( BinaryBuffer& ) {}
    py::object data() const { return py::none(); }

  private:
    const std::string m_name;
};
