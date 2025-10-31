#pragma once

#include <list>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

#include <TObject.h>
#include <TString.h>

using namespace std;

class TSTLSequence : public TObject {
  private:
    vector<double> m_vec_double{ 1.0, 2.0, 3.0 };
    set<double> m_set_double{ 1.0, 2.0, 3.0 };
    list<double> m_list_double{ 1.0, 2.0, 3.0 };
    unordered_set<double> m_uset_double{ 1.0, 2.0, 3.0 };
    multiset<double> m_mset_double{ 1.0, 1.0, 2.0, 3.0 };
    unordered_multiset<double> m_umset_double{ 1.0, 1.0, 2.0, 3.0 };

    vector<string> m_vec_str{ "aaa", "bbb", "ccc" };
    vector<TString> m_vec_tstr{ "aaa", "bbb", "ccc" };

    ClassDef( TSTLSequence, 1 );
};
