#include <iostream>
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

PYBIND11_MODULE( my_reader_cpp, m ) {
    register_reader<OverrideStreamerReader>( m, "OverrideStreamerReader" );
}