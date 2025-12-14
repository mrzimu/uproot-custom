#pragma once

#include <pybind11/cast.h>
#include <pybind11/detail/common.h>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>

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

/**
 * @brief Macro to import the uproot_custom.cpp module.
 * @note This macro should be used in the `PYBIND11_MODULE` definition of your module.
 */
#define IMPORT_UPROOT_CUSTOM_CPP pybind11::module_::import( "uproot_custom.cpp" );

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

    const uint16_t kStreamedMemberWise = 1 << 14; // streamed member-wise mask

    class BinaryBuffer {
      public:
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

        /**
         * @brief Construct a BinaryBuffer from numpy arrays.
         * @param data A numpy array of uint8_t containing the raw data.
         * @param offsets A numpy array of uint32_t containing the offsets for each entry.
         */
        BinaryBuffer( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets )
            : m_data( static_cast<uint8_t*>( data.request().ptr ) )
            , m_offsets( static_cast<uint32_t*>( offsets.request().ptr ) )
            , m_entries( offsets.request().size - 1 )
            , m_cursor( static_cast<uint8_t*>( data.request().ptr ) ) {}

        /**
         * @brief Read a value of type T from the buffer, handling endianness.
         *
         * @tparam T The type to read.
         * @return The value read from the buffer.
         */
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

        /**
         * @brief Read the fVersion field from the buffer
         *
         * @return The fVersion value
         */
        const int16_t read_fVersion() { return read<int16_t>(); }

        /**
         * @brief Read the fNBytes field from the buffer, checking the byte count mask.
         *
         * @return The fNBytes value without the mask.
         * @exception std::runtime_error if the byte count mask is not set.
         */
        const uint32_t read_fNBytes() {
            auto byte_count = read<uint32_t>();
            if ( !( byte_count & kByteCountMask ) )
                throw std::runtime_error( "Invalid byte count" );
            return byte_count & ~kByteCountMask;
        }

        /**
         * @brief Read a null-terminated (`\0`) string from the buffer.
         *
         * @return The string read from the buffer.
         */
        const std::string read_null_terminated_string() {
            auto start = m_cursor;
            while ( *m_cursor != 0 ) { m_cursor++; }
            m_cursor++;
            return std::string( start, m_cursor );
        }

        /**
         * @brief Read an object header from the buffer. The object header has `fNBytes`,
         * `fVersion`, `fTag`. If `fTag == kNewClassTag`, then a null-terminated class name
         * follows.
         *
         * @return The class name if the object is a new class, empty string
         * otherwise.
         */
        const std::string read_obj_header() {
            read_fNBytes();
            auto fTag = read<uint32_t>();
            if ( fTag == kNewClassTag ) return read_null_terminated_string();
            else return std::string();
        }

        /**
         * @brief Read a TString from the buffer. A TString has `length` (uint8_t). If `length
         * == 255`, then the `length` is a following uint32_t. Then following `length` bytes of
         * string data.
         *
         * @return The TString data read from the buffer, as a std::string.
         */
        const std::string read_TString() {
            uint32_t length = read<uint8_t>();
            if ( length == 255 ) length = read<uint32_t>();
            auto start = m_cursor;
            m_cursor += length;
            return std::string( start, m_cursor );
        }

        /**
         * @brief Skip `n` bytes in the buffer.
         *
         * @param n Number of bytes to skip.
         */
        void skip( const size_t n ) { m_cursor += n; }

        /**
         * @brief Skip the fNBytes field. Equivalent to read_fNBytes() but does not return the
         * value, since the mask need to be checked.
         */
        void skip_fNBytes() { read_fNBytes(); }

        /**
         * @brief Skip the fVersion field.
         */
        void skip_fVersion() { skip( 2 ); }

        /**
         * @brief Skip a null-terminated (`\0`) string in the buffer.
         */
        void skip_null_terminated_string() {
            while ( *m_cursor != 0 ) { m_cursor++; }
            m_cursor++;
        }

        /**
         * @brief Skip an object header in the buffer. The object header has `fNBytes`,
         * `fVersion`, `fTag`. If `fTag == kNewClassTag`, then a null-terminated class name
         * follows.
         */
        void skip_obj_header() {
            skip_fNBytes();
            auto fTag = read<uint32_t>();
            if ( fTag == kNewClassTag ) skip_null_terminated_string();
        }

        /**
         * @brief Skip a TObject in the buffer. A TObject has `fVersion` (2 bytes), `fUniqueID`
         * (4 bytes), `fBits` (4 bytes). If `fBits & kIsReferenced`, then a `pidf` (2 bytes)
         * follows.
         */
        void skip_TObject() {
            // TODO: CanIgnoreTObjectStreamer() ?
            skip_fVersion();
            skip( 4 ); // fUniqueID
            auto fBits = read<uint32_t>();
            if ( fBits & ( kIsReferenced ) ) skip( 2 ); // pidf
        }

        /**
         * @brief Get the raw data pointer.
         */
        const uint8_t* get_data() const { return m_data; }

        /**
         * @brief Get the current cursor pointer.
         */
        const uint8_t* get_cursor() const { return m_cursor; }

        /**
         * @brief Get the entry offsets array pointer.
         */
        const uint32_t* get_offsets() const { return m_offsets; }

        /**
         * @brief Get the number of entries.
         */
        const uint64_t entries() const { return m_entries; }

        /**
         * @brief Debug print the next `n` bytes from the current cursor.
         *
         * @param n Number of bytes to print.
         */
        void debug_print( const size_t n = 100 ) const {
            for ( size_t i = 0; i < n; i++ ) { std::cout << (int)*( m_cursor + i ) << " "; }
            std::cout << std::endl;
        }

      private:
        uint8_t* m_cursor;         ///< current cursor position
        const uint64_t m_entries;  ///< number of entries
        const uint8_t* m_data;     ///< raw data pointer
        const uint32_t* m_offsets; ///< entry offsets pointer
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Interface for element readers. All element readers must inherit from this class.
     */
    class IReader {
      protected:
        const std::string m_name; ///< name of the reader

      public:
        /**
         * @brief Construct a new IReader object.
         *
         * @param name Name of the reader.
         */
        IReader( std::string name ) : m_name( name ) {}

        virtual ~IReader() = default;

        /**
         * @brief Get the name of the reader.
         *
         * @return Name of the reader.
         */
        virtual const std::string name() const { return m_name; }

        /**
         * @brief Read an element from the buffer.
         *
         * @param buffer The binary buffer to read from.
         */
        virtual void read( BinaryBuffer& buffer ) = 0;

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return The data read by the reader.
         */
        virtual py::object data() const = 0;

        /**
         * @brief Read multiple elements from the buffer in one go. Repeatedly calls @ref
         * read() by default.
         *
         * @note When multiple elements are stored together, some classes may have "one common
         * header + multiple data objects" format. This method can be overridden to handle such
         * cases more efficiently.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of elements to read.
         * @return Number of elements read.
         */
        virtual uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) {
            for ( int32_t i = 0; i < count; i++ ) { read( buffer ); }
            return count;
        }

        /**
         * @brief Read elements from the buffer until reaching the end position. Repeatedly
         * calls @ref read() method by default.
         *
         * @note When multiple elements are stored together, some classes may have "one common
         * header + multiple data objects" format. This method can be overridden to handle such
         * cases more efficiently.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position pointer.
         * @return Number of elements read.
         */
        virtual uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) {
            uint32_t cur_count = 0;
            while ( buffer.get_cursor() < end_pos )
            {
                read( buffer );
                cur_count++;
            }
            return cur_count;
        }

        /**
         * @brief Read multiple elements from the buffer in member-wise fashion. Readers
         * that need to handle member-wise data reading must implement this method.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of elements to read.
         * @return Number of elements read.
         */
        virtual uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) {
            throw std::runtime_error( name() + "::read_many_memberwise is not implemented." );
        }
    };

    /**
     * @brief Deprecated alias for IReader.
     * @deprecated Use IReader instead.
     */
    using IElementReader
        [[deprecated( "IElementReader is deprecated. Use IReader instead." )]] = IReader;

    /**
     * @brief Shortcut for shared pointer to IReader.
     * @note When a reader requires another reader as a member, it must use
     * `std::shared_ptr<IReader>` to properly handle lifetime management.
     */
    using SharedReader = shared_ptr<IReader>;

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Helper function to create a shared pointer to a reader. Pybind11 requires
     * shared_ptr to handle object lifetime correctly.
     *
     * @tparam ReaderType The type of the reader.
     * @tparam Args The argument types for the reader constructor.
     * @param args The arguments for the reader constructor.
     * @return The shared pointer to the created reader.
     */
    template <typename ReaderType, typename... Args>
    shared_ptr<ReaderType> CreateReader( Args... args ) {
        return std::make_shared<ReaderType>( std::forward<Args>( args )... );
    }

    /**
     * @brief Helper function to declare a reader class in a pybind11 module. Automatically
     * wraps the class' constructor to return a shared_ptr. User should always use this
     * function to declare reader classes.
     *
     * @tparam ReaderType The type of the reader.
     * @tparam Args The argument types for the reader constructor.
     * @param m The declaring pybind11 module.
     * @param name The name of the reader class in Python.
     */
    template <typename ReaderType, typename... Args>
    void declare_reader( py::module& m, const char* name ) {
        py::class_<ReaderType, shared_ptr<ReaderType>, IReader>( m, name ).def(
            py::init( &CreateReader<ReaderType, Args...> ) );
    }

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Convert a shared pointer to a std::vector<T> to a numpy array without copying.
     * User can use this function to return numpy arrays from reader's data() method.
     *
     * @tparam T The element type of the vector.
     * @param seq The shared pointer to the std::vector<T>.
     * @return The numpy array wrapping the vector data.
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

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Debug print function. Prints only when macro or environment varialbe with name
     * `UPROOT_DEBUG` is defined. Use this function like `printf()`.
     *
     * @tparam Args Argument types. No need to specify explicitly.
     * @param msg The format string.
     * @param args Arguments to format.
     */
    template <typename... Args>
    inline void debug_printf( const char* msg, Args... args ) {
        bool do_print = getenv( "UPROOT_DEBUG" );
#ifdef UPROOT_DEBUG
        do_print = true;
#endif
        if ( !do_print ) return;
        printf( msg, std::forward<Args>( args )... );
    }

    /**
     * @brief Debug print function for BinaryBuffer. Prints only when macro or environment
     * varialbe with name `UPROOT_DEBUG` is defined. Call @ref BinaryBuffer::debug_print()
     * internally.
     *
     * @param buffer The BinaryBuffer to print.
     * @param n Number of bytes to print.
     */
    inline void debug_printf( uproot::BinaryBuffer& buffer, const size_t n = 100 ) {
        bool do_print = getenv( "UPROOT_DEBUG" );
#ifdef UPROOT_DEBUG
        do_print = true;
#endif
        if ( !do_print ) return;
        buffer.debug_print( n );
    }

} // namespace uproot
