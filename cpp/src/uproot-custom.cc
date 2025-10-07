#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <pybind11/gil.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>
#include <stdexcept>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

template <typename... Args>
void debug_printf( const char* msg, Args... args ) {
    bool do_print = getenv( "UPROOT_DEBUG" );
#ifdef UPROOT_DEBUG
    do_print = true;
#endif
    if ( !do_print ) return;
    printf( msg, std::forward<Args>( args )... );
}

void debug_printf( uproot::BinaryBuffer& buffer ) {
    bool do_print = getenv( "UPROOT_DEBUG" );
#ifdef UPROOT_DEBUG
    do_print = true;
#endif
    if ( !do_print ) return;
    buffer.debug_print();
}

namespace uproot {
    template <typename T>
    using SharedVector = std::shared_ptr<std::vector<T>>;

    template <typename T>
    class BasicTypeReader : public IElementReader {
      private:
        SharedVector<T> m_data;

      public:
        BasicTypeReader( std::string name )
            : IElementReader( name ), m_data( std::make_shared<std::vector<T>>() ) {}

        void read( BinaryBuffer& buffer ) override { m_data->push_back( buffer.read<T>() ); }

        py::object data() const override { return make_array( m_data ); }
    };

    template <>
    class BasicTypeReader<bool> : public IElementReader {
      private:
        SharedVector<uint8_t> m_data;

      public:
        BasicTypeReader( std::string name )
            : IElementReader( name ), m_data( std::make_shared<std::vector<uint8_t>>() ) {}

        void read( BinaryBuffer& buffer ) override {
            m_data->push_back( buffer.read<uint8_t>() != 0 );
        }

        py::object data() const override { return make_array( m_data ); }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class TObjectReader : public IElementReader {
      private:
        const bool m_keep_data;
        SharedVector<int32_t> m_unique_id;
        SharedVector<uint32_t> m_bits;
        SharedVector<uint16_t> m_pidf;
        SharedVector<int64_t> m_pidf_offsets;

      public:
        TObjectReader( std::string name, bool keep_data )
            : IElementReader( name )
            , m_keep_data( keep_data )
            , m_unique_id( std::make_shared<std::vector<int32_t>>() )
            , m_bits( std::make_shared<std::vector<uint32_t>>() )
            , m_pidf( std::make_shared<std::vector<uint16_t>>() )
            , m_pidf_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) ) {}

        void read( BinaryBuffer& buffer ) override {
            buffer.skip_fVersion();
            auto fUniqueID = buffer.read<int32_t>();
            auto fBits     = buffer.read<uint32_t>();

            if ( fBits & ( BinaryBuffer::kIsReferenced ) )
            {
                if ( m_keep_data ) m_pidf->push_back( buffer.read<uint16_t>() );
                else buffer.skip( 2 );
            }

            if ( m_keep_data )
            {
                m_unique_id->push_back( fUniqueID );
                m_bits->push_back( fBits );
                m_pidf_offsets->push_back( m_pidf->size() );
            }
        }

        py::object data() const override {
            if ( !m_keep_data ) return py::none();

            auto unique_id_array = make_array( m_unique_id );
            auto bits_array      = make_array( m_bits );
            auto pidf_array      = make_array( m_pidf );
            auto pidf_offsets    = make_array( m_pidf_offsets );
            return py::make_tuple( unique_id_array, bits_array, pidf_array, pidf_offsets );
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class TStringReader : public IElementReader {
      private:
        const bool m_with_header;
        SharedVector<uint8_t> m_data;
        SharedVector<int64_t> m_offsets;

      public:
        TStringReader( std::string name, bool with_header )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_data( std::make_shared<std::vector<uint8_t>>() )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) ) {}

        void read( BinaryBuffer& buffer ) override {
            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
            m_offsets->push_back( m_data->size() );
        }

        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count < 0 )
                throw std::runtime_error(
                    "TStringReader::read_many with negative count not supported!" );

            if ( count == 0 ) return 0;

            if ( m_with_header )
            {
                auto fNBytes  = buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();
            }

            for ( auto i = 0; i < count; i++ ) { read( buffer ); }
            return count;
        }

        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
            if ( buffer.get_cursor() == end_pos ) return 0;

            if ( m_with_header )
            {
                auto fNBytes  = buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();
            }

            uint32_t cur_count = 0;
            while ( buffer.get_cursor() < end_pos )
            {
                read( buffer );
                cur_count++;
            }
            return cur_count;
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto data_array    = make_array( m_data );
            return py::make_tuple( offsets_array, data_array );
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class STLSeqReader : public IElementReader {
      private:
        const bool m_with_header;
        const int m_objwise_or_memberwise{ -1 }; // -1: auto, 0: obj-wise, 1: member-wise
        SharedReader m_element_reader;
        SharedVector<int64_t> m_offsets;

      public:
        STLSeqReader( std::string name, bool with_header, int objwise_or_memberwise,
                      SharedReader element_reader )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_objwise_or_memberwise( objwise_or_memberwise )
            , m_element_reader( element_reader )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) ) {}

        void check_objwise_memberwise( const bool is_memberwise ) {
            if ( m_objwise_or_memberwise == 0 && is_memberwise )
                throw std::runtime_error( "STLSeqReader(" + name() +
                                          "): Expect obj-wise, got member-wise!" );
            if ( m_objwise_or_memberwise == 1 && !is_memberwise )
                throw std::runtime_error( "STLSeqReader(" + name() +
                                          "): Expect member-wise, got obj-wise!" );
        }

        void read_body( BinaryBuffer& buffer, bool is_memberwise ) {
            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            debug_printf( "STLSeqReader(%s): reading body, is_memberwise=%d, fSize=%d\n",
                          m_name.c_str(), is_memberwise, fSize );
            debug_printf( buffer );

            if ( is_memberwise ) m_element_reader->read_many_memberwise( buffer, fSize );
            else m_element_reader->read_many( buffer, fSize );
        }

        void read( BinaryBuffer& buffer ) override {
            buffer.read_fNBytes();
            auto fVersion      = buffer.read_fVersion();
            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            if ( is_memberwise ) buffer.skip( 2 );
            read_body( buffer, is_memberwise );
        }

        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLSeqReader::read with negative count only "
                                              "supported when with_header is true!" );

                auto fNBytes       = buffer.read_fNBytes();
                auto fVersion      = buffer.read_fVersion();
                bool is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
                if ( is_memberwise ) buffer.skip( 2 );
                auto end_pos = buffer.get_cursor() + fNBytes - 2; //

                uint32_t cur_count = 0;
                while ( buffer.get_cursor() < end_pos )
                {
                    read_body( buffer, is_memberwise );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                bool is_memberwise = m_objwise_or_memberwise == 1;
                if ( m_with_header )
                {
                    buffer.read_fNBytes();
                    auto fVersion = buffer.read_fVersion();
                    is_memberwise = fVersion & kStreamedMemberWise;
                    check_objwise_memberwise( is_memberwise );
                }
                if ( is_memberwise ) buffer.skip( 2 );

                for ( auto i = 0; i < count; i++ ) { read_body( buffer, is_memberwise ); }
                return count;
            }
        }

        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
            if ( buffer.get_cursor() == end_pos ) return 0;
            bool is_memberwise = m_objwise_or_memberwise == 1;
            if ( m_with_header )
            {
                auto fNBytes  = buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();
                is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
            }
            if ( is_memberwise ) buffer.skip( 2 );

            uint32_t cur_count = 0;
            while ( buffer.get_cursor() < end_pos )
            {
                read_body( buffer, is_memberwise );
                cur_count++;
            }
            return cur_count;
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto elements_data = m_element_reader->data();
            return py::make_tuple( offsets_array, elements_data );
        }
    };

    class STLMapReader : public IElementReader {
      private:
        const bool m_with_header;
        const int m_objwise_or_memberwise{ -1 }; // -1: auto, 0: obj-wise, 1: member-wise
        SharedVector<int64_t> m_offsets;
        SharedReader m_key_reader;
        SharedReader m_value_reader;

      public:
        STLMapReader( std::string name, bool with_header, int objwise_or_memberwise,
                      SharedReader key_reader, SharedReader value_reader )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_objwise_or_memberwise( objwise_or_memberwise )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
            , m_key_reader( key_reader )
            , m_value_reader( value_reader ) {}

        void check_objwise_memberwise( const bool is_memberwise ) {
            if ( m_objwise_or_memberwise == 0 && is_memberwise )
                throw std::runtime_error( "STLMapReader(" + name() +
                                          "): Expect obj-wise, got member-wise!" );
            if ( m_objwise_or_memberwise == 1 && !is_memberwise )
                throw std::runtime_error( "STLMapReader(" + name() +
                                          "): Expect member-wise, got obj-wise!" );
        }

        void read_body( BinaryBuffer& buffer, bool is_memberwise ) {
            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            if ( is_memberwise )
            {
                m_key_reader->read_many( buffer, fSize );
                m_value_reader->read_many( buffer, fSize );
            }
            else
            {
                for ( auto i = 0; i < fSize; i++ )
                {
                    m_key_reader->read( buffer );
                    m_value_reader->read( buffer );
                }
            }
        }

        void read( BinaryBuffer& buffer ) override {
            buffer.read_fNBytes();
            auto fVersion = buffer.read_fVersion();
            buffer.skip( 6 );

            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            read_body( buffer, is_memberwise );
        }

        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLMapReader::read with negative count only "
                                              "supported when with_header is true!" );

                auto fNBytes  = buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();
                buffer.skip( 6 );
                bool is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );

                auto end_pos = buffer.get_cursor() + fNBytes - 8;

                uint32_t cur_count = 0;
                while ( buffer.get_cursor() < end_pos )
                {
                    read_body( buffer, is_memberwise );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                bool is_memberwise = m_objwise_or_memberwise == 1;
                if ( m_with_header )
                {
                    auto fNBytes  = buffer.read_fNBytes();
                    auto fVersion = buffer.read_fVersion();
                    buffer.skip( 6 ); // skip 6 bytes

                    is_memberwise = fVersion & kStreamedMemberWise;
                    check_objwise_memberwise( is_memberwise );
                }

                for ( auto i = 0; i < count; i++ ) { read_body( buffer, is_memberwise ); }
                return count;
            }
        }

        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
            if ( buffer.get_cursor() == end_pos ) return 0;

            bool is_memberwise = m_objwise_or_memberwise == 1;
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();
                buffer.skip( 6 ); // skip 6 bytes

                is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
            }

            uint32_t cur_count = 0;
            while ( buffer.get_cursor() < end_pos )
            {
                read_body( buffer, is_memberwise );
                cur_count++;
            }
            return cur_count;
        }

        virtual uint32_t read_many_memberwise( BinaryBuffer& buffer,
                                               const int64_t count ) override {
            if ( count < 0 )
            {
                std::stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            bool is_memberwise = true;
            check_objwise_memberwise( is_memberwise );
            return read_many( buffer, count );
        }

        py::object data() const override {
            auto offsets_array     = make_array( m_offsets );
            py::object keys_data   = m_key_reader->data();
            py::object values_data = m_value_reader->data();
            return py::make_tuple( offsets_array, keys_data, values_data );
        }
    };

    class STLStringReader : public IElementReader {
      private:
        const bool m_with_header;
        SharedVector<int64_t> m_offsets;
        SharedVector<uint8_t> m_data;

      public:
        STLStringReader( std::string name, bool with_header )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
            , m_data( std::make_shared<std::vector<uint8_t>>() ) {}

        void read_body( BinaryBuffer& buffer ) {
            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            m_offsets->push_back( m_offsets->back() + fSize );
            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
        }

        void read( BinaryBuffer& buffer ) override {
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }
            read_body( buffer );
        }

        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLStringReader::read with negative count only "
                                              "supported when with_header is true!" );
                auto fNBytes  = buffer.read_fNBytes();
                auto fVersion = buffer.read_fVersion();

                auto end_pos       = buffer.get_cursor() + fNBytes - 2; // -2 for fVersion
                uint32_t cur_count = 0;
                while ( buffer.get_cursor() < end_pos )
                {
                    read_body( buffer );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                if ( m_with_header )
                {
                    auto fNBytes  = buffer.read_fNBytes();
                    auto fVersion = buffer.read_fVersion();
                }

                for ( auto i = 0; i < count; i++ ) { read_body( buffer ); }
                return count;
            }
        }

        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
            if ( buffer.get_cursor() == end_pos ) return 0;
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }

            int32_t cur_count = 0;
            while ( buffer.get_cursor() < end_pos )
            {
                read_body( buffer );
                cur_count++;
            }
            return cur_count;
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto data_array    = make_array( m_data );

            return py::make_tuple( offsets_array, data_array );
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    template <typename T>
    class TArrayReader : public IElementReader {
      private:
        SharedVector<int64_t> m_offsets;
        SharedVector<T> m_data;

      public:
        TArrayReader( std::string name )
            : IElementReader( name )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
            , m_data( std::make_shared<std::vector<T>>() ) {}

        void read( BinaryBuffer& buffer ) override {
            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );
            for ( auto i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<T>() ); }
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto data_array    = make_array( m_data );
            return py::make_tuple( offsets_array, data_array );
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */
    class GroupReader : public IElementReader {
      private:
        std::vector<SharedReader> m_element_readers;

      public:
        GroupReader( std::string name, std::vector<SharedReader> element_readers )
            : IElementReader( name ), m_element_readers( element_readers ) {}

        void read( BinaryBuffer& buffer ) override {
            for ( auto& reader : m_element_readers )
            {
                debug_printf( "GroupReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( buffer );
                reader->read( buffer );
            }
        }

        uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count < 0 )
            {
                std::stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "GroupReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( buffer );
                reader->read_many( buffer, count );
            }
            return count;
        }

        py::object data() const override {
            py::list res;
            for ( auto& reader : m_element_readers ) { res.append( reader->data() ); }
            return res;
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */
    class AnyClassReader : public IElementReader {
      private:
        std::vector<SharedReader> m_element_readers;

      public:
        AnyClassReader( std::string name, std::vector<SharedReader> element_readers )
            : IElementReader( name ), m_element_readers( element_readers ) {}

        void read( BinaryBuffer& buffer ) override {
            auto fNBytes  = buffer.read_fNBytes();
            auto fVersion = buffer.read_fVersion();

            auto start_pos = buffer.get_cursor();
            auto end_pos   = buffer.get_cursor() + fNBytes - 2; // -2 for fVersion

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "AnyClassReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( buffer );
                reader->read( buffer );
            }

            if ( buffer.get_cursor() != end_pos )
            {
                std::stringstream msg;
                msg << "AnyClassReader: Invalid read length for " << name() << "! Expect "
                    << end_pos - start_pos << ", got " << buffer.get_cursor() - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }

        uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count < 0 )
            {
                std::stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "AnyClassReader %s: reading memberwise %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( buffer );
                reader->read_many( buffer, count );
            }

            return count;
        }

        py::object data() const override {
            py::list res;
            for ( auto& reader : m_element_readers ) { res.append( reader->data() ); }
            return res;
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class ObjectHeaderReader : public IElementReader {
      private:
        SharedReader m_element_reader;

      public:
        ObjectHeaderReader( std::string name, SharedReader element_reader )
            : IElementReader( name ), m_element_reader( element_reader ) {}

        void read( BinaryBuffer& buffer ) override {
            auto nbytes  = buffer.read_fNBytes();
            auto end_pos = buffer.get_cursor() + nbytes;

            auto fTag = buffer.read<int32_t>();
            if ( fTag == -1 ) { auto fTypename = buffer.read_null_terminated_string(); }

            auto start_pos = buffer.get_cursor();
            m_element_reader->read( buffer );

            if ( buffer.get_cursor() != end_pos )
            {
                std::stringstream msg;
                msg << "ObjectHeaderReader: Invalid read length for "
                    << m_element_reader->name() << "! Expect " << end_pos - start_pos
                    << ", got " << buffer.get_cursor() - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }

        py::object data() const override { return m_element_reader->data(); }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class CStyleArrayReader : public IElementReader {
      private:
        const int64_t m_flat_size;
        SharedVector<int64_t> m_offsets;
        SharedReader m_element_reader;

      public:
        CStyleArrayReader( std::string name, const int64_t flat_size,
                           SharedReader element_reader )
            : IElementReader( name )
            , m_flat_size( flat_size )
            , m_offsets( std::make_shared<std::vector<int64_t>>( 1, 0 ) )
            , m_element_reader( element_reader ) {}

        void read( BinaryBuffer& buffer ) override {
            debug_printf( "CStyleArrayReader(%s) with flat_size %ld\n", m_name.c_str(),
                          m_flat_size );
            debug_printf( buffer );

            if ( m_flat_size > 0 ) { m_element_reader->read_many( buffer, m_flat_size ); }
            else
            {
                // get end-position
                auto n_entries     = buffer.entries();
                auto start_pos     = buffer.get_data();
                auto entry_offsets = buffer.get_offsets();
                auto cursor_pos    = buffer.get_cursor();
                auto entry_end = std::find_if( entry_offsets, entry_offsets + n_entries + 1,
                                               [start_pos, cursor_pos]( uint32_t offset ) {
                                                   return start_pos + offset > cursor_pos;
                                               } );
                auto end_pos   = start_pos + *entry_end;
                uint32_t count = m_element_reader->read_until( buffer, end_pos );
                m_offsets->push_back( m_offsets->back() + count );
                debug_printf( "CStyleArrayReader(%s) read %d elements\n", m_name.c_str(),
                              count );
            }
        }

        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( m_flat_size < 0 )
            {
                std::stringstream msg;
                msg << name() << "::read_many only supported when flat_size > 0!";
                throw std::runtime_error( msg.str() );
            }
            if ( count < 0 )
            {
                std::stringstream msg;
                msg << name() << "::read_many with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto i = 0; i < count; i++ )
                m_element_reader->read_many( buffer, m_flat_size );

            return count;
        }

        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
            throw std::runtime_error( "CStyleArrayReader::read with end_pos not supported!" );
        }

        py::object data() const override {
            if ( m_flat_size > 0 ) return m_element_reader->data();
            else
            {
                auto offsets_array = make_array( m_offsets );
                auto elements_data = m_element_reader->data();
                return py::make_tuple( offsets_array, elements_data );
            }
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class EmptyReader : public IElementReader {
      public:
        EmptyReader( std::string name ) : IElementReader( name ) {}

        void read( BinaryBuffer& ) override {}
        py::object data() const override { return py::none(); }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    py::object py_read_data( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets,
                             SharedReader reader ) {
        BinaryBuffer buffer( data, offsets );
        for ( auto i_evt = 0; i_evt < buffer.entries(); i_evt++ )
        {
            auto start_pos = buffer.get_cursor();
            reader->read( buffer );
            auto end_pos = buffer.get_cursor();

            if ( end_pos - start_pos !=
                 buffer.get_offsets()[i_evt + 1] - buffer.get_offsets()[i_evt] )
            {
                std::stringstream msg;
                msg << "py_read_data: Invalid read length for " << reader->name()
                    << " at event " << i_evt << "! Expect "
                    << buffer.get_offsets()[i_evt + 1] - buffer.get_offsets()[i_evt]
                    << ", got " << end_pos - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }
        return reader->data();
    }

    PYBIND11_MODULE( cpp, m ) {
        m.doc() = "C++ module for uproot-custom";

        m.def( "read_data", &py_read_data, "Read data from a binary buffer", py::arg( "data" ),
               py::arg( "offsets" ), py::arg( "reader" ) );

        py::class_<IElementReader, SharedReader>( m, "IElementReader" )
            .def( "name", &IElementReader::name, "Get the name of the reader" );

        // Basic type readers
        register_reader<BasicTypeReader<uint8_t>>( m, "UInt8Reader" );
        register_reader<BasicTypeReader<uint16_t>>( m, "UInt16Reader" );
        register_reader<BasicTypeReader<uint32_t>>( m, "UInt32Reader" );
        register_reader<BasicTypeReader<uint64_t>>( m, "UInt64Reader" );
        register_reader<BasicTypeReader<int8_t>>( m, "Int8Reader" );
        register_reader<BasicTypeReader<int16_t>>( m, "Int16Reader" );
        register_reader<BasicTypeReader<int32_t>>( m, "Int32Reader" );
        register_reader<BasicTypeReader<int64_t>>( m, "Int64Reader" );
        register_reader<BasicTypeReader<float>>( m, "FloatReader" );
        register_reader<BasicTypeReader<double>>( m, "DoubleReader" );
        register_reader<BasicTypeReader<bool>>( m, "BoolReader" );

        // STL readers
        register_reader<STLSeqReader, bool, int, SharedReader>( m, "STLSeqReader" );
        register_reader<STLMapReader, bool, int, SharedReader, SharedReader>( m,
                                                                              "STLMapReader" );
        register_reader<STLStringReader, bool>( m, "STLStringReader" );

        // TArrayReader
        register_reader<TArrayReader<int8_t>>( m, "TArrayCReader" );
        register_reader<TArrayReader<int16_t>>( m, "TArraySReader" );
        register_reader<TArrayReader<int32_t>>( m, "TArrayIReader" );
        register_reader<TArrayReader<int64_t>>( m, "TArrayLReader" );
        register_reader<TArrayReader<float>>( m, "TArrayFReader" );
        register_reader<TArrayReader<double>>( m, "TArrayDReader" );

        // Other readers
        register_reader<TStringReader, bool>( m, "TStringReader" );
        register_reader<TObjectReader, bool>( m, "TObjectReader" );
        register_reader<GroupReader, std::vector<SharedReader>>( m, "GroupReader" );
        register_reader<AnyClassReader, std::vector<SharedReader>>( m, "AnyClassReader" );
        register_reader<ObjectHeaderReader, SharedReader>( m, "ObjectHeaderReader" );
        register_reader<CStyleArrayReader, int64_t, SharedReader>( m, "CStyleArrayReader" );
        register_reader<EmptyReader>( m, "EmptyReader" );
    }

} // namespace uproot
