"""Demo classroom: one course, one lab assignment, nine students.

Lets the whole stack run without a Google account, and covers the cases a
TA meets: correct work, a disguised copy, Word-damaged code, faked output,
Java, a compile error, an infinite loop, a scanned page, a missing upload.
"""
from __future__ import annotations

import threading

from .demo_pdf import make_docx, make_pdf, rasterize, screenshot
from .provider import Provider, ProviderError

COURSE = {"id": "demo-it2271", "name": "IT 2271 Data Structures Lab",
          "section": "B.Tech IT, 2nd year", "link": ""}

ASSIGNMENT_TEXT = [
    ("h", "IT 2271 Data Structures Lab - Assignment 3"),
    ("p", "Submit one PDF with your code and a copy of the output for each question."),
    ("h", "Question 1: Bubble sort"),
    ("p", "Read n, then n integers. Print them in ascending order, separated by spaces."),
    ("p", "Sample Input 1:"), ("code", "5\n4 1 3 9 2", "mono_spaces"),
    ("p", "Sample Output 1:"), ("code", "1 2 3 4 9", "mono_spaces"),
    ("p", "Sample Input 2:"), ("code", "3\n3 2 1", "mono_spaces"),
    ("p", "Sample Output 2:"), ("code", "1 2 3", "mono_spaces"),
    ("h", "Question 2: Sum of digits"),
    ("p", "Read a non-negative integer n and print the sum of its digits."),
    ("p", "Sample Input:"), ("code", "1234", "mono_spaces"),
    ("p", "Sample Output:"), ("code", "10", "mono_spaces"),
]

C_SORT = '''#include <stdio.h>
int main() {
    int n, arr[100], i, j, temp;
    scanf("%d", &n);
    for (i = 0; i < n; i++)
        scanf("%d", &arr[i]);
    for (i = 0; i < n - 1; i++) {
        for (j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
    for (i = 0; i < n; i++)
        printf("%d ", arr[i]);
    printf("\\n");
    return 0;
}'''
C_SORT_COPY = '''#include<stdio.h>
// bubble sort - my own work
int main()
{
    int size, a[50], x, y, t;
    scanf("%d",&size);
    for(x=0;x<size;x++)
        scanf("%d",&a[x]);
    for(x=0;x<size-1;x++)
    {
        for(y=0;y<size-x-1;y++)
        {
            if(a[y]>a[y+1])
            {
                t=a[y];
                a[y]=a[y+1];
                a[y+1]=t;
            }
        }
    }
    for(x=0;x<size;x++)
        printf("%d ",a[x]);
    printf("\\n");
    return 0;
}'''
C_DIGITS = '''#include <stdio.h>
int main() {
    long n;
    int sum = 0;
    scanf("%ld", &n);
    while (n > 0) {
        sum += n % 10;
        n /= 10;
    }
    printf("%d\\n", sum);
    return 0;
}'''
C_DIGITS_COPY = '''#include<stdio.h>
int main()
{
    long num;
    int s=0;
    scanf("%ld",&num);
    while(num>0)
    {
        s+=num%10;
        num/=10;
    }
    printf("%d\\n",s);
    return 0;
}'''
# Word-damaged: smart quotes, auto-capitals
PY_SORT = '''Def bubble_sort(a):
    n = len(a)
    for i in range(n - 1):
        for j in range(n - i - 1):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
    return a


n = int(input())
nums = list(map(int, input().split()))
Print(\u201c \u201d.join(map(str, bubble_sort(nums))))'''
PY_DIGITS = '''n = input().strip()
print(sum(int(ch) for ch in n))'''
PY_DIGITS_TLE = '''n = int(input())
s = 0
while n > 0:
    s += n % 10
print(s)'''
# sorts descending, but the PDF shows the right answer
CPP_SORT_WRONG = '''#include <iostream>
#include <vector>
#include <algorithm>
#include <functional>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<int> v(n);
    for (auto &x : v) cin >> x;
    sort(v.begin(), v.end(), greater<int>());
    for (size_t i = 0; i < v.size(); i++)
        cout << v[i] << (i + 1 < v.size() ? " " : "\\n");
    return 0;
}'''
C_SORT_FUNC = '''#include <stdio.h>

void bubble(int a[], int n) {
    int swapped = 1;
    while (swapped) {
        swapped = 0;
        for (int k = 1; k < n; k++) {
            if (a[k - 1] > a[k]) {
                int t = a[k];
                a[k] = a[k - 1];
                a[k - 1] = t;
                swapped = 1;
            }
        }
    }
}

int main(void) {
    int n, a[200];
    scanf("%d", &n);
    for (int k = 0; k < n; k++) scanf("%d", &a[k]);
    bubble(a, n);
    for (int k = 0; k < n; k++) printf("%d%c", a[k], k == n - 1 ? '\\n' : ' ');
    return 0;
}'''
C_SORT_INSERTION = '''#include <stdio.h>
int main() {
    int n, a[100];
    scanf("%d", &n);
    for (int i = 0; i < n; i++)
        scanf("%d", &a[i]);
    for (int i = 1; i < n; i++) {
        int key = a[i], j = i - 1;
        while (j >= 0 && a[j] > key) {
            a[j + 1] = a[j];
            j--;
        }
        a[j + 1] = key;
    }
    for (int i = 0; i < n; i++)
        printf("%d ", a[i]);
    printf("\\n");
    return 0;
}'''
C_DIGITS_REC = '''#include <stdio.h>
int digit_sum(long x) {
    if (x == 0)
        return 0;
    return (int)(x % 10) + digit_sum(x / 10);
}
int main() {
    long n;
    scanf("%ld", &n);
    printf("%d\\n", digit_sum(n));
    return 0;
}'''
PY_DIGITS_LOOP = '''n = int(input())
total = 0
while n:
    total += n % 10
    n //= 10
print(total)'''
CPP_DIGITS = '''#include <iostream>
#include <string>
using namespace std;

int main() {
    string s;
    cin >> s;
    int total = 0;
    for (char c : s)
        total += c - '0';
    cout << total << endl;
    return 0;
}'''
JAVA_SORT = '''import java.util.Scanner;

public class BubbleSort {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = sc.nextInt();
        for (int i = 0; i < n - 1; i++)
            for (int j = 0; j < n - 1 - i; j++)
                if (a[j] > a[j + 1]) { int t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
        StringBuilder sb = new StringBuilder();
        for (int x : a) sb.append(x).append(" ");
        System.out.println(sb.toString().trim());
    }
}'''
JAVA_DIGITS = '''import java.util.Scanner;

public class DigitSum {
    public static void main(String[] args) {
        long n = new Scanner(System.in).nextLong();
        int s = 0;
        while (n > 0) { s += n % 10; n /= 10; }
        System.out.println(s);
    }
}'''
C_SORT_BROKEN = '''#include <stdio.h>
int main() {
    int n, x[100];
    scanf("%d", &n);
    for (int p = 0; p < n; p++)
        scanf("%d", &x[p]);
    for (int p = 0; p < n - 1; p++) {
        int m = p;
        for (int q = p + 1; q < n; q++)
            if (x[q] < x[m])
                m = q;
        int tmp = x[m]; x[m] = x[p]; x[p] = tmp
    }
    for (int p = 0; p < n; p++)
        printf("%d ", x[p]);
    return 0;
}'''   # missing semicolon after the swap


PY_SORT_BUILTIN = '''input()
nums = list(map(int, input().split()))
nums.sort()
print(*nums)'''
CPP_DIGITS_WRONG = '''#include <iostream>
using namespace std;

int main() {
    long long n;
    cin >> n;
    int s = 0;
    while (n > 9) {          // stops one digit early
        s += n % 10;
        n /= 10;
    }
    cout << s << endl;
    return 0;
}'''
C_SORT_WORD = '''#include <stdio.h>
int main() {
    int count, v[100];
    scanf("%d", &count);
    for (int k = 0; k < count; k++)
        scanf("%d", &v[k]);
    for (int pass = 1; pass < count; pass++)
        for (int k = 0; k < count - pass; k++)
            if (v[k] > v[k + 1]) {
                int hold = v[k];
                v[k] = v[k + 1];
                v[k + 1] = hold;
            }
    for (int k = 0; k < count; k++)
        printf("%d ", v[k]);
    printf("\\n");
    return 0;
}'''
PY_DIGITS_WORD = '''Def digit_sum(text):
    total = 0
    for ch in text:
        total += int(ch)
    return total


Print(digit_sum(input().strip()))'''.replace("Print(digit_sum(", "Print(digit_sum(")


def _riya_docx() -> bytes:
    """Word file, code typed in Word, output pasted as screenshots."""
    return make_docx([
        ("p", "Name: Riya Sen    Roll No: 2023ITB010"),
        ("h", "Question 1: Bubble sort"), ("p", "Code:"), ("code", C_SORT_WORD, "Courier New"),
        ("p", "Output:"), ("img", screenshot("$ gcc lab3.c && ./a.out\n5\n4 1 3 9 2\n1 2 3 4 9\n$", dark=True)),
        ("h", "Question 2: Sum of digits"), ("code", PY_DIGITS_WORD.replace("Print(", "Print("), "Calibri"),
        ("img", screenshot("1234\n10\n\nProcess finished with exit code 0", dark=False, title="Run: lab3"), 3.5),
    ])


def _aman_files() -> list[tuple[str, bytes, str]]:
    """PDF whose outputs are screenshots, plus Q2's output as a separate PNG.
    His Q2 is wrong, but the screenshot shows the right answer."""
    pdf = make_pdf([
        ("p", "Name: Aman Gupta"), ("p", "Roll No: 2023ITB011"),
        ("h", "Question 1: Bubble sort"), ("p", "Code:"), ("code", PY_SORT_BUILTIN, "mono_offset"),
        ("p", "Output:"), ("img", screenshot("5\n4 1 3 9 2\n1 2 3 4 9", dark=True, title="zsh")),
        ("h", "Question 2: Sum of digits"), ("p", "Code:"), ("code", CPP_DIGITS_WRONG, "mono_offset"),
        ("p", "Output: see the attached screenshot"),
    ], header="2023ITB011 Aman Gupta")
    png = screenshot("1234\n10", dark=True, title="Terminal")
    return [("2023ITB011_Aman_Gupta.pdf", pdf, "application/pdf"),
            ("Q2_output.png", png, "image/png")]


def _student_pdf(name, roll, q1, q2, out1="1 2 3 4 9", out2="10"):
    blocks = [("p", f"Name: {name}"), ("p", f"Roll No: {roll}")]
    if q1:
        blocks += [("h", "Question 1: Bubble sort"), ("p", "Code:"), ("code", q1[0], q1[1]),
                   ("p", "Output:"), ("code", out1, "mono_spaces")]
    if q2:
        blocks += [("h", "Question 2: Sum of digits"), ("p", "Code:"), ("code", q2[0], q2[1]),
                   ("p", "Output:"), ("code", out2, "mono_spaces")]
    return make_pdf(blocks, header=f"{roll} {name}")


STUDENTS = [
    # id, name, roll, q1, q2, extras
    ("s01", "Ananya Bose", "2023ITB001", (C_SORT, "mono_offset"), (C_DIGITS, "mono_offset"), {}),
    ("s02", "Rohit Mondal", "2023ITB002", (C_SORT_COPY, "prop_offset"), (C_DIGITS_COPY, "prop_offset"), {}),
    ("s03", "Sneha Paul", "2023ITB003", (PY_SORT, "mono_offset"), (PY_DIGITS, "mono_offset"), {}),
    ("s04", "Arjun Saha", "2023ITB004", (CPP_SORT_WRONG, "mono_offset"), (CPP_DIGITS, "numbered"), {}),
    ("s05", "Priya Dutta", "2023ITB005", (JAVA_SORT, "mono_spaces"), (JAVA_DIGITS, "mono_spaces"), {}),
    ("s06", "Kunal Ghosh", "2023ITB006", (C_SORT_BROKEN, "mono_offset"), (PY_DIGITS_LOOP, "mono_offset"), {}),
    ("s07", "Mehul Das", "2023ITB007", (C_SORT_FUNC, "mono_spaces"), (PY_DIGITS_TLE, "mono_offset"),
     {"out2": "10"}),
    ("s08", "Ishita Roy", "2023ITB008", (C_SORT_INSERTION, "mono_spaces"), (C_DIGITS_REC, "mono_spaces"),
     {"scan": True}),
    ("s09", "Debjit Sen", "2023ITB009", None, None, {"missing": True}),
    ("s10", "Riya Sen", "2023ITB010", None, None, {"custom": "riya"}),
    ("s11", "Aman Gupta", "2023ITB011", None, None, {"custom": "aman"}),
]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DemoProvider(Provider):
    mode = "demo"

    def __init__(self):
        self._lock = threading.Lock()
        self._files: dict[str, tuple[str, bytes]] | None = None
        self.grades: dict[str, dict] = {}

    def _build(self):
        with self._lock:
            if self._files is not None:
                return
            files = {"f-assignment3": ("Assignment 3 - Sorting and digits.pdf", make_pdf(ASSIGNMENT_TEXT),
                                       "application/pdf")}
            attached: dict[str, list[str]] = {}
            for sid, name, roll, q1, q2, ex in STUDENTS:
                if ex.get("missing"):
                    attached[sid] = []
                    continue
                if ex.get("custom") == "riya":
                    files[f"f-{sid}"] = ("Riya_Sen_Lab3.docx", _riya_docx(), DOCX_MIME)
                    attached[sid] = [f"f-{sid}"]
                    continue
                if ex.get("custom") == "aman":
                    attached[sid] = []
                    for i, (title, data, mime) in enumerate(_aman_files()):
                        files[f"f-{sid}-{i}"] = (title, data, mime)
                        attached[sid].append(f"f-{sid}-{i}")
                    continue
                pdf = _student_pdf(name, roll, q1, q2, out2=ex.get("out2", "10"))
                if ex.get("scan"):
                    pdf = rasterize(pdf)
                files[f"f-{sid}"] = (f"{roll}_{name.replace(' ', '_')}.pdf", pdf, "application/pdf")
                attached[sid] = [f"f-{sid}"]
            self._attached = attached
            self._files = files

    def list_courses(self):
        return [COURSE]

    def list_coursework(self, course_id):
        if course_id != COURSE["id"]:
            raise ProviderError(f"unknown course {course_id}")
        return [{"id": "cw-lab3", "title": "Assignment 3: Sorting and digits",
                 "description": "Bubble sort and sum of digits. Submit one PDF.",
                 "max_points": 20, "due": "2026-09-30",
                 "materials": [{"file_id": "f-assignment3", "title": "Assignment 3 - Sorting and digits.pdf",
                                "link": ""}], "link": ""}]

    def list_submissions(self, course_id, coursework_id):
        if coursework_id != "cw-lab3":
            raise ProviderError(f"unknown coursework {coursework_id}")
        self._build()
        out = []
        for sid, name, roll, *_rest, ex in STUDENTS:
            missing = ex.get("missing")
            out.append({
                "id": f"sub-{sid}",
                "student": {"id": sid, "name": name, "email": f"{roll.lower()}@students.iiests.ac.in"},
                "state": "CREATED" if missing else "TURNED_IN",
                "late": sid == "s07",
                "update_time": "2026-09-01T10:00:00Z",
                "files": [{"file_id": fid, "title": self._files[fid][0], "link": ""} for fid in self._attached[sid]],
                "assigned_grade": self.grades.get(f"sub-{sid}", {}).get("assigned"),
                "draft_grade": self.grades.get(f"sub-{sid}", {}).get("draft"),
            })
        return out

    def download_file(self, file_id):
        self._build()
        if file_id not in self._files:
            raise ProviderError(f"unknown file {file_id}")
        title, data, mime = self._files[file_id]
        return {"file_id": file_id, "title": title, "mime": mime, "data": data}

    def set_grade(self, course_id, coursework_id, submission_id, grade, assign):
        g = self.grades.setdefault(submission_id, {})
        g["draft"] = grade
        if assign:
            g["assigned"] = grade
        return {"ok": True}
