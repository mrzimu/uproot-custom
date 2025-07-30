#pragma once

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

namespace uproot {
    namespace py = pybind11;
    using std::shared_ptr;

    const uint32_t kNewClassTag    = 0xFFFFFFFF;
    const uint32_t kClassMask      = 0x80000000; // OR the class index with this
    const uint32_t kByteCountMask  = 0x40000000; // OR the byte count with this
    const uint32_t kMaxMapCount    = 0x3FFFFFFE; // last valid fMapCount and byte count
    const uint16_t kByteCountVMask = 0x4000;     // OR the version byte count with this
    const uint16_t kMaxVersion     = 0x3FFF;     // highest possible version number
    const int32_t kMapOffset = 2; // first 2 map entries are taken by null obj and self obj

    class BinaryBuffer {

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
            kInvalidObject = 1ULL
                             << 13 ///< if object ctor succeeded but object should not be used
        };

      public:
        BinaryBuffer( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets )
            : m_data( static_cast<uint8_t*>( data.request().ptr ) )
            , m_offsets( static_cast<uint32_t*>( offsets.request().ptr ) )
            , m_entries( offsets.request().size - 1 )
            , m_cursor( static_cast<uint8_t*>( data.request().ptr ) ) {}

        template <typename T>
        const T read() {
            constexpr auto size = sizeof( T );

            switch ( size )
            {
            case 1: return *reinterpret_cast<const T*>( m_cursor++ );
            case 2: {
                union {
                    T value;
                    uint16_t bits;
                } val;
                val.value = *reinterpret_cast<const T*>( m_cursor );
                m_cursor += size;
                val.bits = bswap16( val.bits );
                return val.value;
            }
            case 4: {
                union {
                    T value;
                    uint32_t bits;
                } val;
                val.value = *reinterpret_cast<const T*>( m_cursor );
                m_cursor += size;
                val.bits = bswap32( val.bits );
                return val.value;
            }
            case 8: {
                union {
                    T value;
                    uint64_t bits;
                } val;
                val.value = *reinterpret_cast<const T*>( m_cursor );
                m_cursor += size;
                val.bits = bswap64( val.bits );
                return val.value;
            }
            default:
                throw std::runtime_error( "Unsupported type size: " + std::to_string( size ) );
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

        void skip( const size_t n ) { m_cursor += n; }

        void skip_fNBytes() { read_fNBytes(); } // need to check the mask
        void skip_fVersion() { skip( 2 ); }
        void skip_null_terminated_string() {
            while ( *m_cursor != 0 ) { m_cursor++; }
            m_cursor++;
        }

        void skip_obj_header() {
            skip_fNBytes();
            auto fTag = read<uint32_t>();
            if ( fTag == kNewClassTag ) skip_null_terminated_string();
        }

        void skip_TObject() {
            // TODO: CanIgnoreTObjectStreamer() ?
            skip_fVersion();
            skip( 4 ); // fUniqueID
            auto fBits = read<uint32_t>();
            if ( fBits & ( kIsReferenced ) ) skip( 2 ); // pidf
        }

        const uint8_t* get_cursor() const { return m_cursor; }
        const uint64_t entries() const { return m_entries; }

      private:
        uint8_t* m_cursor;
        const uint64_t m_entries;
        const uint8_t* m_data;
        const uint32_t* m_offsets; // by the time, this is not used
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class IElementReader {
      protected:
        const std::string m_name;

      public:
        IElementReader( std::string name ) : m_name( name ) {}
        virtual ~IElementReader() = default;

        virtual const std::string name() const { return m_name; }

        virtual void read( BinaryBuffer& buffer ) = 0;
        virtual py::object data() const           = 0;
    };

    using SharedReader = shared_ptr<IElementReader>;

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    template <typename ReaderType, typename... Args>
    shared_ptr<ReaderType> CreateReader( Args... args ) {
        return std::make_shared<ReaderType>( std::forward<Args>( args )... );
    }

    template <typename ReaderType, typename... Args>
    void register_reader( py::module& m, const char* name ) {
        py::class_<ReaderType, shared_ptr<ReaderType>, IElementReader>( m, name ).def(
            py::init( &CreateReader<ReaderType, std::string, Args...> ) );
    }

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    template <typename T>
    inline py::array_t<T> make_array( shared_ptr<std::vector<T>> seq ) {
        auto size = seq->size();
        auto data = seq->data();

        auto capsule = py::capsule( new auto( seq ), []( void* p ) {
            delete reinterpret_cast<std::shared_ptr<std::vector<T>>*>( p );
        } );

        return py::array_t<T>( size, data, capsule );
    }

} // namespace uproot
