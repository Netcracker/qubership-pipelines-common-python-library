from qubership_pipelines_common_library.v2.artifacts_finder.comparers.default_version_comparer import DefaultVersionComparer

# (v1, v2, description, expected)
# expected: -2 major upgrade, -1 minor/patch upgrade or lex smaller,
#            0 equal, +1 minor/patch downgrade or lex greater, +2 major downgrade
VERSION_COMPARE_CASES = [
    # --- SEMVER vs SEMVER -------------------------------------------------
    ("1.0.0",  "2.0.0",   "major upgrade",                         -2),
    ("2.0.0",  "1.9.9",   "major downgrade",                        2),
    ("1.2.3",  "1.2.3",   "identical versions",                     0),
    ("1.2.3",  "1.2.4",   "patch increment",                       -1),
    ("1.3.0",  "1.2.99",  "minor beats large patch",                1),
    ("0.0.1",  "0.0.2",   "tiny patch diff",                       -1),
    ("10.0.0", "9.99.99", "major downgrade (numeric, not lex)",     2),

    ("v26.2_main_r1.1.0-20260525.103047-1-RELEASE", "v26.2_main_r1.1.0-20260525.103047-1-RELEASE",    "same build, identical semver",          0),
    ("v26.2_main_r1.1.0-20260525.103047-1-RELEASE", "v26.2_main_r1.2.0-20270525.103047-1-RELEASE",    "same prefix, minor increment",         -1),
    ("v26.2_main_r1.2.0-20260525.103047-1-RELEASE", "v26.3_main_r1.1.0-20270525.103047-1-RELEASE",    "release increment",                    -1),
    ("release-1.0.0-20231116.090331-1-RELEASE",      "release-1.1.0-20241116.090331-1-RELEASE",       "release branch, minor increment",      -1),
    ("v1.2.0-20260525.052827-13885121-RELEASE",       "v1.10.0-20260625.052827-13885121-RELEASE",     "minor 2 vs 10, numeric wins over lex", -1),
    ("v1.0.5-20260505.110551-13623799-RELEASE",       "v10.0.5-20260605.110551-13623799-RELEASE",     "major upgrade 1 -> 10",                -2),
    ("master-20260512.013338-63-RELEASE",             "master-20260612.013338-64-RELEASE",            "no semver, lexico by timestamp",       -1),
    ("release-2026-1-1_20260209-012147-20260209.012800-1-RELEASE", "release-2026-2-1_20260209-012147-20260209.012800-2-RELEASE", "no semver, lexico by date segment", -1),
    ("v2.10.4-cloud_dd-20260601.080053-1-RELEASE",    "v2.106.4-cloud_dd-20260601.080053-2-RELEASE",  "minor 10 vs 106, same major",          -1),
    ("v2.106.3-cloud_dd-20260601.080053-1-RELEASE",   "v2.107.1-cloud_dd-20260601.080053-1-RELEASE",  "minor 106 vs 107, same major",         -1),
    ("v2.106.3-cloud_dd-20260601.080053-1-RELEASE",   "v3.1.1-cloud_dd-20250601.080053-1-RELEASE",    "major upgrade 2 -> 3 (cloud_dd)",      -2),
    ("v2.5.1-20260513.075133-1-RELEASE",              "v3.4.1-20260513.075133-2-RELEASE",             "major upgrade 2 -> 3",                 -2),
    ("v2.81.5-20260519.042017-6-RELEASE",             "v2.82.5-20260519.042017-6-RELEASE",            "minor increment, same major",          -1),
    ("v0.41.3-20260529.075449-1-RELEASE",             "v1.4.3-20260530.075449-1-RELEASE",             "major upgrade 0 -> 1",                 -2),
    ("release-20260508.064312-67-RELEASE", "release-20270508.064312-1-RELEASE", "no semver, lexico by year in timestamp", -1),
    ("pg18-1.53.7-20260508.113626-2-RELEASE",         "pg18-1.54.6-20260408.113626-1-RELEASE",          "pg18, minor increment",                -1),
    ("pg18-1.53.7-20260508.113626-2-RELEASE",         "pg18-2.4.80-20260408.113626-2-RELEASE",          "pg18, major upgrade 1 -> 2",           -2),
    ("pg18-1.53.7-20260508.113626-2-RELEASE",         "pg17-2.4.80-20260408.113626-2-RELEASE",          "prefix pg18 > pg17, prefix wins before semver", 1),
    ("1.53.7-supplementary-20260508.113557-2-RELEASE", "2.1.1-supplementary-20260506.113557-1-RELEASE", "no prefix, major upgrade 1 -> 2",      -2),
    ("arango3.11-0.47.4-20260503.152239-6-RELEASE",   "arango3.11-0.50.2-20260503.152239-5-RELEASE",    "arango, minor 47 vs 50, major both 0", -1),
    ("clickhouse243-0.45.1-20260520.031714-1-RELEASE", "clickhouse243-0.5.1-20260520.021714-1-RELEASE", "minor 45 vs 5, major both 0: 45 > 5",   1),
    ("0.45.1-supplementary-20260520.031302-1-RELEASE", "0.50.1-supplementary-20260520.031302-1-RELEASE", "no prefix, minor 45 vs 50, major both 0", -1),
    ("zk3-0.11.17-20260416.070721-4-RELEASE",         "zk3-1.0.0-20260416.070721-3-RELEASE",            "zk3, major upgrade 0 -> 1",              -2),
    ("0.7.9-20260417.102956-4-RELEASE",               "0.18.5-20260417.102956-2-RELEASE",               "no prefix, minor 7 vs 18, major both 0", -1),
    ("redis-crd-4.2.4-20260525.064429-1-RELEASE",     "redis-crd-4.11.1-20260525.064429-1-RELEASE",     "redis-crd, minor 2 vs 11, same major",   -1),
    ("v3.10.1-charts_argocd-20260504.081015-2-RELEASE", "v3.11.1-charts_argocd-20260504.081015-2-RELEASE", "argocd charts, minor 10 vs 11, same major", -1),

    # --- mixed / non-SEMVER -----------------------------------------------
    ("1.0",           "1.0.0",         "missing patch -> lexicographic",        -1),
    ("v1.0.0",        "v2.0.0",        "semver with v-prefix, major upgrade",   -2),
    ("alpha",         "beta",          "plain words",                           -1),
    ("1.0.0-rc.1",    "1.0.0",         "same semver, suffix makes it greater",   1),
    ("abc",           "abc",           "equal strings",                          0),
    ("2.0",           "10.0",          "lex: '2' > '1' even though 2 < 10",      1),
    ("release-1.2.3", "release-1.2.4", "prefixed release strings",              -1),
]


class TestDefaultVersionComparer:

    def test_compare(self):
        comparer = DefaultVersionComparer()
        failures = []
        for v1, v2, desc, expected in VERSION_COMPARE_CASES:
            actual = comparer.compare(v1, v2)
            if actual != expected:
                failures.append(f"  [{desc}] compare({v1!r}, {v2!r}) -> {actual}, expected {expected}")
            swapped = comparer.compare(v2, v1)
            if swapped != -expected:
                failures.append(f"  [{desc}] compare({v2!r}, {v1!r}) -> {swapped}, expected {-expected}")
        assert not failures, f"{len(failures)} version comparison(s) failed:\n" + "\n".join(failures)
