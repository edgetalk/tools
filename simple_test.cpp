// Simple C++ test for function parsing
#include <iostream>

class SimpleClass {
public:
    void method1();
    int method2(int x, int y);
};

void SimpleClass::method1() {
    std::cout << "Method 1" << std::endl;
}

int SimpleClass::method2(int x, int y) {
    return x + y;
}

void global_function() {
    std::cout << "Global function" << std::endl;
}

int main() {
    return 0;
}