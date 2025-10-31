#pragma once

#include <cstdint>

#include <RtypesCore.h>
#include <TArrayI.h>
#include <TObject.h>
#include <TString.h>

using namespace std;

class TBasicTypes : public TObject {
  private:
    // basic types with predefined names
    bool m_bool{ false };
    char m_char{ 8 };
    signed char m_schar{ 8 };
    unsigned char m_uchar{ 8 };
    short m_short{ 16 };
    signed short m_sshort{ 16 };
    unsigned short m_ushort{ 16 };
    int m_int{ 32 };
    signed int m_sint{ 32 };
    unsigned int m_uint{ 32 };
    long m_long{ 64 };
    signed long m_slong{ 64 };
    unsigned long m_ulong{ 64 };
    long long m_llong{ 64 };
    signed long long m_sllong{ 64 };
    unsigned long long m_ullong{ 64 };
    float m_float{ 3.14f };
    double m_double{ 3.1415926 };
    long double m_ldouble{ 3.14159265358979323846 };

    // basic types defined in cstdint
    int8_t m_int8{ 8 };
    uint8_t m_uint8{ 8 };
    int16_t m_int16{ 16 };
    uint16_t m_uint16{ 16 };
    int32_t m_int32{ 32 };
    uint32_t m_uint32{ 32 };
    int64_t m_int64{ 64 };
    uint64_t m_uint64{ 64 };

    // basic types defined in ROOT
    Bool_t m_rt_bool{ false };
    Char_t m_rt_char{ 8 };
    UChar_t m_rt_uchar{ 8 };
    Short_t m_rt_short{ 16 };
    UShort_t m_rt_ushort{ 16 };
    Int_t m_rt_int{ 32 };
    UInt_t m_rt_uint{ 32 };
    Long_t m_rt_long{ 64 };
    ULong_t m_rt_ulong{ 64 };
    Long64_t m_rt_llong{ 64 };
    ULong64_t m_rt_ullong{ 64 };
    Float_t m_rt_float{ 3.14f };
    Double_t m_rt_double{ 3.1415926 };
    LongDouble_t m_rt_ldouble{ 3.14159265358979323846 };

    ClassDef( TBasicTypes, 1 );
};