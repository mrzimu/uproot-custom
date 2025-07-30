#include <pybind11/gil.h>
#include <pybind11/pybind11.h>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

#ifdef UPROOT_DEBUG
#    define PRINT_BUFFER( buffer )                                                            \
        {                                                                                     \
            std::cout << "[DEBUG] ";                                                          \
            for ( int i = 0; i < 80; i++ )                                                    \
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

namespace uproot {
    template <typename T>
    using SharedVector = std::shared_ptr<std::vector<T>>;

    template <typename T>
    class BasicTypeReader : public IElementReader {
      public:
        BasicTypeReader( std::string name )
            : IElementReader( name ), m_data( std::make_shared<std::vector<T>>() ) {}

        void read( BinaryBuffer& buffer ) override { m_data->push_back( buffer.read<T>() ); }

        py::object data() const override { return make_array( m_data ); }

      private:
        SharedVector<T> m_data;
    };

    template <>
    class BasicTypeReader<bool> : public IElementReader {
      public:
        BasicTypeReader( std::string name )
            : IElementReader( name ), m_data( std::make_shared<std::vector<uint8_t>>() ) {}

        void read( BinaryBuffer& buffer ) override {
            m_data->push_back( buffer.read<uint8_t>() != 0 );
        }

        py::object data() const override { return make_array( m_data ); }

      private:
        SharedVector<uint8_t> m_data;
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class TObjectReader : public IElementReader {

      public:
        TObjectReader( std::string name ) : IElementReader( name ) {}

        void read( BinaryBuffer& buffer ) override { buffer.skip_TObject(); }

        py::object data() const override { return py::none(); }

      private:
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class TStringReader : public IElementReader {
      public:
        TStringReader( std::string name )
            : IElementReader( name )
            , m_data( std::make_shared<std::vector<uint8_t>>() )
            , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) ) {}

        void read( BinaryBuffer& buffer ) override {
            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
            m_offsets->push_back( m_data->size() );
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto data_array    = make_array( m_data );
            return py::make_tuple( offsets_array, data_array );
        }

      private:
        SharedVector<uint8_t> m_data;
        SharedVector<uint32_t> m_offsets;
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class STLSeqReader : public IElementReader {
      public:
        STLSeqReader( std::string name, bool with_header, SharedReader element_reader )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_element_reader( element_reader )
            , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) ) {}

        void read( BinaryBuffer& buffer ) override {
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }

            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );
            for ( auto i = 0; i < fSize; i++ ) m_element_reader->read( buffer );
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto elements_data = m_element_reader->data();
            return py::make_tuple( offsets_array, elements_data );
        }

      private:
        const bool m_with_header;
        SharedReader m_element_reader;
        SharedVector<uint32_t> m_offsets;
    };

    class STLMapReader : public IElementReader {
      public:
        STLMapReader( std::string name, bool with_header, SharedReader key_reader,
                      SharedReader value_reader )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) )
            , m_key_reader( key_reader )
            , m_value_reader( value_reader ) {}

        void read( BinaryBuffer& buffer ) override {
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.skip( 8 );
            }

            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            if ( m_with_header )
            {
                for ( auto i = 0; i < fSize; i++ ) m_key_reader->read( buffer );
                for ( auto i = 0; i < fSize; i++ ) m_value_reader->read( buffer );
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

        py::object data() const override {
            auto offsets_array     = make_array( m_offsets );
            py::object keys_data   = m_key_reader->data();
            py::object values_data = m_value_reader->data();
            return py::make_tuple( offsets_array, keys_data, values_data );
        }

      private:
        const bool m_with_header;

        SharedVector<uint32_t> m_offsets;
        SharedReader m_key_reader;
        SharedReader m_value_reader;
    };

    class STLStringReader : public IElementReader {
      public:
        STLStringReader( std::string name, bool with_header )
            : IElementReader( name )
            , m_with_header( with_header )
            , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) )
            , m_data( std::make_shared<std::vector<uint8_t>>() ) {}

        void read( BinaryBuffer& buffer ) override {
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }

            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            m_offsets->push_back( m_offsets->back() + fSize );
            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
        }

        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto data_array    = make_array( m_data );

            return py::make_tuple( offsets_array, data_array );
        }

      private:
        const bool m_with_header;

        SharedVector<uint32_t> m_offsets;
        SharedVector<uint8_t> m_data;
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    template <typename T>
    class TArrayReader : public IElementReader {
      public:
        TArrayReader( std::string name )
            : IElementReader( name )
            , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) )
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

      private:
        SharedVector<uint32_t> m_offsets;
        SharedVector<T> m_data;
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class ObjectReader : public IElementReader {
      public:
        ObjectReader( std::string name, std::vector<SharedReader> element_readers )
            : IElementReader( name ), m_element_readers( element_readers ) {}

        void read( BinaryBuffer& buffer ) override {
#ifdef UPROOT_DEBUG
            std::cout << "BaseObjectReader " << m_name << "::read(): " << std::endl;
            for ( int i = 0; i < 40; i++ ) std::cout << (int)buffer.get_cursor()[i] << " ";
            std::cout << std::endl << std::endl;
#endif
            buffer.read_fNBytes();
            buffer.read_fVersion();
            for ( auto& reader : m_element_readers )
            {
#ifdef UPROOT_DEBUG
                std::cout << "BaseObjectReader " << m_name << ": " << reader->name() << ":"
                          << std::endl;
                for ( int i = 0; i < 40; i++ ) std::cout << (int)buffer.get_cursor()[i] << " ";
                std::cout << std::endl << std::endl;
#endif
                reader->read( buffer );
            }
        }

        py::object data() const override {
            py::list res;
            for ( auto& reader : m_element_readers ) { res.append( reader->data() ); }
            return res;
        }

      private:
        std::vector<SharedReader> m_element_readers;
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    class CArrayReader : public IElementReader {
      public:
        CArrayReader( std::string name, bool is_obj, const uint32_t flat_size,
                      SharedReader element_reader )
            : IElementReader( name )
            , m_is_obj( is_obj )
            , m_flat_size( flat_size )
            , m_element_reader( element_reader ) {}

        void read( BinaryBuffer& buffer ) override {
            if ( m_is_obj )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }
            for ( auto i = 0; i < m_flat_size; i++ ) m_element_reader->read( buffer );
        }

        py::object data() const override { return m_element_reader->data(); }

      private:
        bool m_is_obj;
        const uint32_t m_flat_size;
        SharedReader m_element_reader;
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
        for ( auto i_evt = 0; i_evt < buffer.entries(); i_evt++ ) { reader->read( buffer ); }
        return reader->data();
    }

    PYBIND11_MODULE( _cpp, m ) {
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
        register_reader<STLSeqReader, bool, SharedReader>( m, "STLSeqReader" );
        register_reader<STLMapReader, bool, SharedReader, SharedReader>( m, "STLMapReader" );
        register_reader<STLStringReader, bool>( m, "STLStringReader" );

        // TArrayReader
        register_reader<TArrayReader<int8_t>>( m, "TArrayCReader" );
        register_reader<TArrayReader<int16_t>>( m, "TArraySReader" );
        register_reader<TArrayReader<int32_t>>( m, "TArrayIReader" );
        register_reader<TArrayReader<int64_t>>( m, "TArrayLReader" );
        register_reader<TArrayReader<float>>( m, "TArrayFReader" );
        register_reader<TArrayReader<double>>( m, "TArrayDReader" );

        // Other readers
        register_reader<TStringReader>( m, "TStringReader" );
        register_reader<TObjectReader>( m, "TObjectReader" );
        register_reader<ObjectReader, std::vector<SharedReader>>( m, "ObjectReader" );
        register_reader<CArrayReader, bool, uint32_t, SharedReader>( m, "CArrayReader" );
        register_reader<EmptyReader>( m, "EmptyReader" );
    }

} // namespace uproot
