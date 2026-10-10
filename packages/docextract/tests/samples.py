"""Typical 2nd-year programs, used to build fake submissions."""

PY_FACT = '''def fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)


n = int(input())
for i in range(1, n + 1):
    print("Fact", i, fact(i))'''

C_SUM = '''#include <stdio.h>
int main() {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("Sum = %d\\n", a + b);
    return 0;
}'''

CPP_STACK = '''#include <iostream>
#include <stack>
using namespace std;

int main() {
    stack<int> s;
    int n, x;
    cin >> n;
    for (int i = 0; i < n; i++) {
        cin >> x;
        s.push(x);
    }
    while (!s.empty()) {
        cout << s.top() << " ";
        s.pop();
    }
    cout << endl;
    return 0;
}'''

JAVA_REV = '''import java.util.Scanner;

public class ReverseString {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        String s = sc.nextLine();
        String r = "";
        for (int i = s.length() - 1; i >= 0; i--) {
            r = r + s.charAt(i);
        }
        System.out.println("Reversed: " + r);
    }
}'''

PY_CLASS = '''class Stack:
    def __init__(self):
        self.items = []

    def push(self, x):
        self.items.append(x)

    def pop(self):
        if not self.items:
            return None
        return self.items.pop()


s = Stack()
for v in map(int, input().split()):
    s.push(v)
out = []
while True:
    v = s.pop()
    if v is None:
        break
    out.append(str(v))
print(" ".join(out))'''

CASES = {
    # name: (code, language, stdin, expected stdout, entrypoint)
    "py_fact": (PY_FACT, "python", "3\n", "Fact 1 1\nFact 2 2\nFact 3 6\n", None),
    "py_class": (PY_CLASS, "python", "1 2 3\n", "3 2 1\n", None),
    "c_sum": (C_SUM, "c", "3 4\n", "Sum = 7\n", None),
    "cpp_stack": (CPP_STACK, "cpp", "3\n1 2 3\n", "3 2 1 \n", None),
    "java_rev": (JAVA_REV, "java", "abc\n", "Reversed: cba\n", "ReverseString"),
}
