#include <pybind11/gil.h>
#include <pybind11/pybind11.h>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

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

namespace uproot {

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

      public:
        TObjectReader( std::string name ) : m_name( name ) {}

        const std::string name() const { return m_name; }

        void read( BinaryBuffer& buffer ) { buffer.skip_TObject(); }

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

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    py::object py_read_data( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets,
                             IElementReader reader ) {
        BinaryBuffer buffer( data, offsets );
        // py::gil_scoped_release release;
        for ( auto i_evt = 0; i_evt < buffer.entries(); i_evt++ ) { reader->read( buffer ); }
        // py::gil_scoped_acquire acquire;
        return reader->data();
    }

    std::string get_reader_name( IElementReader reader ) { return reader->name(); }

    PYBIND11_MODULE( _cpp, m ) {
        m.doc() = "C++ module for uproot-custom";

        m.def( "read_data", &py_read_data, "Read data from a binary buffer", py::arg( "data" ),
               py::arg( "offsets" ), py::arg( "reader" ) );

        m.def( "get_reader_name", &get_reader_name, "Get the name of the reader",
               py::arg( "reader" ) );

        py::class_<IElementReader>( m, "IElementReader" );

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
        register_reader<STLSeqReader, bool, IElementReader>( m, "STLSeqReader" );
        register_reader<STLMapReader, bool, IElementReader, IElementReader>( m,
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
        register_reader<TStringReader>( m, "TStringReader" );
        register_reader<TObjectReader>( m, "TObjectReader" );
        register_reader<ObjectReader, std::vector<IElementReader>>( m, "ObjectReader" );
        register_reader<CArrayReader, bool, uint32_t, IElementReader>( m, "CArrayReader" );
        register_reader<EmptyReader>( m, "EmptyReader" );
    }

} // namespace uproot
