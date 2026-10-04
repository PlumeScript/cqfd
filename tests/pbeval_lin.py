# L1: pbEvalLin — evaluate a linear combination ax +/- by +/- cz over the six
# situations (#128: boulangerie, papeterie, dinoshop, cinema, marche,
# librairie). Runs tests/pbeval_lin_driver.plume under the installed plume,
# then checks, per question:
#   - shape (class contract): itemCount in {2,3}, first term positive, no
#     zero count, at most two bare prices (|c| == 1), at least one full
#     count (|c| >= 2), total > 0,
#   - catalog: per item, the unit and the negative labels match the
#     situation's catalog, the price (dec, tenths of euro) is inside the
#     catalog range, and a full count (|c| >= 2) stays below countMax,
#   - arithmetic: solution == sum(c_i * d_i) / 10 exact, and the rendered
#     formula evaluates to the same total,
#   - id: "<itemCount>-<select joined>" consistent with the counts,
#   - instruction: the situation's opening (named — "est allé(e)" agrees
#     with the name — or the "je" form), per-item quantity/label/price in
#     order ("N kg de <plural> (P € le kilo)" for kilo items, "N <label>
#     (P € <unit>)" otherwise), ", " / " et " separators,
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

# Situation catalog: per context, the "je" opening and the item data
# name -> (unit, minDec, maxDec, countMax, negS, negP). Dec ranges are in
# tenths of euro (boulangerie gâteau: 10..50 € -> 100..500).
CONTEXTS = {
    "boulangerie": {
        "je": "Je suis allé à la boulangerie, mon ticket de caisse indique : ",
        "items": {
            "baguette": ("pièce", 5, 10, 20, "coupon de réduction", "coupons de réduction"),
            "croissant": ("pièce", 8, 12, 20, "coupon de réduction", "coupons de réduction"),
            "pain au chocolat": ("pièce", 8, 12, 20, "coupon de réduction", "coupons de réduction"),
            "gâteau": ("pièce", 100, 500, 5, "coupon de réduction", "coupons de réduction"),
        },
    },
    "papeterie": {
        "je": "J'ai fait mes fournitures scolaires à la papeterie. Mon ticket de caisse indique : ",
        "items": {
            "cahier": ("pièce", 22, 35, 6, "coupon de la carte élève", "coupons de la carte élève"),
            "règle": ("pièce", 15, 25, 5, "coupon de la carte élève", "coupons de la carte élève"),
            "crayon à papier": ("pièce", 8, 15, 10, "coupon de la carte élève", "coupons de la carte élève"),
            "gomme": ("pièce", 10, 20, 8, "coupon de la carte élève", "coupons de la carte élève"),
            "tube de colle": ("pièce", 15, 40, 4, "coupon de la carte élève", "coupons de la carte élève"),
        },
    },
    "dinoshop": {
        "je": "Je suis allé au dino-shop, mon ticket de caisse indique : ",
        "items": {
            "baby T-rex": ("pièce", 1500, 3500, 2, "baby T-rex rendu", "baby T-rex rendus"),
            "sac de viande préhistorique": ("pièce", 60, 120, 8, "sac de viande préhistorique rendu", "sacs de viande préhistorique rendus"),
            "os à mâcher": ("pièce", 50, 100, 6, "os à mâcher cassé rendu", "os à mâcher cassés rendus"),
            "jus de dinosaure": ("pièce", 30, 60, 4, "jus de dinosaure rendu", "jus de dinosaure rendus"),
        },
    },
    "cinema": {
        "je": "Je suis allé au cinéma, mon ticket de caisse indique : ",
        "items": {
            "place": ("pièce", 80, 110, 4, "place rendue", "places rendues"),
            "popcorn": ("pièce", 40, 70, 3, "popcorn rendu", "popcorns rendus"),
            "soda": ("pièce", 35, 50, 3, "soda rendu", "sodas rendus"),
            "bonbon": ("pièce", 20, 35, 4, "bonbon rendu", "bonbons rendus"),
        },
    },
    "marche": {
        "je": "J'ai fait mes courses au marché. Mon ticket indique : ",
        "items": {
            "pomme": ("le kilo", 20, 35, 5, "pommes abîmées rendues", "pommes abîmées rendues"),
            "fraise": ("le kilo", 50, 80, 4, "fraises abîmées rendues", "fraises abîmées rendues"),
            "tomate": ("le kilo", 30, 50, 4, "tomates abîmées rendues", "tomates abîmées rendues"),
            "melon": ("pièce", 40, 70, 3, "melon abîmé rendu", "melons abîmés rendus"),
            "pot de miel": ("le pot", 30, 60, 3, "pot de miel fêlé rendu", "pots de miel fêlés rendus"),
        },
    },
    "librairie": {
        "je": "J'ai acheté des livres à la librairie. Mon ticket de caisse indique : ",
        "items": {
            "roman": ("pièce", 65, 100, 5, "roman rendu", "romans rendus"),
            "bande dessinée": ("pièce", 70, 120, 5, "bande dessinée rendue", "bandes dessinées rendues"),
            "magazine": ("pièce", 50, 80, 4, "magazine rendu", "magazines rendus"),
            "atlas": ("pièce", 120, 200, 2, "atlas rendu", "atlas rendu"),
            "livre de cuisine": ("pièce", 150, 250, 2, "livre de cuisine rendu", "livres de cuisine rendus"),
        },
    },
}


def opening_for(ctx, who):
    """the expected opening (up to and including the space before item 1)."""
    if who == "0":
        return CONTEXTS[ctx]["je"]
    if ctx == "boulangerie":
        went = "est allée" if who == "Lise" else "est allé"
        return "%s %s à la boulangerie, son ticket de caisse indique : " % (who, went)
    if ctx == "dinoshop":
        went = "est allée" if who == "Lise" else "est allé"
        return "%s %s au dino-shop, son ticket de caisse indique : " % (who, went)
    if ctx == "cinema":
        went = "est allée" if who == "Lise" else "est allé"
        return "%s %s au cinéma, son ticket de caisse indique : " % (who, went)
    if ctx == "papeterie":
        return "%s a fait ses fournitures scolaires à la papeterie. Son ticket de caisse indique : " % who
    if ctx == "marche":
        return "%s a fait ses courses au marché. Son ticket indique : " % who
    if ctx == "librairie":
        return "%s a acheté des livres à la librairie. Son ticket de caisse indique : " % who
    raise ValueError("unknown context %r" % ctx)


def fail(msg, extra=""):
    print("FAIL: %s" % msg)
    if extra:
        print(str(extra)[:3000])
    print("INVALIDE")
    return 1


def locale_num(x):
    """regex for a number rendered by the user locale (point or comma)."""
    return re.escape("%g" % x).replace("\\.", "[.,]")


def item_fragment(c, d, name, plural, unit, negS, negP):
    """regex for one ticket line (the decimal separator is relaxed)."""
    price = d / 10.0
    pstr = "%g" % price
    if unit == "le kilo":
        label = negP if c < 0 else plural
        plain = "%d kg de %s (%s € le kilo)" % (abs(c), label, pstr)
    elif c < 0:
        label = negS if -c == 1 else negP
        plain = "%d %s (%s € %s)" % (-c, label, pstr, unit)
    else:
        label = name if c == 1 else plural
        plain = "%d %s (%s € %s)" % (c, label, pstr, unit)
    return re.escape(plain).replace(re.escape(pstr), locale_num(price))


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
    pat = re.compile(r"==Q-(\d+)-(\d+)-([a-z]+)====META\|([^=]+)====I==(.*?)==S==(.*?)==END==", re.S)
    for m in pat.finditer(out):
        pass_id, idx, mctx, meta, instr, sol = m.groups()
        try:
            fields = dict(kv.split(":", 1) for kv in meta.split("|") if ":" in kv)
            if fields["ctx"] != mctx:
                return fail("Q%s-%s: marker ctx %r != META ctx %r" % (pass_id, idx, mctx, fields["ctx"]))
            n = int(fields["n"])
            cs = [int(fields["c%d" % k]) for k in range(1, 4)][:n]
            ds = [int(fields["d%d" % k]) for k in range(1, 4)][:n]
            nms = [fields["nm%d" % k] for k in range(1, 4)][:n]
            pls = [fields["pl%d" % k] for k in range(1, 4)][:n]
            us = [fields["u%d" % k] for k in range(1, 4)][:n]
            nss = [fields["ns%d" % k] for k in range(1, 4)][:n]
            nps = [fields["np%d" % k] for k in range(1, 4)][:n]
            solution = float(fields["sol"])
            qid = fields["id"]
            who = fields["who"]
        except Exception as e:
            return fail("bad META in Q%s-%s (%s)" % (pass_id, idx, e), meta)
        qs.append(dict(pass_id=pass_id, idx=idx, ctx=mctx, n=n, cs=cs, ds=ds, nms=nms,
                       pls=pls, us=us, nss=nss, nps=nps, sol=solution, soltext=sol,
                       instr=instr, id=qid, who=who))

    if len(qs) < 200:
        return fail("too few questions (%d < 200)" % len(qs))

    for q in qs:
        tag = "Q%s-%s-%s" % (q["pass_id"], q["idx"], q["ctx"])
        n, cs, ds = q["n"], q["cs"], q["ds"]
        sol = q["sol"]
        instr, soltext = q["instr"], q["soltext"]
        who, ctx = q["who"], q["ctx"]
        if ctx not in CONTEXTS:
            return fail("%s: unknown context %r" % (tag, ctx))
        catalog = CONTEXTS[ctx]["items"]
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

        # instruction prose: the opening depends on the context and the
        # name, the "est allé(e)" forms agree with it (Lise -> allée)
        opening = opening_for(ctx, who)
        if not instr.startswith(opening):
            return fail("%s: instruction without the opening %r" % (tag, opening), instr)
        closing = ". Quel est le montant total à payer ?"
        if not instr.endswith(closing):
            return fail("%s: instruction without the total question" % tag, instr)
        # count the separators in the item list only (some openings have
        # their own ", ")
        body = instr[len(opening):len(instr) - len(closing)]
        if body.count(" et ") != 1:
            return fail("%s: expected one ' et ' separator (n=%d)" % (tag, n), instr)
        if n >= 3 and body.count(", ") != n - 2:
            return fail("%s: expected %d ', ' separators (n=%d)" % (tag, n - 2, n), instr)

        # per item: catalog data, then the quantity/label/price fragment,
        # in the list order
        pos = -1
        for k in range(n):
            c, d = cs[k], ds[k]
            name, plural = q["nms"][k], q["pls"][k]
            unit, ns, np_ = q["us"][k], q["nss"][k], q["nps"][k]
            if name not in catalog:
                return fail("%s: item %d unknown in the %s catalog (%r)"
                            % (tag, k + 1, ctx, name), instr)
            unit0, mn, mx, cmax, negS0, negP0 = catalog[name]
            if unit != unit0:
                return fail("%s: item %d unit %r != catalog %r" % (tag, k + 1, unit, unit0))
            if ns != negS0 or np_ != negP0:
                return fail("%s: item %d negative labels (%r, %r) != catalog (%r, %r)"
                            % (tag, k + 1, ns, np_, negS0, negP0))
            if not (mn <= d <= mx):
                return fail("%s: item %d price %d dec outside the catalog range [%d, %d]"
                            % (tag, k + 1, d, mn, mx))
            if abs(c) >= 2 and abs(c) > cmax:
                return fail("%s: item %d count %d above the catalog countMax %d"
                            % (tag, k + 1, c, cmax))
            frag = item_fragment(c, d, name, plural, unit, ns, np_)
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
    for ctx in CONTEXTS:
        if not any(q["ctx"] == ctx and q["pass_id"] == "1" for q in qs):
            return fail("no je question in context %r" % ctx)
        if not any(q["ctx"] == ctx and q["pass_id"] == "2" for q in qs):
            return fail("no named question in context %r" % ctx)
        if not any(q["ctx"] == ctx and any(c < 0 for c in q["cs"]) for q in qs):
            return fail("no negative (refund/coupon) term in context %r" % ctx)
    if not any(q["who"] == "Marc" for q in qs):
        return fail("no Marc question in the draw stream")
    if not any(q["who"] == "Lise" for q in qs):
        return fail("no Lise question in the draw stream")
    if not any(q["n"] == 2 for q in qs):
        return fail("no 2-item question in the draw stream")
    if not any(q["n"] == 3 for q in qs):
        return fail("no 3-item question in the draw stream")
    if not any(c < 0 for q in qs for c in q["cs"]):
        return fail("no negative term in the draw stream")
    if not any(c == 1 for q in qs for c in q["cs"]):
        return fail("no bare-price term in the draw stream")
    if not any(u == "le kilo" for q in qs for u in q["us"]):
        return fail("no kilo item in the draw stream")

    print("OK: %d questions checked (shape, catalog, arithmetic, id, prose, formulas)" % len(qs))
    print("VALIDE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
