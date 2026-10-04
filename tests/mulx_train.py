# L1: coherent rewrite of the mulX formulation (level-indexed templates) +
# train proposition (named "chef de ligne" character + division, #129).
#
# Runs tests/mulx_train_driver.plume under the installed plume, then checks:
#   - arithmetic (total = product of the first d+1 factors; solution = the
#     hidden factor for division, the total for multiplication; the chain
#     fits the 4-level vocabulary; division only in train; train start <= 2),
#   - rendered instructions/solutions (train prose, generic prose,
#     \div / \times formulas, "donc" in the division solutions),
#   - trap (the level just below the target): present for train
#     (start, depth) in {(1,1), (2,1), (1,2)} with trap: true, absent
#     with trap: false; those three are the only (start, depth) where the
#     trap sentence is textually distinguishable from a chain link.
import os
import re
import subprocess

LUAJIT = r"F:\Dropbox\proj\code\dev\plume\plume\bin\luajit.exe"
INIT = r"F:\Dropbox\proj\code\dev\plume\plume\plume-data\cli\init.lua"
ROOT = r"F:\Dropbox\proj\code\dev\plume\plume" + "\\"
DRIVER = "tests\\mulx_train_driver.plume"

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
        is_train = ctx == "train"
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
        if division and not is_train:
            return fail("%s: division outside the train context (ctx=%s)" % (tag, ctx))
        if is_train and start > 2:
            return fail("%s: train with start > 2 (start=%d)" % (tag, start))

        # rendered instruction
        if is_train:
            if "chef de ligne" not in instr:
                return fail("%s: train instruction without the character" % tag, instr)
        else:
            if "Il y a" not in instr:
                return fail("%s: generic instruction without a top sentence" % tag, instr)
            if "En tout, combien y a-t-il d" not in instr:
                return fail("%s: generic instruction without the total question" % tag, instr)
        if is_train and division:
            if "En tout, il y a" not in instr:
                return fail("%s: division instruction without the given total" % tag, instr)
            if "div" not in soltext:
                return fail("%s: division formula without \\div" % tag, soltext)
        if not division and "times" not in soltext:
            return fail("%s: multiplication formula without \\times" % tag, soltext)
        if is_train and ("donc" in soltext) != division:
            return fail("%s: 'donc' in the solution inconsistent with division" % tag, soltext)

        # trap: the level just below the target
        if is_train and (start, d) in TRAP_CLASSES:
            trap_text = ("Chaque train a " in instr) or ("Chaque wagon a " in instr)
            if q["pass_id"] == "1" and not trap_text:
                return fail("%s: train trap missing (start=%d d=%d)" % (tag, start, d), instr)
            if q["pass_id"] == "2" and trap_text:
                return fail("%s: train trap present with trap=false (start=%d d=%d)" % (tag, start, d), instr)

    # coverage of the classes the checks rely on
    classes = {(q["ctx"] == "train", q["u"] <= q["d"]) for q in qs}
    for needed, label in [((True, True), "train division"),
                          ((True, False), "train multiplication"),
                          ((False, False), "generic multiplication")]:
        if needed not in classes:
            return fail("no %s question in the draw stream" % label)
    if (False, True) in classes:
        return fail("a generic division question leaked")
    seen = {(q["start"], q["d"]) for q in qs if q["ctx"] == "train" and q["pass_id"] == "1"}
    missing = TRAP_CLASSES - seen
    if missing:
        print("WARN: no pass-1 train question for (start, depth) in %s — trap not checked there" % sorted(missing))

    print("OK: %d questions checked (arithmetic, prose, formulas, traps)" % len(qs))
    print("VALIDE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
