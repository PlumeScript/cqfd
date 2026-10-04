# L1: pbEvalLin — evaluate a linear combination ax +/- by +/- cz drawn over
# the boulangerie context (#128). Runs tests/pbeval_lin_driver.plume under
# the installed plume, then checks, per question:
#   - shape (class contract): itemCount in {2,3}, first term positive, no
#     zero count, at most two bare prices (|c| == 1), at least one full
#     count (|c| >= 2), total > 0,
#   - arithmetic: solution == sum(c_i * d_i) / 10 exact (d in tenths of
#     euro), and the rendered formula evaluates to the same total,
#   - id: "<itemCount>-<select joined>" consistent with the counts,
#   - instruction: named prose ("Marc est allé / Lise est allée" — the
#     past participle agrees with the name — or the "Je suis allé / mon
#     ticket" form without a name), per-item quantity/name(s)/price in
#     order, coupon wording for negative terms, ", " / " et " separators,
#   - solution: formula rhs equals the solution, \times iff some |c| >= 2,
#     prose ending in "€.".
# The decimal separator is locale dependent (point here, comma for the
# user): never hardcode it — numbers are matched with [.,].
import os
import re
import subprocess

LUAJIT = r"F:\Dropbox\proj\code\dev\plume\plume\bin\luajit.exe"
INIT = r"F:\Dropbox\proj\code\dev\plume\plume\plume-data\cli\init.lua"
ROOT = r"F:\Dropbox\proj\code\dev\plume\plume" + "\\"
DRIVER = "tests\\pbeval_lin_driver.plume"


def fail(msg, extra=""):
    print("FAIL: %s" % msg)
    if extra:
        print(str(extra)[:3000])
    print("INVALIDE")
    return 1


def locale_num(x):
    """regex for a number rendered by the user locale (point or comma)."""
    return re.escape("%g" % x).replace("\\.", "[.,]")


def eval_formula(f):
    """evaluate a flat 'a+b\\times c-d' formula (locale decimal comma ok)."""
    f = f.replace(",", ".")
    total = 0.0
    for part in re.split(r"(?=[+-])", f):
        if not part:
            continue
        neg = part.startswith("-")
        if neg:
            part = part[1:]
        v = 1.0
        for x in part.replace("\\times", "*").split("*"):
            v *= float(x)
        total += -v if neg else v
    return total


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
    pat = re.compile(r"==Q-(\d+)-(\d+)====META\|([^=]+)====I==(.*?)==S==(.*?)==END==", re.S)
    for m in pat.finditer(out):
        pass_id, idx, meta, instr, sol = m.groups()
        try:
            fields = dict(kv.split(":", 1) for kv in meta.split("|") if ":" in kv)
            n = int(fields["n"])
            cs = [int(fields["c%d" % k]) for k in range(1, 4)][:n]
            ds = [int(fields["d%d" % k]) for k in range(1, 4)][:n]
            nms = [fields["nm%d" % k] for k in range(1, 4)][:n]
            pls = [fields["pl%d" % k] for k in range(1, 4)][:n]
            solution = float(fields["sol"])
            qid = fields["id"]
            who = fields["who"]
        except Exception as e:
            return fail("bad META in Q%s-%s (%s)" % (pass_id, idx, e), meta)
        qs.append(dict(pass_id=pass_id, idx=idx, n=n, cs=cs, ds=ds, nms=nms, pls=pls,
                       sol=solution, soltext=sol, instr=instr, id=qid, who=who))

    if len(qs) < 25:
        return fail("too few questions (%d < 25)" % len(qs))

    for q in qs:
        tag = "Q%s-%s" % (q["pass_id"], q["idx"])
        n, cs, ds = q["n"], q["cs"], q["ds"]
        sol = q["sol"]
        instr, soltext = q["instr"], q["soltext"]
        who = q["who"]
        # the name is a per-question hyperparameter: pass 1 has none,
        # pass 2 draws Marc (m) or Lise (f)
        if q["pass_id"] == "1" and who != "0":
            return fail("%s: pass 1 question with a name (%r)" % (tag, who))
        if q["pass_id"] == "2" and who not in ("Marc", "Lise"):
            return fail("%s: pass 2 question without a known name (%r)" % (tag, who))

        # shape: the class contract
        if n not in (2, 3):
            return fail("%s: itemCount %d outside {2,3}" % (tag, n))
        if cs[0] <= 0:
            return fail("%s: first term not positive (c1=%d)" % (tag, cs[0]))
        if any(c == 0 for c in cs):
            return fail("%s: a zero count (c=%s)" % (tag, cs))
        if sum(1 for c in cs if abs(c) == 1) > 2:
            return fail("%s: more than two bare prices (c=%s)" % (tag, cs))
        if not any(abs(c) >= 2 for c in cs):
            return fail("%s: no full count (c=%s)" % (tag, cs))
        if sol <= 0:
            return fail("%s: non-positive total (%.1f)" % (tag, sol))

        # arithmetic: the solution is the exact sum, in tenths of euro
        expect = sum(c * d for c, d in zip(cs, ds)) / 10
        if abs(expect - sol) > 1e-9:
            return fail("%s: solution %.1f != expected %.1f (c=%s d=%s)"
                        % (tag, sol, expect, cs, ds))

        # id: "<n>-<select>" with select 0/1/2 == bare/plus/minus
        sel = [0 if c == 1 else (1 if c > 0 else 2) for c in cs]
        if n < 3:
            sel.append(0)
        expect_id = "%d-%s" % (n, "".join(map(str, sel)))
        if q["id"] != expect_id:
            return fail("%s: id %s != expected %s (c=%s)" % (tag, q["id"], expect_id, cs))

        # instruction prose: the opening depends on the name, and the
        # participle agrees with it (Lise → allée)
        if who == "0":
            opening = "Je suis allé à la boulangerie, mon ticket de caisse indique : "
        else:
            went = "est allée" if who == "Lise" else "est allé"
            opening = "%s %s à la boulangerie, son ticket de caisse indique : " % (who, went)
        if not instr.startswith(opening):
            return fail("%s: instruction without the opening %r" % (tag, opening), instr)
        closing = ". Quel est le montant total à payer ?"
        if not instr.endswith(closing):
            return fail("%s: instruction without the total question" % tag, instr)
        # count the separators in the item list only (the opening has one ", ")
        body = instr[len(opening):len(instr) - len(closing)]
        if body.count(" et ") != 1:
            return fail("%s: expected one ' et ' separator (n=%d)" % (tag, n), instr)
        if n >= 3 and body.count(", ") != n - 2:
            return fail("%s: expected %d ', ' separators (n=%d)" % (tag, n - 2, n), instr)

        # per item: quantity, name(s), price — in the list order
        pos = -1
        for k in range(n):
            c, d, name, plural = cs[k], ds[k], q["nms"][k], q["pls"][k]
            price_str = "%g" % (d / 10)
            if c < 0:
                word = "coupon" if -c == 1 else "coupons"
                plain = "%d %s de réduction (%s € pièce)" % (-c, word, price_str)
            else:
                word = name if c == 1 else plural
                plain = "%d %s (%s € pièce)" % (c, word, price_str)
            # escape the whole fragment, then relax the decimal separator
            frag = re.escape(plain).replace(re.escape(price_str), locale_num(d / 10))
            m = re.search(frag, instr)
            if not m:
                return fail("%s: item %d fragment missing (%r)" % (tag, k + 1, frag), instr)
            if m.start() <= pos:
                return fail("%s: item %d out of order (%r)" % (tag, k + 1, frag), instr)
            pos = m.start()

        # solution: the formula equals the solution, the prose wraps it
        m = re.search(r"pages--as-inline\">(.*?)</script>", soltext, re.S)
        if not m:
            return fail("%s: solution without a formula" % tag, soltext)
        formula = m.group(1)
        if "=" not in formula:
            return fail("%s: formula without '='" % tag, formula)
        lhs, rhs = formula.split("=", 1)
        ev = eval_formula(lhs.strip())
        if abs(ev - sol) > 1e-9:
            return fail("%s: formula %r evaluates to %.1f != solution %.1f"
                        % (tag, lhs, ev, sol))
        try:
            rhs_v = float(rhs.strip().replace(",", "."))
        except ValueError:
            return fail("%s: formula rhs not a number (%r)" % (tag, rhs), formula)
        if abs(rhs_v - sol) > 1e-9:
            return fail("%s: formula rhs %.1f != solution %.1f" % (tag, rhs_v, sol), formula)
        if ("\\times" in lhs) != any(abs(c) >= 2 for c in cs):
            return fail("%s: \\times presence inconsistent with c=%s" % (tag, cs), formula)
        if "Le montant total à payer est de" not in soltext:
            return fail("%s: solution without the prose" % tag, soltext)
        if not soltext.endswith("€."):
            return fail("%s: solution prose does not end in '€.'" % tag, soltext)

    # coverage: the fixed-seed stream must exercise every branch
    if not any(q["n"] == 2 for q in qs):
        return fail("no 2-item question in the draw stream")
    if not any(q["n"] == 3 for q in qs):
        return fail("no 3-item question in the draw stream")
    if not any(c < 0 for q in qs for c in q["cs"]):
        return fail("no negative (coupon) term in the draw stream")
    if not any(c == 1 for q in qs for c in q["cs"]):
        return fail("no bare-price term in the draw stream")
    if not any(q["who"] == "0" for q in qs):
        return fail("no nameless (je) question in the draw stream")
    if not any(q["who"] == "Marc" for q in qs):
        return fail("no Marc question in the draw stream")
    if not any(q["who"] == "Lise" for q in qs):
        return fail("no Lise question in the draw stream")

    print("OK: %d questions checked (shape, arithmetic, id, prose, formulas)" % len(qs))
    print("VALIDE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
