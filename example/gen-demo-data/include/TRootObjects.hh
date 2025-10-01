#pragma once

#include <RtypesCore.h>
#include <TArrayC.h>
#include <TArrayD.h>
#include <TArrayF.h>
#include <TArrayI.h>
#include <TArrayL.h>
#include <TArrayL64.h>
#include <TArrayS.h>
#include <TObject.h>
#include <TString.h>

class TRootObjects : public TObject {
  private:
    // TString
    TString m_TString{ "This is a TString" };

    // TArray
    TArrayC m_TArrayC{ 5 };
    TArrayS m_TArrayD{ 5 };
    TArrayS m_TArrayF{ 5 };
    TArrayI m_TArrayI{ 5 };
    TArrayL m_TArrayL{ 5 };
    TArrayL64 m_TArrayL64{ 5 };
    TArrayS m_TArrayS{ 5 };

  public:
    TRootObjects() : TObject() {
        for ( int i = 0; i < 5; i++ )
        {
            m_TArrayC[i]   = i;
            m_TArrayD[i]   = i;
            m_TArrayF[i]   = i;
            m_TArrayI[i]   = i;
            m_TArrayL[i]   = i;
            m_TArrayL64[i] = i;
            m_TArrayS[i]   = i;
        }
    }

    ClassDef( TRootObjects, 1 );
};