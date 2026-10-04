# L1: the mulX specific contexts (#129). Every context is a self-contained
# situation (named character + own prose) in the `situations` list of
# generators/calc/situations/mulX.plume; matrioska draws them by index
# (Range(1, len(situations))), so the stream mixes all contexts.
#
# Runs tests/mulx_train_driver.plume under the installed plume, then checks:
#   - arithmetic (total = product of the first d+1 factors; solution = the
#     hidden factor for division, the total for multiplication; the chain
#     fits the 4-level vocabulary; start <= maxStart per context),
#   - rendered instructions (the context's role is present and gendered with
#     the named character, \div / \times formulas, "donc" in the division
#     solutions),
#   - the instruction gives every known value (multiplication: all d+1
#     factors; division: the other factors + the total), otherwise the
#     question is unsolvable,
#   - trap (the level just below the target, values[d+2]): present in pass 1
#     (trap: true), absent in pass 2 (trap: false) — checked numerically for
#     every context, and by the train trap sentence for train.
import os
import re
import subprocess

LUAJIT = r"F:\Dropbox\proj\code\dev\plume\plume\bin\luajit.exe"
INIT = r"F:\Dropbox\proj\code\dev\plume\plume\plume-data\cli\init.lua"
ROOT = r"F:\Dropbox\proj\code\dev\plume\plume" + "\\"
DRIVER = "tests\\mulx_train_driver.plume"

# per context: the role words (the feminine is None when the role is
# invariable) and the highest allowed top level (matrioska rejects
# start > maxStart).
CONTEXTS = {
    "train":    dict(role_m="chef de ligne", role_f="cheffe de ligne", maxStart=2),
    "chocolat": dict(role_m="chocolatier", role_f="chocolatière", maxStart=3),
    "collège":  dict(role_m="professeur", role_f="professeure", maxStart=3),
    "arbre":    dict(role_m="jardinier", role_f="jardinière", maxStart=3),
    "ville":    dict(role_m="conseiller régional", role_f="conseillère régionale", maxStart=3),
    "magasin":  dict(role_m="commerçant", role_f="commerçante", maxStart=3),
    "salle":    dict(role_m="conservateur", role_f="conservatrice", maxStart=3),
    "caisse":   dict(role_m="gérant", role_f="gérante", maxStart=3),
    "haras":    dict(role_m="écuyer", role_f="écuyère", maxStart=3),
    "étoile":   dict(role_m="astronome", role_f=None, maxStart=3),
}

# the (start, depth) pairs where the train trap sentence is textually
# distinguishable from a chain link (in (1,3), link[4] == trap[4]).
TRAP_CLASSES = {(1, 1), (2, 1), (1, 2)}


def fail(msg, extra=""):
    print("FAIL: %s" % msg)
    if extra:
        print(str(extra)[:3000])
    print("INVALIDE")
    return 1


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    cmd = [LUAJIT, INIT, ROOT, "-i", DRIVER]
    # plume emits UTF-8 and no newlines between template lines: the whole
    # stream is one line, the ==MARKERS== delimit the sections.
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=root)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        return fail("plume driver exited rc=%d" % proc.returncode, out)
    low = out.lower()
    if "runtime" in low or "syntax" in low:
        return fail("plume error in output", out)
    if "==DONE==" not in out:
        return fail("no ==DONE== marker (driver incomplete)", out)

    qs = []
    pat = re.compile(r"==Q(\d+)-(\d+)====META\|([^=]+)====I==(.*?)==S==(.*?)==END==", re.S)
    for m in pat.finditer(out):
        pass_id, idx, meta, instr, sol = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        try:
            fields = dict(kv.split(":", 1) for kv in meta.split("|") if ":" in kv)
            ctx = fields["ctx"]
            start, u, d = int(fields["start"]), int(fields["u"]), int(fields["d"])
            vals = [int(v) for v in fields["vals"].split(",")]
            total, solution = int(fields["total"]), int(fields["sol"])
        except Exception as e:
            return fail("bad META in Q%s-%s (%s)" % (pass_id, idx, e), meta)
        qs.append(dict(pass_id=pass_id, idx=idx, ctx=ctx, start=start, u=u, d=d,
                       vals=vals, total=total, sol=solution, instr=instr, soltext=sol))

    n1 = sum(1 for q in qs if q["pass_id"] == "1")
    print("questions: %d (pass1 trap=true: %d, pass2 trap=false: %d)" % (len(qs), n1, len(qs) - n1))
    if len(qs) < 25:
        return fail("too few questions (%d < 25)" % len(qs))

    for q in qs:
        tag = "Q%s-%s" % (q["pass_id"], q["idx"])
        ctx, start, u, d = q["ctx"], q["start"], q["u"], q["d"]
        vals, total, solution = q["vals"], q["total"], q["sol"]
        instr, soltext = q["instr"], q["soltext"]
        if ctx not in CONTEXTS:
            return fail("%s: unknown context %s" % (tag, ctx), instr)
        cfg = CONTEXTS[ctx]
        division = u <= d

        # arithmetic
        expect_total = 1
        for v in vals[:d + 1]:
            expect_total *= v
        if total != expect_total:
            return fail("%s: total %d != product %d (vals=%s d=%d)" % (tag, total, expect_total, vals, d))
        expect_sol = vals[u - 1] if division else total
        if solution != expect_sol:
            return fail("%s: solution %d != expected %d (u=%d d=%d)" % (tag, solution, expect_sol, u, d))
        if start + d > 4:
            return fail("%s: chain does not fit the 4-level vocabulary (start=%d d=%d)" % (tag, start, d))
        if start > cfg["maxStart"]:
            return fail("%s: %s with start %d > maxStart %d" % (tag, ctx, start, cfg["maxStart"]), instr)

        # rendered instruction: the context's named character
        role_m, role_f = cfg["role_m"], cfg["role_f"]
        if role_f is None:
            role_f = role_m
        if role_m not in instr and role_f not in instr:
            return fail("%s: %s instruction without the role" % (tag, ctx), instr)
        # the title is gendered with the named character
        if "Sophie" in instr and role_f not in instr:
            return fail("%s: Sophie must be %s" % (tag, role_f), instr)
        if "Pierre" in instr and role_m not in instr:
            return fail("%s: Pierre must be %s" % (tag, role_m), instr)
        if "Pierre" in instr and role_f != role_m and role_f in instr:
            return fail("%s: Pierre must not be %s" % (tag, role_f), instr)
        if division:
            if "En tout, il y a" not in instr:
                return fail("%s: division instruction without the given total" % tag, instr)
            if "div" not in soltext:
                return fail("%s: division formula without \\div" % tag, soltext)
        if not division and "times" not in soltext:
            return fail("%s: multiplication formula without \\times" % tag, soltext)
        if ("donc" in soltext) != division:
            return fail("%s: 'donc' in the solution inconsistent with division" % tag, soltext)

        # the instruction must give every value that is known, otherwise the
        # question is unsolvable (multiplication: all d+1 factors; division:
        # the other factors + the total)
        nums = [int(v) for v in re.findall(r">(\d+)</script>", instr)]
        if division:
            required = [v for k, v in enumerate(vals, 1) if k <= d + 1 and k != u] + [total]
        else:
            required = vals[:d + 1]
        for v in required:
            if v not in nums:
                return fail("%s: instruction misses given value %d (needed %s)" % (tag, v, required), instr)

        # trap: the count of the level just below the target (values[d+2])
        if start + d + 1 <= 4:
            trapval = vals[d + 1]
            if q["pass_id"] == "1":
                if trapval not in nums:
                    return fail("%s: trap value %d missing (start=%d d=%d)" % (tag, trapval, start, d), instr)
            elif trapval not in set(required) and trapval in nums:
                return fail("%s: trap value %d present with trap=false (start=%d d=%d)" % (tag, trapval, start, d), instr)
            # the train trap sentence, where it is textually distinguishable
            if ctx == "train" and (start, d) in TRAP_CLASSES:
                trap_text = ("Chaque train a " in instr) or ("Chaque wagon a " in instr)
                if q["pass_id"] == "1" and not trap_text:
                    return fail("%s: train trap sentence missing (start=%d d=%d)" % (tag, start, d), instr)
                if q["pass_id"] == "2" and trap_text:
                    return fail("%s: train trap sentence present with trap=false (start=%d d=%d)" % (tag, start, d), instr)

    # coverage: every context, both operation kinds
    seen_ctx = {q["ctx"] for q in qs}
    missing = set(CONTEXTS) - seen_ctx
    if missing:
        return fail("no question for context(s) %s" % sorted(missing))
    classes = {q["u"] <= q["d"] for q in qs}
    for needed, label in [(True, "division"), (False, "multiplication")]:
        if needed not in classes:
            return fail("no %s question in the draw stream" % label)
    seen = {(q["start"], q["d"]) for q in qs if q["ctx"] == "train" and q["pass_id"] == "1"}
    missing = TRAP_CLASSES - seen
    if missing:
        print("WARN: no pass-1 train question for (start, depth) in %s — trap not checked there" % sorted(missing))

    print("OK: %d questions checked (arithmetic, prose, formulas, traps)" % len(qs))
    print("VALIDE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
