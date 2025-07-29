#include <pybind11/gil.h>
#include <pybind11/pybind11.h>

#include "uproot-custom.hh"

py::object py_read_data( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets,
                         IElementReader reader ) {
    BinaryBuffer buffer( data, offsets );
    // py::gil_scoped_release release;
    for ( auto i_evt = 0; i_evt < buffer.entries(); i_evt++ ) { reader->read( buffer ); }
    // py::gil_scoped_acquire acquire;
    return reader->data();
}

PYBIND11_MODULE( _cpp, m ) {
    m.doc() = "Custom C++ module for Uproot";

    m.def( "read_data", &py_read_data, "Read data from a binary buffer", py::arg( "data" ),
           py::arg( "offsets" ), py::arg( "reader" ) );

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
    register_reader<STLMapReader, bool, IElementReader, IElementReader>( m, "STLMapReader" );
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