#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <stdexcept>
#include <variant>
#include <vector>

#include <pybind11/gil.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>

#include "uproot-custom/uproot-custom.hh"

namespace uproot {
    using std::pair;
    using std::shared_ptr;
    using std::string;
    using std::stringstream;
    using std::vector;

    template <typename T>
    using SharedVector = shared_ptr<vector<T>>;

    /**
     * @brief Reader for primitive types
     *
     * @tparam T Primitive type
     */
    template <typename T>
    class PrimitiveReader : public IReader {
      private:
        SharedVector<T> m_data; ///< Store the read data

      public:
        /**
         * @brief Construct a new PrimitiveReader object
         *
         * @param name Name of the reader
         */
        PrimitiveReader( string name )
            : IReader( name ), m_data( std::make_shared<vector<T>>() ) {}

        /**
         * @brief Read a value from the stream and store it. Only reads one value at a time.
         *
         * @param stream The binary stream to read from
         */
        void read( BinaryStream& stream ) override { m_data->push_back( stream.read<T>() ); }

        /**
         * @brief Get the read data as a numpy array
         *
         * @return Numpy array containing the read data
         */
        py::object data() const override { return make_array( m_data ); }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Reader for TObject.
     */
    class TObjectReader : public IReader {
      private:
        const bool m_keep_data;               ///< Whether to keep the read data
        SharedVector<int32_t> m_unique_id;    ///< Store fUniqueID values
        SharedVector<uint32_t> m_bits;        ///< Store fBits values
        SharedVector<uint16_t> m_pidf;        ///< Store pidf values
        SharedVector<int64_t> m_pidf_offsets; ///< Store offsets for pidf

      public:
        /**
         * @brief Construct a new TObjectReader object
         *
         * @param name Name of the reader
         * @param keep_data Whether to keep the read data
         */
        TObjectReader( string name, bool keep_data )
            : IReader( name )
            , m_keep_data( keep_data )
            , m_unique_id( std::make_shared<vector<int32_t>>() )
            , m_bits( std::make_shared<vector<uint32_t>>() )
            , m_pidf( std::make_shared<vector<uint16_t>>() )
            , m_pidf_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) ) {}

        /**
         * @brief Read a TObject from the stream. A TObject contains `fVersion` (int16_t),
         * `fUniqueID` (int32_t), `fBits` (uint32_t). If `fBits & kIsReferenced`, then a `pidf`
         * (uint16_t) follows. If @ref m_keep_data is true, the read data
         * will be stored.
         *
         * @param stream The binary stream to read from
         */
        void read( BinaryStream& stream ) override {
            stream.skip_fVersion();
            auto fUniqueID = stream.read<int32_t>();
            auto fBits     = stream.read<uint32_t>();

            if ( fBits & ( BinaryStream::kIsReferenced ) )
            {
                if ( m_keep_data ) m_pidf->push_back( stream.read<uint16_t>() );
                else stream.skip( 2 );
            }

            if ( m_keep_data )
            {
                m_unique_id->push_back( fUniqueID );
                m_bits->push_back( fBits );
                m_pidf_offsets->push_back( m_pidf->size() );
            }
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return If @ref m_keep_data is true, returns a tuple of numpy arrays: (unique_id,
         * bits, pidf, pidf_offsets). Otherwise, returns None.
         */
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

    /**
     * @brief Reader for TString.
     */
    class TStringReader : public IReader {
      private:
        const bool m_with_header;     ///< Whether the TString has a `fNBytes+fVersion` header
        SharedVector<uint8_t> m_data; ///< Store the string data
        SharedVector<int64_t> m_offsets; ///< Store the offsets for each string

      public:
        /**
         * @brief Construct a new TStringReader object.
         *
         * @param name Name of the reader.
         * @param with_header Whether the TString has a `fNBytes+fVersion` header.
         */
        TStringReader( string name, bool with_header )
            : IReader( name )
            , m_with_header( with_header )
            , m_data( std::make_shared<vector<uint8_t>>() )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) ) {}

        /**
         * @brief Read a TString from the stream. A TString starts with a uint8_t size. If the
         * size is 255, then a uint32_t size follows. Then the string data follows. It @ref
         * m_with_header is true, read a `fNBytes+fVersion` header before reading the TString.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            uint32_t fSize = stream.read<uint8_t>();
            if ( fSize == 255 ) fSize = stream.read<uint32_t>();

            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( stream.read<uint8_t>() ); }
            m_offsets->push_back( m_data->size() );
        }

        /**
         * @brief Read multiple TStrings from the stream. If @ref m_with_header is true, only
         * read `fNBytes+fVersion` header once before reading multiple TStrings.
         *
         * @param stream The binary stream to read from.
         * @param count Number of TStrings to read. If negative, throws an error.
         * @return Number of TStrings read.
         */
        uint32_t read_many( BinaryStream& stream, const int64_t count ) override {
            if ( count < 0 )
                throw std::runtime_error(
                    "TStringReader::read_many with negative count not supported!" );

            if ( count == 0 ) return 0;

            if ( m_with_header )
            {
                auto fNBytes  = stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();
            }

            for ( auto i = 0; i < count; i++ ) { read( stream ); }
            return count;
        }

        /**
         * @brief Read TStrings from the stream until reaching the end position. If @ref
         * m_with_header is true, only read `fNBytes+fVersion` header once before reading
         * TStrings.
         *
         * @param stream The binary stream to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of TStrings read.
         */
        uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) override {
            if ( stream.get_cursor() == end_pos ) return 0;

            if ( m_with_header )
            {
                auto fNBytes  = stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();
            }

            uint32_t cur_count = 0;
            while ( stream.get_cursor() < end_pos )
            {
                read( stream );
                cur_count++;
            }
            return cur_count;
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A tuple of numpy arrays: (offsets, data).
         */
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

    /**
     * @brief Reader for STL sequence types (e.g., std::vector, std::list).
     */
    class STLSeqReader : public IReader {
      private:
        const bool m_with_header; ///< Whether the sequence has a `fNBytes+fVersion` header.
        const int m_objwise_or_memberwise{ -1 }; ///< -1: auto, 0: obj-wise, 1: member-wise
        SharedReader m_element_reader;           ///< Reader for the elements of the sequence.
        SharedVector<int64_t> m_offsets;         ///< Store the offsets for each sequence.

      public:
        /**
         * @brief Construct a new STLSeqReader object.
         *
         * @param name Name of the reader.
         * @param with_header Whether the sequence has a `fNBytes+fVersion` header.
         * @param objwise_or_memberwise Object-wise or member-wise reading mode.
         *        -1: auto, 0: obj-wise, 1: member-wise.
         * @param element_reader Reader for the elements of the sequence.
         */
        STLSeqReader( string name, bool with_header, int objwise_or_memberwise,
                      SharedReader element_reader )
            : IReader( name )
            , m_with_header( with_header )
            , m_objwise_or_memberwise( objwise_or_memberwise )
            , m_element_reader( element_reader )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) ) {}

        /**
         * @brief Check if the reading mode matches the expected mode.
         *
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
        void check_objwise_memberwise( const bool is_memberwise ) {
            if ( m_objwise_or_memberwise == 0 && is_memberwise )
                throw std::runtime_error( "STLSeqReader(" + name() +
                                          "): Expect obj-wise, got member-wise!" );
            if ( m_objwise_or_memberwise == 1 && !is_memberwise )
                throw std::runtime_error( "STLSeqReader(" + name() +
                                          "): Expect member-wise, got obj-wise!" );
        }

        /**
         * @brief Read the element version and checksum from the stream.
         *
         * @param stream The binary stream to read from.
         * @return A tuple of (version, checksum).
         */
        pair<int, uint32_t> read_element_version( BinaryStream& stream ) {
            auto version      = stream.read_fVersion();
            uint32_t checksum = 0;
            if ( version == 0 ) checksum = stream.read<uint32_t>();
            return { version, checksum };
        }

        /**
         * @brief Read the body of the sequence from the stream. First reads the size
         * (uint32_t) of the sequence, then calls @ref m_element_reader to read the elements.
         *
         * @param stream The binary stream to read from.
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
        void read_body( BinaryStream& stream, bool is_memberwise ) {
            auto fSize = stream.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            debug_printf( "STLSeqReader(%s): reading body, is_memberwise=%d, fSize=%d\n",
                          m_name.c_str(), is_memberwise, fSize );
            debug_printf( stream );

            if ( is_memberwise ) m_element_reader->read_many_memberwise( stream, fSize );
            else m_element_reader->read_many( stream, fSize );
        }

        /**
         * @brief Read a sequence from the stream. If @ref m_with_header is true, reads a
         * `fNBytes+fVersion` header. Then calls @ref read_body() to read the sequence body.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            stream.read_fNBytes();
            auto fVersion      = stream.read_fVersion();
            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            if ( is_memberwise ) read_element_version( stream );
            read_body( stream, is_memberwise );
        }

        /**
         * @brief Read multiple sequences from the stream. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header once before reading multiple sequences.
         *
         * @param stream The binary stream to read from.
         * @param count Number of sequences to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of sequences read.
         */
        uint32_t read_many( BinaryStream& stream, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLSeqReader::read with negative count only "
                                              "supported when with_header is true!" );

                auto fNBytes       = stream.read_fNBytes();
                auto end_pos       = stream.get_cursor() + fNBytes;
                auto fVersion      = stream.read_fVersion();
                bool is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
                if ( is_memberwise ) read_element_version( stream );

                uint32_t cur_count = 0;
                while ( stream.get_cursor() < end_pos )
                {
                    read_body( stream, is_memberwise );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                bool is_memberwise = m_objwise_or_memberwise == 1;
                if ( m_with_header )
                {
                    stream.read_fNBytes();
                    auto fVersion = stream.read_fVersion();
                    is_memberwise = fVersion & kStreamedMemberWise;
                    check_objwise_memberwise( is_memberwise );
                }
                if ( is_memberwise ) read_element_version( stream );

                for ( auto i = 0; i < count; i++ ) { read_body( stream, is_memberwise ); }
                return count;
            }
        }

        /**
         * @brief Read sequences from the stream until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header once before reading
         * sequences. If data is stored member-wise, skips 2 bytes after the header.
         *
         * @param stream The binary stream to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of sequences read.
         */
        uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) override {
            if ( stream.get_cursor() == end_pos ) return 0;
            bool is_memberwise = m_objwise_or_memberwise == 1;
            if ( m_with_header )
            {
                auto fNBytes  = stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();
                is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
            }
            if ( is_memberwise ) read_element_version( stream );

            uint32_t cur_count = 0;
            while ( stream.get_cursor() < end_pos )
            {
                read_body( stream, is_memberwise );
                cur_count++;
            }
            return cur_count;
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A tuple contains: (offsets, elements_data).
         */
        py::object data() const override {
            auto offsets_array = make_array( m_offsets );
            auto elements_data = m_element_reader->data();
            return py::make_tuple( offsets_array, elements_data );
        }
    };

    /**
     * @brief Reader for STL map types (e.g., std::map, std::unordered_map).
     */
    class STLMapReader : public IReader {
      private:
        const bool m_with_header; ///< Whether the map has a `fNBytes+fVersion` header.
        const int m_objwise_or_memberwise{ -1 }; ///< -1: auto, 0: obj-wise, 1: member-wise
        SharedVector<int64_t> m_offsets;         ///< Store the offsets for each map.
        SharedReader m_key_reader;               ///< Reader for the keys of the map.
        SharedReader m_value_reader;             ///< Reader for the values of the map.

      public:
        /**
         * @brief Construct a new STLMapReader object.
         *
         * @param name Name of the reader.
         * @param with_header Whether the map has a `fNBytes+fVersion` header.
         * @param objwise_or_memberwise Object-wise or member-wise reading mode.
         *        -1: auto, 0: obj-wise, 1: member-wise.
         * @param key_reader Reader for the keys of the map.
         * @param value_reader Reader for the values of the map.
         */
        STLMapReader( string name, bool with_header, int objwise_or_memberwise,
                      SharedReader key_reader, SharedReader value_reader )
            : IReader( name )
            , m_with_header( with_header )
            , m_objwise_or_memberwise( objwise_or_memberwise )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) )
            , m_key_reader( key_reader )
            , m_value_reader( value_reader ) {}

        /**
         * @brief Check if the reading mode matches the expected mode.
         *
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
        void check_objwise_memberwise( const bool is_memberwise ) {
            if ( m_objwise_or_memberwise == 0 && is_memberwise )
                throw std::runtime_error( "STLMapReader(" + name() +
                                          "): Expect obj-wise, got member-wise!" );
            if ( m_objwise_or_memberwise == 1 && !is_memberwise )
                throw std::runtime_error( "STLMapReader(" + name() +
                                          "): Expect member-wise, got obj-wise!" );
        }

        /**
         * @brief Read the element version and checksum from the stream.
         *
         * @param stream The binary stream to read from.
         * @return A tuple of (version, checksum).
         */
        pair<int, uint32_t> read_element_version( BinaryStream& stream ) {
            auto version      = stream.read_fVersion();
            uint32_t checksum = 0;
            if ( version == 0 ) checksum = stream.read<uint32_t>();
            return { version, checksum };
        }

        /**
         * @brief Read the body of the map from the stream. First reads the size
         * (uint32_t) of the map, then calls @ref m_key_reader and @ref m_value_reader
         * to read the keys and values. If member-wise, reads all keys first, then all values.
         * Otherwise, reads key-value pairs one by one.
         *
         * @param stream The binary stream to read from.
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
        void read_body( BinaryStream& stream, bool is_memberwise ) {
            auto fSize = stream.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            if ( is_memberwise )
            {
                m_key_reader->read_many( stream, fSize );
                m_value_reader->read_many( stream, fSize );
            }
            else
            {
                for ( auto i = 0; i < fSize; i++ )
                {
                    m_key_reader->read( stream );
                    m_value_reader->read( stream );
                }
            }
        }

        /**
         * @brief Read a map from the stream. Reads a `fNBytes+fVersion` header,
         * then reads element version/checksum via @ref read_element_version(), and
         * finally calls @ref read_body() to read the map body.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            stream.read_fNBytes();
            auto fVersion = stream.read_fVersion();
            read_element_version( stream );

            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            read_body( stream, is_memberwise );
        }

        /**
         * @brief Read multiple maps from the stream. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header and element version/checksum once before
         * reading multiple maps.
         *
         * @param stream The binary stream to read from.
         * @param count Number of maps to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of maps read.
         */
        uint32_t read_many( BinaryStream& stream, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLMapReader::read with negative count only "
                                              "supported when with_header is true!" );

                auto fNBytes  = stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();
                read_element_version( stream );
                bool is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );

                auto end_pos = stream.get_cursor() + fNBytes - 8;

                uint32_t cur_count = 0;
                while ( stream.get_cursor() < end_pos )
                {
                    read_body( stream, is_memberwise );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                bool is_memberwise = m_objwise_or_memberwise == 1;
                if ( m_with_header )
                {
                    auto fNBytes  = stream.read_fNBytes();
                    auto fVersion = stream.read_fVersion();
                    read_element_version( stream );

                    is_memberwise = fVersion & kStreamedMemberWise;
                    check_objwise_memberwise( is_memberwise );
                }

                for ( auto i = 0; i < count; i++ ) { read_body( stream, is_memberwise ); }
                return count;
            }
        }

        /**
         * @brief Read maps from the stream until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header and element
         * version/checksum once before reading maps.
         *
         * @param stream The binary stream to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of maps read.
         */
        uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) override {
            if ( stream.get_cursor() == end_pos ) return 0;

            bool is_memberwise = m_objwise_or_memberwise == 1;
            if ( m_with_header )
            {
                stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();
                read_element_version( stream );

                is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
            }

            uint32_t cur_count = 0;
            while ( stream.get_cursor() < end_pos )
            {
                read_body( stream, is_memberwise );
                cur_count++;
            }
            return cur_count;
        }

        /**
         * @brief Read multiple maps from the stream in member-wise mode.
         *
         * @param stream The binary stream to read from.
         * @param count Number of maps to read. If negative, throws an error.
         * @return Number of maps read.
         */
        virtual uint32_t read_many_memberwise( BinaryStream& stream,
                                               const int64_t count ) override {
            if ( count < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            bool is_memberwise = true;
            check_objwise_memberwise( is_memberwise );
            return read_many( stream, count );
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A tuple contains: (offsets, keys_data, values_data).
         */
        py::object data() const override {
            auto offsets_array     = make_array( m_offsets );
            py::object keys_data   = m_key_reader->data();
            py::object values_data = m_value_reader->data();
            return py::make_tuple( offsets_array, keys_data, values_data );
        }
    };

    /**
     * @brief Reader for STL string (std::string).
     */
    class STLStringReader : public IReader {
      private:
        const bool m_with_header; ///< Whether the string has a `fNBytes+fVersion` header.
        SharedVector<int64_t> m_offsets; ///< Store the offsets for each string.
        SharedVector<uint8_t> m_data;    ///< Store the string data as uint8_t.

      public:
        /**
         * @brief Construct a new STLStringReader object.
         *
         * @param name Name of the reader.
         * @param with_header Whether the string has a `fNBytes+fVersion` header.
         */
        STLStringReader( string name, bool with_header )
            : IReader( name )
            , m_with_header( with_header )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) )
            , m_data( std::make_shared<vector<uint8_t>>() ) {}

        /**
         * @brief Read the body of the string from the stream. A string starts with a uint8_t
         * size. If the size is 255, then a uint32_t size follows. Then the string data
         * follows.
         *
         * @param stream The binary stream to read from.
         */
        void read_body( BinaryStream& stream ) {
            uint32_t fSize = stream.read<uint8_t>();
            if ( fSize == 255 ) fSize = stream.read<uint32_t>();

            m_offsets->push_back( m_offsets->back() + fSize );
            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( stream.read<uint8_t>() ); }
        }

        /**
         * @brief Read a string from the stream. If @ref m_with_header is true, reads a
         * `fNBytes+fVersion` header before reading the string body.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            if ( m_with_header )
            {
                stream.read_fNBytes();
                stream.read_fVersion();
            }
            read_body( stream );
        }

        /**
         * @brief Read multiple strings from the stream. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header once before reading multiple strings.
         *
         * @param stream The binary stream to read from.
         * @param count Number of strings to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of strings read.
         */
        uint32_t read_many( BinaryStream& stream, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLStringReader::read with negative count only "
                                              "supported when with_header is true!" );
                auto fNBytes  = stream.read_fNBytes();
                auto fVersion = stream.read_fVersion();

                auto end_pos       = stream.get_cursor() + fNBytes - 2; // -2 for fVersion
                uint32_t cur_count = 0;
                while ( stream.get_cursor() < end_pos )
                {
                    read_body( stream );
                    cur_count++;
                }
                return cur_count;
            }
            else
            {
                if ( m_with_header )
                {
                    auto fNBytes  = stream.read_fNBytes();
                    auto fVersion = stream.read_fVersion();
                }

                for ( auto i = 0; i < count; i++ ) { read_body( stream ); }
                return count;
            }
        }

        /**
         * @brief Read strings from the stream until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header once before reading
         * strings.
         *
         * @param stream The binary stream to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of strings read.
         */
        uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) override {
            if ( stream.get_cursor() == end_pos ) return 0;
            if ( m_with_header )
            {
                stream.read_fNBytes();
                stream.read_fVersion();
            }

            int32_t cur_count = 0;
            while ( stream.get_cursor() < end_pos )
            {
                read_body( stream );
                cur_count++;
            }
            return cur_count;
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A tuple of numpy arrays: (offsets, data).
         */
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

    /**
     * @brief Reader for TArray types.
     *
     * @tparam T Element type of the TArray.
     */
    template <typename T>
    class TArrayReader : public IReader {
      private:
        SharedVector<int64_t> m_offsets; ///< Store the offsets for each TArray.
        SharedVector<T> m_data;          ///< Store the TArray data.

      public:
        /**
         * @brief Construct a new TArrayReader object.
         *
         * @param name Name of the reader.
         */
        TArrayReader( string name )
            : IReader( name )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) )
            , m_data( std::make_shared<vector<T>>() ) {}

        /**
         * @brief Read a TArray from the stream. First reads the size (uint32_t) of the TArray,
         * then reads the elements of the TArray.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            auto fSize = stream.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );
            for ( auto i = 0; i < fSize; i++ ) { m_data->push_back( stream.read<T>() ); }
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A tuple of numpy arrays: (offsets, data).
         */
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

    /**
     * @brief This reader groups multiple readers together and reads them sequentially.
     */
    class GroupReader : public IReader {
      private:
        vector<SharedReader> m_element_readers; ///< The grouped element readers.

      public:
        /**
         * @brief Construct a new GroupReader object.
         *
         * @param name Name of the reader.
         * @param element_readers The grouped element readers. In Python, this should be a list
         * of readers.
         */
        GroupReader( string name, vector<SharedReader> element_readers )
            : IReader( name ), m_element_readers( element_readers ) {}

        /**
         * @brief Read all grouped elements from the stream sequentially.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            for ( auto& reader : m_element_readers )
            {
                debug_printf( "GroupReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( stream );
                reader->read( stream );
            }
        }

        /**
         * @brief Read multiple grouped elements from the stream sequentially in member-wise
         * mode. This method calls @ref IReader::read_many() of each grouped
         * reader.
         *
         * @param stream The binary stream to read from.
         * @param count Number of objects to read.
         * @return Number of objects read. Should be equal to @ref count.
         */
        uint32_t read_many_memberwise( BinaryStream& stream, const int64_t count ) override {
            if ( count < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "GroupReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( stream );
                reader->read_many( stream, count );
            }
            return count;
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A list of data from each grouped reader.
         */
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

    /**
     * @brief Reader for composed class types. Similar to @ref GroupReader, but reads a
     * `fNBytes+fVersion` header before reading the grouped elements.
     */
    class AnyClassReader : public IReader {
      private:
        vector<SharedReader> m_element_readers; ///< The element readers for the Any class.

      public:
        /**
         * @brief Construct a new Any Class Reader object
         *
         * @param name Name of the reader.
         * @param element_readers The element readers for the Any class. In Python, this should
         * be a list of readers.
         */
        AnyClassReader( string name, vector<SharedReader> element_readers )
            : IReader( name ), m_element_readers( element_readers ) {}

        /**
         * @brief Read the object from the stream. First reads the `fNBytes+fVersion`
         * header, then reads all elements sequentially.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            auto fNBytes   = stream.read_fNBytes();
            auto start_pos = stream.get_cursor();
            auto end_pos   = stream.get_cursor() + fNBytes;

            auto fVersion = stream.read_fVersion();
            if ( fVersion == 0 ) stream.skip( 4 ); // skip checksum for fVersion 0

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "AnyClassReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( stream );
                reader->read( stream );
            }

            if ( stream.get_cursor() != end_pos )
            {
                stringstream msg;
                msg << "AnyClassReader: Invalid read length for " << name() << "! Expect "
                    << end_pos - start_pos << ", got " << stream.get_cursor() - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }

        /**
         * @brief Read multiple objects from the stream in member-wise mode. This method
         * calls @ref IReader::read_many() of each element reader sequentially.
         *
         * @param stream The binary stream to read from.
         * @param count Number of objects to read.
         * @return Number of objects read. Should be equal to @ref count.
         */
        uint32_t read_many_memberwise( BinaryStream& stream, const int64_t count ) override {
            if ( count < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto& reader : m_element_readers )
            {
                debug_printf( "AnyClassReader %s: reading memberwise %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( stream );
                reader->read_many( stream, count );
            }

            return count;
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return A list of data from each element reader.
         */
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

    class AnyPointerReader : public IReader {
      private:
        SharedReader m_element_reader; ///< Reader for the object content.

        int64_t m_object_counter{ 0 }; ///< Counter for the number of objects read, used for
                                       ///< generating indexes

        SharedVector<int64_t> m_object_indexes; ///< Store the indexes of the objects read

        string m_class_name{}; ///< Store the class name of the object

      public:
        AnyPointerReader( string name, SharedReader element_reader )
            : IReader( name )
            , m_element_reader( element_reader )
            , m_object_indexes( std::make_shared<vector<int64_t>>() ) {}

        void check_cursor_position( BinaryStream& stream, const uint32_t expected_nbytes,
                                    const uint8_t* expected_pos ) {
            if ( stream.get_cursor() != expected_pos )
            {
                stringstream msg;
                msg << "AnyPointerReader(" << name() << "): Invalid read length! Expect "
                    << expected_nbytes << " bytes, got "
                    << static_cast<int64_t>( expected_nbytes ) -
                           ( expected_pos - stream.get_cursor() )
                    << " bytes.";
                throw std::runtime_error( msg.str() );
            }
        }

        void read( BinaryStream& stream ) override {
            auto start_ptr     = stream.get_cursor();
            uint32_t start_pos = stream.get_index();
            uint32_t ref_begin = start_pos + stream.get_initial_cursor_offset();
            auto fNBytes       = stream.read<uint32_t>();

            int16_t fVersion;
            uint32_t fTag;

            if ( ( fNBytes & kByteCountMask ) == 0 || fNBytes == kNewClassTag )
            {
                fVersion  = 0;
                ref_begin = 0;
                fTag      = fNBytes;
                fNBytes   = 0;
            }
            else
            {
                fVersion = 1;
                fTag     = stream.read<uint32_t>();
                fNBytes &= ~kByteCountMask;
            }

            auto end_ptr = fVersion > 0 ? start_ptr + 4 + fNBytes : start_ptr + 4;

            if ( ( fTag & kClassMask ) == 0 )
            {
                if ( fTag == 0 )
                {
                    check_cursor_position( stream, fNBytes, end_ptr );
                    m_object_indexes->push_back( -1 ); // use -1 to indicate null pointer
                    return;
                }
                else if ( fTag == 1 )
                    throw std::runtime_error( "AnyPointerReader(" + name() +
                                              "): Unsupported fTag value 1" );
                else if ( stream.get_refs().find( fTag ) == stream.get_refs().end() )
                {
                    // skip unknown reference
                    auto nskip = end_ptr - stream.get_cursor();
                    stream.skip( nskip );
                    check_cursor_position( stream, fNBytes, end_ptr );
                    return;
                }
                else
                {
                    auto ref     = stream.get_refs().at( fTag );
                    auto ref_idx = std::get<BinaryStream::RefObj>( ref ).index;
                    m_object_indexes->push_back( ref_idx );
                    check_cursor_position( stream, fNBytes, end_ptr );
                    return;
                }
            }
            else if ( fTag == kNewClassTag )
            {
                auto class_name = stream.read_null_terminated_string();
                if ( m_class_name.empty() ) m_class_name = class_name;
                else if ( m_class_name != class_name )
                {
                    stringstream msg;
                    msg << "AnyPointerReader(" << name()
                        << "): Inconsistent class names! Expect " << m_class_name << ", got "
                        << class_name;
                    throw std::runtime_error( msg.str() );
                }

                auto& buf_refs = stream.get_refs();

                auto ref_key = fVersion > 0 ? ref_begin + kMapOffset : buf_refs.size() + 1;
                buf_refs[ref_key] = BinaryStream::RefCls{ class_name };

                m_element_reader->read( stream );
                m_object_indexes->push_back( m_object_counter );

                ref_key = fVersion > 0 ? ref_begin + kMapOffset : buf_refs.size() + 1;
                buf_refs[ref_key] = BinaryStream::RefObj{ m_object_counter };

                m_object_counter++;
            }
            else
            {
                auto& buf_refs   = stream.get_refs();
                auto cls_ref_key = fTag & ( ~kClassMask );
                if ( buf_refs.find( cls_ref_key ) != buf_refs.end() )
                {
                    auto class_name =
                        std::get<BinaryStream::RefCls>( buf_refs.at( cls_ref_key ) ).name;
                    if ( class_name != m_class_name )
                    {
                        stringstream msg;
                        msg << "AnyPointerReader(" << name()
                            << "): Inconsistent class names! Expect " << m_class_name
                            << ", got " << class_name;
                        throw std::runtime_error( msg.str() );
                    }
                }

                m_element_reader->read( stream );
                m_object_indexes->push_back( m_object_counter );

                auto obj_ref_key = fVersion > 0 ? ref_begin + kMapOffset : buf_refs.size() + 1;
                buf_refs[obj_ref_key] = BinaryStream::RefObj{ m_object_counter };

                m_object_counter++;
            }

            check_cursor_position( stream, fNBytes, end_ptr );
        }

        py::object data() const override {
            auto element_data  = m_element_reader->data();
            auto indexes_array = make_array( m_object_indexes );
            return py::make_tuple( element_data, indexes_array );
        }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Reader for C-style arrays and std::array.
     */
    class CStyleArrayReader : public IReader {
      private:
        const int64_t m_flat_size; ///< Flatten size of the array. If negative, means variable
                                   ///< size.
        SharedVector<int64_t> m_offsets; ///< Store the offsets for each array (only used when
                                         ///< variable size).
        SharedReader m_element_reader;   ///< Reader for the array elements.

      public:
        /**
         * @brief Construct a new CStyleArrayReader object.
         *
         * @param name Name of the reader.
         * @param flat_size Flatten size of the array. If negative, means variable size.
         * @param element_reader Reader for the array elements.
         */
        CStyleArrayReader( string name, const int64_t flat_size, SharedReader element_reader )
            : IReader( name )
            , m_flat_size( flat_size )
            , m_offsets( std::make_shared<vector<int64_t>>( 1, 0 ) )
            , m_element_reader( element_reader ) {}

        /**
         * @brief Read the array from the stream. If @ref m_flat_size is positive, calls @ref
         * IReader::read_many() function of @ref m_element_reader. Otherwise, reads
         * until the end of the current entry in the stream.
         *
         * @param stream The binary stream to read from.
         */
        void read( BinaryStream& stream ) override {
            debug_printf( "CStyleArrayReader(%s) with flat_size %ld\n", m_name.c_str(),
                          m_flat_size );
            debug_printf( stream );

            if ( m_flat_size >= 0 ) { m_element_reader->read_many( stream, m_flat_size ); }
            else
            {
                // get end-position
                auto n_entries     = stream.entries();
                auto start_pos     = stream.get_data();
                auto entry_offsets = stream.get_offsets();
                auto cursor_pos    = stream.get_cursor();
                auto entry_end = std::find_if( entry_offsets, entry_offsets + n_entries + 1,
                                               [start_pos, cursor_pos]( uint32_t offset ) {
                                                   return start_pos + offset > cursor_pos;
                                               } );
                auto end_pos   = start_pos + *entry_end;
                uint32_t count = m_element_reader->read_until( stream, end_pos );
                m_offsets->push_back( m_offsets->back() + count );
                debug_printf( "CStyleArrayReader(%s) read %d elements\n", m_name.c_str(),
                              count );
            }
        }

        /**
         * @brief Read multiple arrays from the stream. Only supported when @ref m_flat_size
         * is positive.
         *
         * @param stream The binary stream to read from.
         * @param count Number of arrays to read.
         * @return Number of arrays read.
         */
        uint32_t read_many( BinaryStream& stream, const int64_t count ) override {
            if ( m_flat_size < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many only supported when flat_size > 0!";
                throw std::runtime_error( msg.str() );
            }
            if ( count < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            for ( auto i = 0; i < count; i++ )
                m_element_reader->read_many( stream, m_flat_size );

            return count;
        }

        /**
         * @brief Read arrays from the stream until reaching the end position. Not supported.
         *
         * @param stream The binary stream to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of arrays read.
         *
         * @exception std::runtime_error Always thrown since this method is not supported.
         */
        uint32_t read_until( BinaryStream& stream, const uint8_t* end_pos ) override {
            throw std::runtime_error( "CStyleArrayReader::read with end_pos not supported!" );
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return If @ref m_flat_size is positive, directly return the data from @ref
         * m_element_reader. Otherwise, return a tuple contains: (offsets, elements_data).
         */
        py::object data() const override {
            if ( m_flat_size >= 0 ) return m_element_reader->data();
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

    /**
     * @brief Reader that does nothing and returns None.
     */
    class EmptyReader : public IReader {
      public:
        /**
         * @brief Construct a new EmptyReader object.
         *
         * @param name Name of the reader.
         */
        EmptyReader( string name ) : IReader( name ) {}

        /**
         * @brief Do nothing.
         */
        void read( BinaryStream& ) override {}

        /**
         * @brief Return None.
         */
        py::object data() const override { return py::none(); }
    };

    /*
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    -----------------------------------------------------------------------------
    */

    /**
     * @brief Read data from a binary stream using the provided reader.
     *
     * @param data Binary data as a numpy array of uint8_t
     * @param offsets Offsets for each entry as a numpy array of uint32_t
     * @param reader Shared pointer to the top-level reader
     * @return (Possibly nested) numpy array containing the read data
     */
    py::object py_read_data( py::array_t<uint8_t> data, py::array_t<uint32_t> offsets,
                             uint32_t cursor_offset, SharedReader reader ) {
        BinaryStream stream( data, offsets, cursor_offset );
        for ( auto i_evt = 0; i_evt < stream.entries(); i_evt++ )
        {
            auto start_pos = stream.get_cursor();
            reader->read( stream );
            auto end_pos = stream.get_cursor();

            if ( end_pos - start_pos !=
                 stream.get_offsets()[i_evt + 1] - stream.get_offsets()[i_evt] )
            {
                stringstream msg;
                msg << "py_read_data: Invalid read length for " << reader->name()
                    << " at event " << i_evt << "! Expect "
                    << stream.get_offsets()[i_evt + 1] - stream.get_offsets()[i_evt]
                    << ", got " << end_pos - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }
        return reader->data();
    }

    PYBIND11_MODULE( cpp, m ) {
        m.doc() = "C++ module for uproot-custom";

        m.def( "read_data", &py_read_data, "Read data from a binary stream", py::arg( "data" ),
               py::arg( "offsets" ), py::arg( "cursor_offset" ), py::arg( "reader" ) );

        py::class_<IReader, SharedReader>( m, "IReader" )
            .def( "name", &IReader::name, "Get the name of the reader" );

        // Basic type readers
        declare_reader<PrimitiveReader<uint8_t>, string>( m, "UInt8Reader" );
        declare_reader<PrimitiveReader<uint16_t>, string>( m, "UInt16Reader" );
        declare_reader<PrimitiveReader<uint32_t>, string>( m, "UInt32Reader" );
        declare_reader<PrimitiveReader<uint64_t>, string>( m, "UInt64Reader" );
        declare_reader<PrimitiveReader<int8_t>, string>( m, "Int8Reader" );
        declare_reader<PrimitiveReader<int16_t>, string>( m, "Int16Reader" );
        declare_reader<PrimitiveReader<int32_t>, string>( m, "Int32Reader" );
        declare_reader<PrimitiveReader<int64_t>, string>( m, "Int64Reader" );
        declare_reader<PrimitiveReader<float>, string>( m, "FloatReader" );
        declare_reader<PrimitiveReader<double>, string>( m, "DoubleReader" );

        // STL readers
        declare_reader<STLSeqReader, string, bool, int, SharedReader>( m, "STLSeqReader" );
        declare_reader<STLMapReader, string, bool, int, SharedReader, SharedReader>(
            m, "STLMapReader" );
        declare_reader<STLStringReader, string, bool>( m, "STLStringReader" );

        // TArrayReader
        declare_reader<TArrayReader<int8_t>, string>( m, "TArrayCReader" );
        declare_reader<TArrayReader<int16_t>, string>( m, "TArraySReader" );
        declare_reader<TArrayReader<int32_t>, string>( m, "TArrayIReader" );
        declare_reader<TArrayReader<int64_t>, string>( m, "TArrayLReader" );
        declare_reader<TArrayReader<float>, string>( m, "TArrayFReader" );
        declare_reader<TArrayReader<double>, string>( m, "TArrayDReader" );

        // Other readers
        declare_reader<TStringReader, string, bool>( m, "TStringReader" );
        declare_reader<TObjectReader, string, bool>( m, "TObjectReader" );
        declare_reader<GroupReader, string, vector<SharedReader>>( m, "GroupReader" );
        declare_reader<AnyClassReader, string, vector<SharedReader>>( m, "AnyClassReader" );
        declare_reader<AnyPointerReader, string, SharedReader>( m, "AnyPointerReader" );
        declare_reader<CStyleArrayReader, string, int64_t, SharedReader>(
            m, "CStyleArrayReader" );
        declare_reader<EmptyReader, string>( m, "EmptyReader" );
    }

} // namespace uproot
