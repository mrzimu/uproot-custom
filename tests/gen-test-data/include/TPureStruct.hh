#pragma once

#include <vector>

struct TPureStructChild {
    int m_int{ 42 };
    std::vector<int> m_vec_int{ 1, 2, 3 };
};

struct TPureStruct {
    std::vector<TPureStructChild*> m_vec_child_ptr;

    TPureStruct( int i = 0 ) {
        for ( int j = 0; j < i; j++ ) { m_vec_child_ptr.push_back( new TPureStructChild() ); }
    }
};
