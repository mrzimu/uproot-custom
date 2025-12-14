#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <pybind11/gil.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>
#include <stdexcept>
#include <vector>

#include "uproot-custom/uproot-custom.hh"

namespace uproot {
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
         * @brief Read a value from the buffer and store it. Only reads one value at a time.
         *
         * @param buffer The binary buffer to read from
         */
        void read( BinaryBuffer& buffer ) override { m_data->push_back( buffer.read<T>() ); }

        /**
         * @brief Get the read data as a numpy array
         *
         * @return Numpy array containing the read data
         */
        py::object data() const override { return make_array( m_data ); }
    };

    /**
     * @brief Specialization of PrimitiveReader for bool type. Bools are stored as uint8_t.
     */
    template <>
    class PrimitiveReader<bool> : public IReader {
      private:
        SharedVector<uint8_t> m_data; ///< Store the read data as uint8_t

      public:
        PrimitiveReader( string name )
            : IReader( name ), m_data( std::make_shared<vector<uint8_t>>() ) {}

        /**
         * @brief Read a uint8_t from the buffer and store it as bool
         *
         * @param buffer The binary buffer to read from
         */
        void read( BinaryBuffer& buffer ) override {
            m_data->push_back( buffer.read<uint8_t>() != 0 );
        }

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
         * @brief Read a TObject from the buffer. A TObject contains `fVersion` (int16_t),
         * `fUniqueID` (int32_t), `fBits` (uint32_t). If `fBits & kIsReferenced`, then a `pidf`
         * (uint16_t) follows. If @ref m_keep_data is true, the read data
         * will be stored.
         *
         * @param buffer The binary buffer to read from
         */
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
         * @brief Read a TString from the buffer. A TString starts with a uint8_t size. If the
         * size is 255, then a uint32_t size follows. Then the string data follows. It @ref
         * m_with_header is true, read a `fNBytes+fVersion` header before reading the TString.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
            m_offsets->push_back( m_data->size() );
        }

        /**
         * @brief Read multiple TStrings from the buffer. If @ref m_with_header is true, only
         * read `fNBytes+fVersion` header once before reading multiple TStrings.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of TStrings to read. If negative, throws an error.
         * @return Number of TStrings read.
         */
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

        /**
         * @brief Read TStrings from the buffer until reaching the end position. If @ref
         * m_with_header is true, only read `fNBytes+fVersion` header once before reading
         * TStrings.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of TStrings read.
         */
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
         * @brief Read the body of the sequence from the buffer. First reads the size
         * (uint32_t) of the sequence, then calls @ref m_element_reader to read the elements.
         *
         * @param buffer The binary buffer to read from.
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
        void read_body( BinaryBuffer& buffer, bool is_memberwise ) {
            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );

            debug_printf( "STLSeqReader(%s): reading body, is_memberwise=%d, fSize=%d\n",
                          m_name.c_str(), is_memberwise, fSize );
            debug_printf( buffer );

            if ( is_memberwise ) m_element_reader->read_many_memberwise( buffer, fSize );
            else m_element_reader->read_many( buffer, fSize );
        }

        /**
         * @brief Read a sequence from the buffer. If @ref m_with_header is true, reads a
         * `fNBytes+fVersion` header. Then calls @ref read_body() to read the sequence body.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            buffer.read_fNBytes();
            auto fVersion      = buffer.read_fVersion();
            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            if ( is_memberwise ) buffer.skip( 2 );
            read_body( buffer, is_memberwise );
        }

        /**
         * @brief Read multiple sequences from the buffer. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header once before reading multiple sequences.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of sequences to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of sequences read.
         */
        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
            if ( count == 0 ) return 0;
            else if ( count < 0 )
            {
                if ( !m_with_header )
                    throw std::runtime_error( "STLSeqReader::read with negative count only "
                                              "supported when with_header is true!" );

                auto fNBytes       = buffer.read_fNBytes();
                auto end_pos       = buffer.get_cursor() + fNBytes;
                auto fVersion      = buffer.read_fVersion();
                bool is_memberwise = fVersion & kStreamedMemberWise;
                check_objwise_memberwise( is_memberwise );
                if ( is_memberwise ) buffer.skip( 2 );

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

        /**
         * @brief Read sequences from the buffer until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header once before reading
         * sequences. If data is stored member-wise, skips 2 bytes after the header.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of sequences read.
         */
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
         * @brief Read the body of the map from the buffer. First reads the size
         * (uint32_t) of the map, then calls @ref m_key_reader and @ref m_value_reader
         * to read the keys and values. If member-wise, reads all keys first, then all values.
         * Otherwise, reads key-value pairs one by one.
         *
         * @param buffer The binary buffer to read from.
         * @param is_memberwise Whether the current reading mode is member-wise.
         */
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

        /**
         * @brief Read a map from the buffer. If @ref m_with_header is true, reads a
         * `fNBytes+fVersion` header and skip 6 extra bytes. Then calls @ref read_body() to
         * read the map body.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            buffer.read_fNBytes();
            auto fVersion = buffer.read_fVersion();
            buffer.skip( 6 );

            bool is_memberwise = fVersion & kStreamedMemberWise;
            check_objwise_memberwise( is_memberwise );
            read_body( buffer, is_memberwise );
        }

        /**
         * @brief Read multiple maps from the buffer. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header and skip 6 extra bytes once before reading
         * multiple maps.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of maps to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of maps read.
         */
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

        /**
         * @brief Read sequences from the buffer until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header and skip 6 extra bytes once
         * before reading sequences. If data is stored member-wise, skips 2 bytes after the
         * header.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of sequences read.
         */
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

        /**
         * @brief Read multiple maps from the buffer in member-wise mode.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of maps to read. If negative, throws an error.
         * @return Number of maps read.
         */
        virtual uint32_t read_many_memberwise( BinaryBuffer& buffer,
                                               const int64_t count ) override {
            if ( count < 0 )
            {
                stringstream msg;
                msg << name() << "::read_many_memberwise with negative count: " << count;
                throw std::runtime_error( msg.str() );
            }

            bool is_memberwise = true;
            check_objwise_memberwise( is_memberwise );
            return read_many( buffer, count );
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
         * @brief Read the body of the string from the buffer. A string starts with a uint8_t
         * size. If the size is 255, then a uint32_t size follows. Then the string data
         * follows.
         *
         * @param buffer The binary buffer to read from.
         */
        void read_body( BinaryBuffer& buffer ) {
            uint32_t fSize = buffer.read<uint8_t>();
            if ( fSize == 255 ) fSize = buffer.read<uint32_t>();

            m_offsets->push_back( m_offsets->back() + fSize );
            for ( int i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<uint8_t>() ); }
        }

        /**
         * @brief Read a string from the buffer. If @ref m_with_header is true, reads a
         * `fNBytes+fVersion` header before reading the string body.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            if ( m_with_header )
            {
                buffer.read_fNBytes();
                buffer.read_fVersion();
            }
            read_body( buffer );
        }

        /**
         * @brief Read multiple strings from the buffer. If @ref m_with_header is true,
         * reads a `fNBytes+fVersion` header once before reading multiple strings.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of strings to read. If negative, reads according to the
         * `fNBytes` header.
         * @return Number of strings read.
         */
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

        /**
         * @brief Read strings from the buffer until reaching the end position. If @ref
         * m_with_header is true, reads a `fNBytes+fVersion` header once before reading
         * strings.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of strings read.
         */
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
         * @brief Read a TArray from the buffer. First reads the size (uint32_t) of the TArray,
         * then reads the elements of the TArray.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            auto fSize = buffer.read<uint32_t>();
            m_offsets->push_back( m_offsets->back() + fSize );
            for ( auto i = 0; i < fSize; i++ ) { m_data->push_back( buffer.read<T>() ); }
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
         * @brief Read all grouped elements from the buffer sequentially.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            for ( auto& reader : m_element_readers )
            {
                debug_printf( "GroupReader %s: reading %s\n", m_name.c_str(),
                              reader->name().c_str() );
                debug_printf( buffer );
                reader->read( buffer );
            }
        }

        /**
         * @brief Read multiple grouped elements from the buffer sequentially in member-wise
         * mode. This method calls @ref IReader::read_many() of each grouped
         * reader.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of objects to read.
         * @return Number of objects read. Should be equal to @ref count.
         */
        uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) override {
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
                debug_printf( buffer );
                reader->read_many( buffer, count );
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
         * @brief Read the object from the buffer. First reads the `fNBytes+fVersion`
         * header, then reads all elements sequentially.
         *
         * @param buffer The binary buffer to read from.
         */
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
                stringstream msg;
                msg << "AnyClassReader: Invalid read length for " << name() << "! Expect "
                    << end_pos - start_pos << ", got " << buffer.get_cursor() - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }

        /**
         * @brief Read multiple objects from the buffer in member-wise mode. This method
         * calls @ref IReader::read_many() of each element reader sequentially.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of objects to read.
         * @return Number of objects read. Should be equal to @ref count.
         */
        uint32_t read_many_memberwise( BinaryBuffer& buffer, const int64_t count ) override {
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
                debug_printf( buffer );
                reader->read_many( buffer, count );
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

    /**
     * @brief Wrapper reader for object headers.
     */
    class ObjectHeaderReader : public IReader {
      private:
        SharedReader m_element_reader; ///< Reader for the object content.

      public:
        /**
         * @brief Construct a new Object Header Reader object
         *
         * @param name Name of the reader.
         * @param element_reader Reader for the object content.
         */
        ObjectHeaderReader( string name, SharedReader element_reader )
            : IReader( name ), m_element_reader( element_reader ) {}

        /**
         * @brief Read the object header from the buffer, then delegate to @ref
         * m_element_reader to read the object content.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            auto nbytes    = buffer.read_fNBytes();
            auto start_pos = buffer.get_cursor();
            auto end_pos   = buffer.get_cursor() + nbytes;

            auto fTag = buffer.read<int32_t>();
            if ( fTag == kNewClassTag )
            { auto fTypename = buffer.read_null_terminated_string(); }

            m_element_reader->read( buffer );

            if ( buffer.get_cursor() != end_pos )
            {
                stringstream msg;
                msg << "ObjectHeaderReader: Invalid read length for "
                    << m_element_reader->name() << "! Expect " << end_pos - start_pos
                    << ", got " << buffer.get_cursor() - start_pos;
                throw std::runtime_error( msg.str() );
            }
        }

        /**
         * @brief Get the data read by the reader. This should be called after the whole
         * reading process.
         *
         * @return Directly return the data from @ref m_element_reader.
         */
        py::object data() const override { return m_element_reader->data(); }
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
         * @brief Read the array from the buffer. If @ref m_flat_size is positive, calls @ref
         * IReader::read_many() function of @ref m_element_reader. Otherwise, reads
         * until the end of the current entry in the buffer.
         *
         * @param buffer The binary buffer to read from.
         */
        void read( BinaryBuffer& buffer ) override {
            debug_printf( "CStyleArrayReader(%s) with flat_size %ld\n", m_name.c_str(),
                          m_flat_size );
            debug_printf( buffer );

            if ( m_flat_size >= 0 ) { m_element_reader->read_many( buffer, m_flat_size ); }
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

        /**
         * @brief Read multiple arrays from the buffer. Only supported when @ref m_flat_size
         * is positive.
         *
         * @param buffer The binary buffer to read from.
         * @param count Number of arrays to read.
         * @return Number of arrays read.
         */
        uint32_t read_many( BinaryBuffer& buffer, const int64_t count ) override {
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
                m_element_reader->read_many( buffer, m_flat_size );

            return count;
        }

        /**
         * @brief Read arrays from the buffer until reaching the end position. Not supported.
         *
         * @param buffer The binary buffer to read from.
         * @param end_pos The end position to stop reading.
         * @return Number of arrays read.
         *
         * @exception std::runtime_error Always thrown since this method is not supported.
         */
        uint32_t read_until( BinaryBuffer& buffer, const uint8_t* end_pos ) override {
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
        void read( BinaryBuffer& ) override {}

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
     * @brief Read data from a binary buffer using the provided reader.
     *
     * @param data Binary data as a numpy array of uint8_t
     * @param offsets Offsets for each entry as a numpy array of uint32_t
     * @param reader Shared pointer to the top-level reader
     * @return (Possibly nested) numpy array containing the read data
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
                stringstream msg;
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
        declare_reader<PrimitiveReader<bool>, string>( m, "BoolReader" );

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
        declare_reader<ObjectHeaderReader, string, SharedReader>( m, "ObjectHeaderReader" );
        declare_reader<CStyleArrayReader, string, int64_t, SharedReader>(
            m, "CStyleArrayReader" );
        declare_reader<EmptyReader, string>( m, "EmptyReader" );
    }

} // namespace uproot
