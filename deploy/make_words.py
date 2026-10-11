"""Rebuilds portal/help/words.js - the word list behind the spelling hint:
construction and UAE terms first, then the 32,000 commonest English words.
Run: pip install wordfreq && python3 deploy/make_words.py"""
import os
from wordfreq import top_n_list

TRADE = """plastering plaster blockwork block blocks shuttering shutter rebar rebars formwork scaffolding scaffold screed grout grouting waterproofing gypsum
ceiling partition tiling tiles tile marble granite porcelain skirting cladding facade glazing aluminium aluminum joinery carpentry painting primer putty
emulsion enamel sealant silicone epoxy bitumen membrane insulation polystyrene rockwool ducting duct chiller fcu ahu cabling conduit trunking switchgear
db mdb smdb lv hv earthing lighting fixture fixtures luminaire sanitary sanitaryware plumbing drainage manhole sewer stormwater irrigation landscaping
hardscape softscape interlock kerb curbstone paver pavers asphalt backfilling backfill excavation compaction dewatering shoring piling pile piles footing
footings raft slab slabs column columns beam beams lintel parapet staircase handrail balustrade pergola gazebo villa villas plot plots site sites
cement sand aggregate gabbro concrete readymix steel mesh binding wire nails screws bolts anchors plywood timber hessian polythene
jcb bobcat excavator crane forklift pickup lorry trailer tanker generator compressor vibrator mixer grinder drill breaker welding welder
dewa noc mep boq lpo ipc rfi mir wir vo ncr itp hse ppe mos rams dm rta dda nakheel emaar sobha hartland meydan keturah ajman sharjah dubai abu dhabi
emirates mulkiya trakhees civil defence etisalat du ejari tasheel tadbeer amer mohre gdrfa wps gpssa iloe eid visa passport labour labours labourers
overtime ot petty cash reimbursement advance salary allowance gratuity accommodation transport fuel diesel petrol toll salik parking fine fines
invoice proforma retention handover snagging defects demarcation affection plan permit permits inspection approval approvals submittal submittals
mockup sample samples quotation quote supplier suppliers subcontractor subcontractors contractor consultant client foreman supervisor engineer
storekeeper chargehand helper mason carpenter electrician plumber painter tiler steelfixer welder driver operator surveyor estimator draftsman"""

words = [w for w in top_n_list("en", 45000) if w.isascii() and w.isalpha() and (len(w) > 1 or w in ("a", "i"))][:32000]
seen, out = set(), []
for w in TRADE.split() + words:
    w = w.lower()
    if w not in seen:
        seen.add(w); out.append(w)
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "portal", "help", "words.js")
with open(path, "w") as f:
    f.write("/* Words the spelling hint knows: construction and UAE terms first, then\n"
            "   common English by frequency. Written by deploy/make_words.py. */\n"
            f'window.SPELL_WORDS = "{" ".join(out)}";\n')
print(len(out), "words")
