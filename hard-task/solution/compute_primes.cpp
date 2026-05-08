#include <fstream>
#include <iostream>
#include <vector>

int main() {
    const int N = 50;
    std::vector<int> primes;
    primes.reserve(N);

    for (int candidate = 2; (int)primes.size() < N; ++candidate) {
        bool is_prime = true;
        for (int p : primes) {
            if (p * p > candidate) break;
            if (candidate % p == 0) {
                is_prime = false;
                break;
            }
        }
        if (is_prime) primes.push_back(candidate);
    }

    std::ofstream out("/tmp/primes.txt");
    for (int p : primes) out << p << "\n";
    return 0;
}
