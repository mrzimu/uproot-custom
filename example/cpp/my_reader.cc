#include <cstdint>
#include <memory>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

using namespace uproot;

class OverrideStreamerReader : public IElementReader {
  public:
    OverrideStreamerReader( std::string name )
        : IElementReader( name )
        , m_data_ints( std::make_shared<std::vector<int>>() )
        , m_data_doubles( std::make_shared<std::vector<double>>() ) {}

    void read( BinaryBuffer& buffer ) {
        // Skip TObject header
        buffer.skip_TObject();

        // Read integer value
        m_data_ints->push_back( buffer.read<int>() );

        // Read a custom added mask value
        auto mask = buffer.read<uint32_t>();
        if ( mask != 0x12345678 )
        {
            throw std::runtime_error( "Error: Unexpected mask value: " +
                                      std::to_string( mask ) );
        }

        // Read double value
        m_data_doubles->push_back( buffer.read<double>() );
    }

    py::object data() const {
        auto int_array    = make_array( m_data_ints );
        auto double_array = make_array( m_data_doubles );
        return py::make_tuple( int_array, double_array );
    }

  private:
    const std::string m_name;
    std::shared_ptr<std::vector<int>> m_data_ints;
    std::shared_ptr<std::vector<double>> m_data_doubles;
};

class TObjArrayReader : public IElementReader {
  private:
    SharedReader m_element_reader;
    std::shared_ptr<std::vector<uint32_t>> m_offsets;

  public:
    TObjArrayReader( std::string name, SharedReader element_reader )
        : IElementReader( name )
        , m_element_reader( element_reader )
        , m_offsets( std::make_shared<std::vector<uint32_t>>( 1, 0 ) ) {}

    void read( BinaryBuffer& buffer ) override final {
        buffer.skip_fNBytes();
        buffer.skip_fVersion();
        buffer.skip_fVersion();
        buffer.skip( 4 ); // fUniqueID
        buffer.skip( 4 ); // fBits

        buffer.skip( 1 ); // fName
        auto fSize = buffer.read<uint32_t>();
        buffer.skip( 4 ); // fLowerBound

        m_offsets->push_back( m_offsets->back() + fSize );
        m_element_reader->read( buffer, fSize );
    }

    py::object data() const override final {
        auto offsets_array      = make_array( m_offsets );
        py::object element_data = m_element_reader->data();
        return py::make_tuple( offsets_array, element_data );
    }
};

PYBIND11_MODULE( my_reader_cpp, m ) {
    register_reader<OverrideStreamerReader>( m, "OverrideStreamerReader" );
    register_reader<TObjArrayReader, SharedReader>( m, "TObjArrayReader" );
}