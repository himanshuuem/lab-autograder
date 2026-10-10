import pytest

from docextract.similarity import Doc, compare_submissions, fingerprints, tokenize
from samples import C_SUM, CPP_STACK, PY_CLASS, PY_FACT

BUBBLE = '''#include <stdio.h>
int main() {
    int n, arr[100], i, j, temp;
    printf("Enter n: ");
    scanf("%d", &n);
    for (i = 0; i < n; i++) scanf("%d", &arr[i]);
    for (i = 0; i < n - 1; i++) {
        for (j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                temp = arr[j]; arr[j] = arr[j + 1]; arr[j + 1] = temp;
            }
        }
    }
    for (i = 0; i < n; i++) printf("%d ", arr[i]);
    return 0;
}'''

# same program: renamed variables, new comments, new strings, reformatted
BUBBLE_DISGUISED = '''#include<stdio.h>
/* my own bubble sort
   written for assignment 3 */
int main()
{
    int size, a[50], x, y, t;   // variables
    printf("Number of elements: ");
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
    for(x=0;x<size;x++) printf("%d ",a[x]);
    return 0;
}'''

# honest, different solution to the same problem
BUBBLE_OWN = '''#include <stdio.h>
void sort(int *v, int n) {
    int swapped = 1;
    while (swapped) {
        swapped = 0;
        for (int k = 1; k < n; k++)
            if (v[k-1] > v[k]) { int t = v[k]; v[k] = v[k-1]; v[k-1] = t; swapped = 1; }
    }
}
int main(void) {
    int n; scanf("%d", &n);
    int v[1000];
    for (int k = 0; k < n; k++) scanf("%d", &v[k]);
    sort(v, n);
    for (int k = 0; k < n; k++) printf("%d\\n", v[k]);
}'''

INSERTION = '''#include <stdio.h>
int main(){int n,a[200];scanf("%d",&n);for(int i=0;i<n;i++)scanf("%d",&a[i]);
int i=1;while(i<n){int key=a[i];int j=i-1;while(j>=0&&a[j]>key){a[j+1]=a[j];j--;}a[j+1]=key;i++;}
for(int i=0;i<n;i++)printf("%d ",a[i]);return 0;}'''


def test_tokenize_normalises_names_numbers_strings_and_comments():
    a = [t for t, _ in tokenize('int total = 5; // sum\nprintf("x%d", total);', "c")]
    b = [t for t, _ in tokenize('int s=99;\nprintf("other", s);', "c")]
    assert a == b
    assert "printf" in a and "V" in a and "N" in a and "S" in a


def test_library_names_used_as_variables_are_normalised():
    a = [t for t, _ in tokenize("int size = 3; v.size();", "cpp")]
    assert a[1] == "V" and "size" in a


def test_python_comments_and_docstrings_ignored():
    a = '"""Doc."""\n# comment\nx = 1\nprint(x)'
    b = "y = 2\nprint(y)"
    assert [t for t, _ in tokenize(a, "python")] == [t for t, _ in tokenize(b, "python")]


def test_line_numbers_survive_comment_removal():
    toks = tokenize("/* a\n b */\nint x;", "c")
    assert toks[0] == ("int", 3)


def test_disguised_copy_is_caught():
    docs = [Doc("alice", BUBBLE, "c"), Doc("bob", BUBBLE_DISGUISED, "c"),
            Doc("carol", BUBBLE_OWN, "c"), Doc("dev", INSERTION, "c")]
    res = compare_submissions(docs, threshold=0.0)
    top = res[0]
    assert {top.a, top.b} == {"alice", "bob"} and top.score >= 0.95
    assert all(r.score < 0.5 for r in res[1:])


def test_default_threshold_reports_only_the_copy():
    docs = [Doc("alice", BUBBLE, "c"), Doc("bob", BUBBLE_DISGUISED, "c"),
            Doc("carol", BUBBLE_OWN, "c"), Doc("dev", INSERTION, "c")]
    res = compare_submissions(docs)
    assert [(r.a, r.b) for r in res] == [("alice", "bob")]
    assert res[0].lines_b and res[0].lines_b[0][0] <= 6


def test_partial_copy_with_extra_code_still_scores_high():
    extended = BUBBLE.replace("return 0;", 'printf("\\nDone\\n");\n    int extra = 0;\n'
                              '    for (i = 0; i < n; i++) extra += arr[i];\n'
                              '    printf("%d", extra);\n    return 0;')
    res = compare_submissions([Doc("a", BUBBLE, "c"), Doc("b", extended, "c")], threshold=0.0)
    assert res[0].score >= 0.8 and res[0].jaccard < res[0].score


def test_starter_code_is_ignored():
    starter = BUBBLE
    docs = [Doc("a", BUBBLE + "\n", "c"), Doc("b", BUBBLE_DISGUISED, "c")]
    assert compare_submissions(docs, starter_code=starter) == []


def test_patterns_most_of_class_share_are_ignored():
    # 6 students all copy the same skeleton but solve the problem differently
    common = '#include <stdio.h>\nint main() {\n    int n, i;\n    scanf("%d", &n);\n'
    bodies = [
        "    for (i = 0; i < n; i++) printf(\"%d\\n\", i * i);\n",
        "    int s = 0; while (n > 0) { s += n % 10; n /= 10; } printf(\"%d\", s);\n",
        "    if (n % 2 == 0) printf(\"even\"); else printf(\"odd\");\n",
        "    long f = 1; for (i = 2; i <= n; i++) f *= i; printf(\"%ld\", f);\n",
        "    int a = 0, b = 1, c; for (i = 0; i < n; i++) { c = a + b; a = b; b = c; } printf(\"%d\", a);\n",
        "    int r = 0; while (n) { r = r * 10 + n % 10; n /= 10; } printf(\"%d\", r);\n",
    ]
    docs = [Doc(f"s{i}", common + b + "    return 0;\n}", "c") for i, b in enumerate(bodies)]
    assert compare_submissions(docs, threshold=0.6) == []


def test_different_languages_are_not_compared():
    docs = [Doc("a", C_SUM, "c"), Doc("b", PY_FACT, "python")]
    assert compare_submissions(docs, threshold=0.0) == []


def test_empty_and_tiny_programs():
    docs = [Doc("a", "", "c"), Doc("b", "int x;", "c"), Doc("c", "int y;", "c")]
    res = compare_submissions(docs, threshold=0.0)
    assert [(r.a, r.b) for r in res] == [("b", "c")]
    assert res[0].low_confidence


def test_identical_python_programs():
    res = compare_submissions([Doc("a", PY_CLASS, "python"), Doc("b", PY_CLASS, "python")])
    assert res[0].score == 1.0 and not res[0].low_confidence


def test_winnowing_guarantee():
    """Any shared run of at least w+k-1 tokens must produce a shared fingerprint."""
    k, w = 8, 4
    shared = CPP_STACK
    a = "int unrelated_a() { return 1 + 2 * 3; }\n" + shared
    b = shared + "\nvoid other(int q) { while (q--) q *= 2; }"
    fa = fingerprints(tokenize(a, "cpp"), k, w)
    fb = fingerprints(tokenize(b, "cpp"), k, w)
    assert set(fa) & set(fb)
