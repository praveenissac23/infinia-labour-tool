"""A copy of the live purchasing records the 31 Oct 2026 data correction touches, read from the live database
(read-only, 31 Oct 2026) with their real ids, laid over a copy of the full test database - so the correction
script (deploy/fix_purchasing_2026_10_31.py) can be run, applied and applied again exactly as on the server.

    python3 tests/purchasing_fix_replica.py /path/to/copy.db      (the file is made a copy of /tmp/claude-0/full.db)

Only the purchasing side is replaced (suppliers, materials, LPOs, material requests, stock movements of these
materials); payroll and everything else in the copy is left as it is. Names longer than the live read showed are
cut where the read cut them - the matching does not depend on the end of a long name."""
import os, shutil, sqlite3, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SUPPLIERS = {8: "Dani Trading LLC", 10: "Najm Al Ofuq Scaffolding", 11: "Shafa Al Nahdah Ready Mixe Concrete", 13: "Avv General Trading LLC",
             16: "Absolute Royal Technologies", 25: "Aim Asia Building & Construction Material Trd LLC", 31: "Al Danube Building Materials",
             51: "Al Raha Intnational Building Materials Trading LLC", 68: "Bahmani Integrated Industries", 80: "Candela Lighting And Automation",
             90: "Cretepro Building Materials", 94: "Desarch Building Contracting L.l.c", 104: "Eon Print Solutions LLC",
             114: "Gemini Building Materials", 115: "Ghantoot Building Materials", 142: "Khuram Cheema Transport LLC", 181: "Rashidco Cement LLC",
             233: "Al Maharah Global Trading", 293: "Dynamic Point Steel Construction", 326: "Seomaa Building Materials", 359: "Al Amaar Block Manufacturing",
             360: "Srayedin Building Materials Trading (llc)", 362: "Glowcraft Contracting L.l.c", 367: "Casa Fiora FZE", 368: "Plant Care Landscape And Garden",
             369: "Unimix Block Industry", 370: "Ultra Power Generators (fze)", 371: "Electra Dubai LLC", 373: "Echo Organic Termite Pest Control LLC"}

# id, code, name, unit, type
ITEMS = """84|ITM81|3/4 Aggregate|pcs|consumable
326|ITM323|Polythene Sheet - 1000G (3.66 X 10 MTR)|roll|consumable
539|ITM536|Cement 50KG|pcs|consumable
555|ITM552|Road Base|pcs|consumable
583|ITM580|Black Sand|pcs|consumable
801|ITM798|Jotun External Primer 18 Lt Drum|drum|consumable
1832|ITM1829|Swivel Clamp|pcs|asset
1848|ITM1845|Universal Clamp|pcs|consumable
2307|ITM2304|Wood Auger Drill Bit - 25MM|pcs|asset
3010|ITM3007|Bracing Tube 4.0M|pcs|consumable
3026|ITM3023|Ledger 0.9M|pcs|asset
3027|ITM3024|Ledger 1.5M|pcs|asset
3028|ITM3025|Ledger 1.2M|pcs|asset
3034|ITM3031|Standard 1.00M|pcs|asset
3036|ITM3033|Standard 2.0M|pcs|asset
3038|ITM3035|Standard 3.0M|pcs|asset
3069|ITM3066|Aluminium Beam 2.5M|pcs|asset
3091|ITM3088|Adjustable U Head|pcs|asset
3175|ITM3172|Tube 4.0M|pcs|asset
3258|ITM3255|Warning Tape|roll|consumable
3364|ITM3361|Poly Propylene String Wound Filter Cartr|pcs|consumable
3369|ITM3366|Wire Nail 2.5 Inch|kg|consumable
3370|ITM3367|Rubber Hand Gloves|set|consumable
3371|ITM3368|Cotton Hand Gloves|set|consumable
3376|ITM3373|Wire Nail 4 Inch|kg|consumable
3381|ITM3378|Measuring Tape 5mtr|pcs|asset
3408|ITM3405|Concrete Nail 2.5 Inch|box|consumable
3413|ITM3410|Ledger 1.60M|pcs|asset
3414|ITM3411|Ledger 1.8 M|pcs|asset
3415|ITM3412|Ledger 2.0 M|pcs|asset
3416|ITM3413|Ledger 1.3 M|pcs|asset
3419|ITM3416|Adjustable Base Jack|pcs|asset
3428|ITM3422|Swivel Coupler|pcs|asset
3433|ITM3427|Trolley Wheel|pcs|asset
3449|ITM3443|Grade Slab BRC Mesh A 252 - 2.4*4.8|pcs|consumable
3469|ITM3463|Pump Charges 42mtr|M3|consumable
3507|ITM3501|Cantilever Frame 1.5M|pcs|asset
3514|ITM3508|KERAKOLE H40 Icon|BAG|consumable
3515|ITM3509|3/4 Aggregate 3m3|trip|consumable
3516|ITM3510|Black Sand 3M3|TRIP|consumable
3517|ITM3511|CEMENT CEMEX|BAGS|consumable
3518|ITM3512|CONCRETE C40/20 420KG OPC(34%OPC+66%GGBS|M3|consumable
3519|ITM3513|PUMP 42MTR|M3|consumable
3520|ITM3514|TEMPERATURE CONTROL 32*|M3|consumable
3521|ITM3515|CEMENT ULTRATECH|BAG|consumable
3522|ITM3516|Jotashield Eterna A Base 16.2L manual fo|DRUM|consumable
3523|ITM3517|Paint Roller 9" Texture|NOS|consumable
3524|ITM3518|Paint Roller 4" Texture|NOS|consumable
3525|ITM3519|Texo Compound 18L Jotun WHITE|DRUM|consumable
3526|ITM3520|REBAR 10MM JINDAL/QATAR|TON|consumable
3527|ITM3521|REBAR 16MM JINDAL/QATAR|TON|consumable
3528|ITM3522|REBAR 20MM JINDAL/QATAR|TON|consumable
3529|ITM3523|TRANSPORTATION|TRIP|consumable
3536|ITM3530|Grade Slab BRC Mesh A 252 - 2.4x4.8x8MM|pcs|consumable
3537|ITM3531|Concrete Nail 2.5 Inch (7KGX2CRTN)|crtn|consumable
3538|ITM3532|Garbage bag 95cmx125cm|bndl|consumable
3539|ITM3533|Cargo Lashing Belt 2"x10mtr|pcs|asset
3540|ITM3534|Polythene Sheet - 1000G (3.66 X 10 MTR)|roll|consumable
3541|ITM3535|Outdoor Fiberglass Lounge Chair Waterpro|pcs|consumable
3543|ITM3537|Outdoor Fiberglass Lounge Chair Waterproof|pcs|consumable
3544|ITM3538|Gloves Latex green grip|PAIR|consumable
3545|ITM3539|Warning Tape RED & WHITE|roll|consumable
3546|ITM3540|Dotted Hand Gloves dzn|DZN|consumable
3559|ITM3553|CONCRETE C40/20 400KG(64%OPC+36%GGBS) SU|M3|consumable
3561|ITM3555|CONCRETE C45/20 420KG(64%OPC+36%GGBS) SU|M3|consumable
3599|ITM3593|GYPSUM BOARD RG 12.5MMX1200X2400 KNAUF|NOS|consumable
3600|ITM3594|MAIN CHANNEL 38X12X0.5X3000 KNAUF|NOS|consumable
3601|ITM3595|FURRING CHANNEL 35X22X68X0.5X3000 KNAUF|NOS|consumable
3602|ITM3596|WALL ANGLE 25X25X0.5X3000MM KNAUF|NOS|consumable
3603|ITM3597|GI HANGING WIRE 4KG|ROLL|consumable
3604|ITM3598|GI WIRE CLIPS|NOS|consumable
3605|ITM3599|CEILINIG WEDGE ANCHOR 6X40 KNAUF|PKT|consumable
3606|ITM3600|DRYWALL SCREW TN3.5X25MM KNAUF|PKT|consumable
3607|ITM3601|WAFER HEAD SCREW LM3.5X11MM KNAUF|PKT|consumable
3608|ITM3602|JOINT TAPE 50MM KNAUF|ROLL|consumable
3609|ITM3603|KNAUF JOINT COMPOUND 28KG|DRUM|consumable
3610|ITM3604|GI CORNER BEED PERF|NOS|consumable
3611|ITM3605|NATIONAL SYNTHETIC ENAMEL 890 1LTR|LTR|consumable
3612|ITM3606|NATIONAL SYNTHETIC ENAMEL 440 18LTR|DRUM|consumable
3613|ITM3607|NATIONAL LAQUER THINNER 4LTR|GALLON|consumable
3615|ITM3609|CONCRETE C45/20 420KG(34%OPC+66%GGBS) SU|M3|consumable
3616|ITM3610|Green Net 4X200MTR|m|asset
3617|ITM3611|Spigot Pin|pcs|asset
3618|ITM3612|Spigot Pin Nut/Bolt|pcs|asset
3619|ITM3613|Jotun Internal Primer 18 Lt Drum|drum|consumable
3620|ITM3614|National External Texture Stucco 18ltr|drum|consumable
3621|ITM3615|Texture Roller 9|pcs|asset
3622|ITM3616|Texture Roller 4|pcs|asset
3623|ITM3617|White Epoxy Paint 18LTR|drum|consumable
3624|ITM3618|Concrete Nail 1 Inch|box|consumable
3626|ITM3620|Advertising Flag Only – Double-sided printing|NOS|consumable
3629|ITM3623|Wire Nail 2.5 Inch 14kg/cartn|carton|consumable
3631|ITM3625|Green Net 4X40MTR|ROLL|consumable
3632|ITM3626|Wood Auger Drill Bit - 25MMX600MM|pcs|consumable
3633|ITM3627|TRAANSPORTATION|NOS|consumable
3634|ITM3628|JOTUN ACRYLIC EMULSION PRIMER 18LTR|drum|consumable
3635|ITM3629|JOTUN PVA PRIMER 18LT|drum|consumable
3636|ITM3630|Aluminium Beam 3.0M|pcs|asset
3637|ITM3631|Aluminium Beam 3.5M|pcs|asset
3638|ITM3632|Aluminium Beam 4.0M|pcs|asset
3639|ITM3633|Aluminium Beam 4.5M|pcs|asset
3640|ITM3634|Aluminium Beam 1.5M|pcs|asset
3641|ITM3635|Aluminium Beam 2.0M|pcs|asset
3642|ITM3636|Jotun Hardtop xp white A+B 18ltr|drum|consumable
3643|ITM3637|Aluminium Beam 2.5M|pcs|asset
3644|ITM3638|GI Perimeter Angle 3 Mtr|pcs|consumable
3646|ITM3640|Drip Tray for 30 KVA|NOS|consumable
3647|ITM3641|Supply of Diesel Engine Generator Sound Proof 30 KVA|NOS|consumable
3648|ITM3642|CONCRETE C40/20 400KG(34%OPC+66%GGBS)SUP|M3|consumable
3649|ITM3643|Cement 50KG ULTRATECH|pcs|consumable
3650|ITM3644|GI CHANNEL 3MTR KNAUF|NOS|consumable
3651|ITM3645|GI FURRING CHANNEL|NOS|consumable
3652|ITM3646|GI HANGING WIRE ROLL KNAUF|ROLL|consumable
3653|ITM3647|GI CONNECTION CLIP KNAUF|NOS|consumable
3654|ITM3648|CEILING WEDGE ANCHOR 6x40mm KNAUF 200PCS|PKT|consumable
3655|ITM3649|Drywall screw KNAUF T3.5x25mm|PKT|consumable
3656|ITM3650|Hammer fixing screw KNAUF 6x40mm|PKT|consumable
3657|ITM3651|CONCRETE C45/20 420KG(34%OPC+66%GGBS) SU|m3|consumable
3658|ITM3652|Standard 3.0m|nos|consumable
3659|ITM3653|Standard 2.0m|nos|consumable
3660|ITM3654|Standard 1.8m|nos|consumable
3661|ITM3655|Standard 1.3m|nos|consumable
3662|ITM3656|Ledger 1.8m|nos|consumable
3663|ITM3657|Ledger 1.6m|nos|consumable
3664|ITM3658|Ledger 1.3m|nos|consumable
3665|ITM3659|Ledger 1.0m|nos|consumable
3666|ITM3660|Ledger 0.6m|nos|consumable
3667|ITM3661|Adjustable Base/base jack|nos|consumable
3668|ITM3662|Adjustable "U" Head|nos|consumable
3669|ITM3663|M.D Props 3.20 to 5.0m|nos|consumable
3670|ITM3664|Spigot / Nut & Bolt|nos|consumable
3671|ITM3665|Swivel Coupler- Forged|nos|consumable
3672|ITM3666|ALUMINIUM BEAM 1.0m|nos|consumable
3673|ITM3667|GTI Automatic Shadow Trim 15x18x3000mm P|NOS|consumable
3674|ITM3668|Rental Prop 4.0M|pcs|asset
3675|ITM3669|Rental Aluminium Beam 4.5M|pcs|asset
3676|ITM3670|Rental Aluminium Beam 3.0M|pcs|asset
3677|ITM3671|Rental Aluminium Beam 2.5M|pcs|asset
3678|ITM3672|Standard 1.5m|nos|consumable
3679|ITM3673|M.D Props 3.20 to 6.0m|nos|consumable
3680|ITM3674|Aggregate 20MM|m3|consumable
3681|ITM3675|Solid Block 8 Inch|pcs|consumable
3682|ITM3676|Hollow Block 4 Inch|pcs|consumable
3683|ITM3677|Rental Standard 2.8M|pcs|asset
3684|ITM3678|Rental ADJ Base Jack|pcs|asset
3685|ITM3679|Rental Aluminium Beam 4.0M|pcs|asset
3686|ITM3680|Rental Aluminium Beam 3.5m|pcs|asset
3687|ITM3681|Rental Aluminium Beam 2.0M|pcs|asset
3688|ITM3682|Rental Aluminium Beam 1.5M|pcs|asset
3689|ITM3683|Rental Aluminium Beam 1.0M|pcs|asset
3690|ITM3684|Rental Tie Rode Set 1.5M|pcs|asset
3691|ITM3685|Rental Tie Rode Set 1.0M|pcs|asset
3692|ITM3686|Rental Standard 3.0M|pcs|asset
3693|ITM3687|Rental Ledger 1.8M|pcs|asset
3694|ITM3688|Rental Ledger 1.6M|pcs|asset
3695|ITM3689|Rental Ledger 1.3M|pcs|asset
3696|ITM3690|Rental Ledger 1.0M|pcs|asset
3697|ITM3691|Rental Ledger 0.9M|pcs|asset
3698|ITM3692|Rental Ledger 0.6M|pcs|asset
3699|ITM3693|Rental U-Head Jack|pcs|asset
3700|ITM3694|Rental Swivel Clamp|pcs|asset
3701|ITM3695|Rental Tube 2.5M|pcs|asset
3702|ITM3696|Rental Standard 2.5M|pcs|asset
3703|ITM3697|Rental Standard 2.3M|pcs|asset
3704|ITM3698|Rental Standard 2.0M|pcs|asset
3705|ITM3699|Rental Ledger 1.2M|pcs|asset
3706|ITM3700|Rental Tube 4.0M|pcs|asset
3707|ITM3701|Rental Tube 3.0M|pcs|asset
3708|ITM3702|Cement 50KG cemex|pcs|consumable
3709|ITM3703|PVC UV Laminated Vinyl Sticker Supply and Installation|sqm|consumable
3710|ITM3704|Rental Prop 5.0M|pcs|asset
3711|ITM3705|Rental Cantilever Frame 1.5M|pcs|asset
3712|ITM3706|Rental Spigot Pin|pcs|asset
3713|ITM3707|Rental Spigot Pin Nut/Bolt|pcs|asset
3714|ITM3708|Rental Tube 1.5M|pcs|asset
3715|ITM3709|Rental Standard 1.5M|pcs|asset
3718|ITM3712|Supply of PVC vinyl sticker with matt lamination|sqm|consumable
3719|ITM3713|Dali Driver 24V 80W|pcs|consumable
3720|ITM3714|Rental Standard 1.3M|pcs|asset
3721|ITM3715|False Ceiling Main Channel|pcs|consumable
3722|ITM3716|Knauf False Ceiling Main Channel 0.5mm X 3MTR|pcs|consumable
3723|ITM3717|Rental Prop 6.0M|pcs|asset
3724|ITM3718|Hollow Block 10CM|pcs|consumable
3725|ITM3719|Hollow Block 25CM|pcs|consumable
3726|ITM3720|Legrand Mallia Senses 13A Switched Socket|nos|consumable
3727|ITM3721|Concrete Drymix C20/20|M3|consumable
3728|ITM3722|Supply and installation of a steel structure|ls|consumable
3731|ITM3725|Starter Motor|pcs|consumable
3732|ITM3726|Service Charges|no|consumable
3733|ITM3727|Rental Standard 1.0M|pcs|asset
3734|ITM3728|Insulation Block 25CM|pcs|consumable
3735|ITM3729|Hollow Block 20CM|pcs|consumable
3741|ITM3735|Plastic Broom|pcs|consumable
3742|ITM3736|Thermal Block 25CM|NOS|consumable
3743|ITM3737|Welding Machine|pcs|asset
3744|ITM3738|White Silicon Sealant|pcs|consumable
3746|ITM3740|ASSEMBLED DESKTOP SYSTEM|pcs|consumable
3749|ITM3743|Rental Standard 1.8M|pcs|consumable
3780|ITM3774|Workers Uniform (Workland)|pcs|consumable
3781|ITM3775|Road Base 3M3|trips|consumable
3783|ITM3777|DELL TOWER QCT1250 CORE I7 DESKTOP|pcs|consumable
3784|ITM3778|PHILIPS 27" LED (Black)|pcs|consumable
3791|ITM3785|Rental Tube 6.0M|pcs|consumable
3792|ITM3786|Anti - Termite Treatmemt For Swimming Pool|ls|consumable
3794|ITM3788|White Silicon Sealant 240ML/PCS-24PCS/CTN|ctn|consumable
3795|ITM3789|Measuring Tape 5.5 MTR X 25MM Raha Plus|nos|consumable"""
PLANT_ITEMS = list(range(3565, 3599))

# id, po_no, ref, date, supplier, request_id, location, status, request_line_ids, combined, discount, cancelled_at
ORDERS = """34|20260114|IC/LPO/20260114|2026-10-01|90|0|911|issued||0|0
35|20260115|IC/LPO/20260115|2026-10-01|90|0|910|issued||0|0
36|20260116|IC/LPO/20260116|2026-10-02|360|0|908|issued||0|0
37|20260117|IC/LPO/20260117|2026-10-02|360|0|914|issued||0|0
38|20260118|IC/LPO/20260118|2026-10-02|11|0|913|issued||0|0
39|20260119|IC/LPO/20260119|2026-10-05|181|0|914|issued||0|0
40|20260120|IC/LPO/20260120|2026-10-05|31|0|912|issued||0|0
41|20260121|IC/LPO/20260121|2026-10-05|8|0|910|issued||0|0
42|20260122|IC/LPO/20260122|2026-10-05|115|0|919|issued||0|0
43|20260123|IC/LPO/20260123|2026-10-05|115|103|913|issued||0|0
44|20260124|IC/LPO/20260124|2026-10-08|326|0|900|issued||0|0
47|20260127|IC/LPO/20260127|2026-10-10|367|0|905|issued||0|0.01
48|20260128|IC/LPO/20260128|2026-10-12|326|0|900|issued||0|0
49|20260129|IC/LPO/20260129|2026-10-14|11|110|912|issued||0|0
50|20260130|IC/LPO/20260130|2026-10-14|11|111|913|issued||0|0
51|20260131|IC/LPO/20260131|2026-10-16|368|0|906|issued||0|7.58
52|20260132|IC/LPO/20260132|2026-10-16|114|0|909|issued||0|0
53|20260133|IC/LPO/20260133|2026-10-16|114|0|900|issued||0|0
54|20260134|IC/LPO/20260134|2026-10-16|11|112|919|issued||0|0
55|20260135|IC/LPO/20260135|2026-10-17|115|113|919|issued||0|0
56|20260136|IC/LPO/20260136|2026-10-20|104|0|900|issued||0|0
57|20260137|IC/LPO/20260137|2026-10-20|13|0|910,909|issued||0|0
58|20260138|IC/LPO/20260138|2026-10-20|114|0|909|issued||0|0
59|20260139|IC/LPO/20260139|2026-10-21|370|0|926|issued||0|4.12
60|20260140|IC/LPO/20260140|2026-10-21|360|121|914|issued||0|0
61|20260141|IC/LPO/20260141|2026-10-21|360|122|912|issued||0|0
62|20260142|IC/LPO/20260142|2026-10-21|360|123|915|issued||0|0
63|20260143|IC/LPO/20260143|2026-10-21|360|124|914|issued||0|0
64|20260144|IC/LPO/20260144|2026-10-21|11|125|912|issued||0|0
65|20260145|IC/LPO/20260145|2026-10-21|31|0|914,909|issued||0|0
66|20260146|IC/LPO/20260146|2026-10-22|114|0|909|issued||0|0
67|20260147|IC/LPO/20260147|2026-10-22|11|126|919|issued||0|0
68|20260148|IC/LPO/20260148|2026-10-23|94|127|919|issued||0|47.62
69|20260149|IC/LPO/20260149|2026-10-23|114|0|909|issued||0|0
70|20260150|IC/LPO/20260150R1|2026-10-24|94|128|913|issued||0|45
71|20260151|IC/LPO/20260151|2026-10-24|181|0|102|cancelled||0|0
72|20260152|IC/LPO/20260152|2026-10-24|362|0|920|issued||0|0
73|20260153|IC/LPO/20260153|2026-10-26|360|0|102|cancelled|,275,276,|0|0
74|20260154|IC/LPO/20260154|2026-10-26|362|0|Store|issued||0|0
75|20260155|IC/LPO/20260155|2026-10-26|80|0|906|issued||0|0
76|20260156|IC/LPO/20260156|2026-10-26|114|0|909|issued||0|0
77|20260157|IC/LPO/20260157|2026-10-26|233|0|906|issued||0|0
78|20260158|IC/LPO/20260158|2026-10-27|11|0|102|issued||0|0
79|20260159|IC/LPO/20260159|2026-10-27|293|0|909|issued||0|0
80|20260160|IC/LPO/20260160|2026-10-27|68|0|Store|issued||0|0
81|20260161|IC/LPO/20260161|2026-10-28|371|135|906|issued||0|0
82|20260162|IC/LPO/20260162|2026-10-28|369|0|914|issued||0|0
83|20260163|IC/LPO/20260163|2026-10-28|369|0|915|issued||0|0
84|20260164|IC/LPO/20260164|2026-10-28|359|136|915|issued||0|0
85|20260165|IC/LPO/20260165|2026-10-28|16|0|Office|issued||0|0
86|20260166|IC/LPO/20260166|2026-10-29|25|0|910|issued|,291,288,287,293,|1|0
87|20260167|IC/LPO/20260167|2026-10-30|360|0|914|issued|,294,|0|0
88|20260168|IC/LPO/20260168|2026-10-30|16|0|Office|issued||0|0
89|20260169|IC/LPO/20260169|2026-10-30|373|0|102|issued||0|0
90|20260170|IC/LPO/20260170|2026-10-30|94|0|926|issued|,308,309,310,312,313,314,|0|55
91|20260171|IC/LPO/20260171|2026-10-31|51|0|Store|issued|,303,304,305,|0|0"""

# order, line id, item, description, qty, unit, rate, cost_to
LINES = """34|171|3514|KERAKOLE H40 Icon|8|BAG|41.4|
35|172|3514|KERAKOLE H40 Icon|15|BAG|41.4|
36|173|3515|3/4 Aggregate 3m3|1|trip|360|
37|174|3516|Black Sand 3M3|1|TRIP|300|
38|666|3518|CONCRETE C40/20 420KG OPC(34%OPC+66%GGBS|116|M3|353|
38|667|3519|PUMP 42MTR|116|M3|15|
38|668|3520|TEMPERATURE CONTROL 32*|116|M3|12|
39|209|3517|CEMENT CEMEX|100|BAGS|16|
40|191|3521|CEMENT ULTRATECH|100|BAG|16|
41|192|3522|Jotashield Eterna A Base 16.2L manual fo|3|DRUM|450|
41|193|3523|Paint Roller 9" Texture|5|NOS|13|
41|194|3524|Paint Roller 4" Texture|5|NOS|7|
41|195|3525|Texo Compound 18L Jotun WHITE|2|DRUM|108|
42|205|3526|REBAR 10MM JINDAL/QATAR|2|TON|2880|
42|206|3527|REBAR 16MM JINDAL/QATAR|2.5|TON|2880|
42|207|3528|REBAR 20MM JINDAL/QATAR|3.03|TON|2880|
42|208|3529|TRANSPORTATION|1|TRIP|700|
43|204|3527|REBAR 16MM JINDAL/QATAR|2.88|TON|2880|
44|217|3536|Grade Slab BRC Mesh A 252 - 2.4x4.8x8MM|30|pcs|144|
44|218|3540|Polythene Sheet - 1000G (3.66 X 10 MTR)|20|roll|19|
44|219|3537|Concrete Nail 2.5 Inch (7KGX2CRTN)|2|crtn|85|
44|220|3540|Polythene Sheet - 1000G (3.66 X 10 MTR)|30|roll|19|
44|221|3433|Trolley Wheel|10|pcs|35|
44|222|3538|Garbage bag 95cmx125cm|2|bndl|95|
44|223|3539|Cargo lashing belt 2"x10mtr|3|nos|19|
47|228|3543|Outdoor Fiberglass Lounge Chair Waterproof|2|pcs|1762|
48|235|3544|Gloves Latex green grip|108|PAIR|2.5|
48|236|3545|Warning Tape RED & WHITE|20|roll|6|
48|237|3546|Dotted Hand Gloves dzn|9|DZN|13|
49|669|3561|CONCRETE C45/20 420KG(64%OPC+36%GGBS) SU|103|M3|353|
49|670|3519|PUMP 42MTR|103|M3|15|
49|671|3520|TEMPERATURE CONTROL 32*|103|M3|12|
50|672|3559|CONCRETE C40/20 400KG(64%OPC+36%GGBS) SU|34|M3|353|
50|673|3519|PUMP 42MTR|1|NOS|600|
50|674|3520|TEMPERATURE CONTROL 32*|34|M3|12|
52|326|3599|GYPSUM BOARD RG 12.5MMX1200X2400 KNAUF|10|NOS|23|
52|327|3600|MAIN CHANNEL 38X12X0.5X3000 KNAUF|10|NOS|7.1|
52|328|3601|FURRING CHANNEL 35X22X68X0.5X3000 KNAUF|22|NOS|12.4|
52|329|3602|WALL ANGLE 25X25X0.5X3000MM KNAUF|10|NOS|5.75|
52|330|3603|GI HANGING WIRE 4KG|1|ROLL|35|
52|331|3604|GI WIRE CLIPS|75|NOS|0.35|
52|332|3605|CEILINIG WEDGE ANCHOR 6X40 KNAUF|1|PKT|105.1|
52|333|3606|DRYWALL SCREW TN3.5X25MM KNAUF|1|PKT|24|
52|334|3607|WAFER HEAD SCREW LM3.5X11MM KNAUF|1|PKT|35.5|
52|335|3608|JOINT TAPE 50MM KNAUF|1|ROLL|13|
52|336|3609|KNAUF JOINT COMPOUND 28KG|1|DRUM|51|
52|337|3610|GI CORNER BEED PERF|8|NOS|6.5|
52|338|3611|NATIONAL SYNTHETIC ENAMEL 890 1LTR|2|LTR|22|
53|339|3612|NATIONAL SYNTHETIC ENAMEL 440 18LTR|1|DRUM|230|
53|340|3613|NATIONAL LAQUER THINNER 4LTR|1|GALLON|46|
54|384|3615|CONCRETE C45/20 420KG(34%OPC+66%GGBS) SU|25|M3|353|
54|385|3469|Pump Charges 42mtr|1|NOS|600|
55|386|3528|REBAR 20MM JINDAL/QATAR|0.3|TON|2870|
56|390|3626|Advertising Flag Only – Double-sided printing|4|NOS|240|
57|457|3376|Wire Nail 4 Inch|2|crtn|72|
57|458|3629|Wire Nail 2.5 Inch 14kg/cartn|2|carton|72|
57|459|3624|Concrete Nail 1 Inch|1|carton|185|
57|460|3631|Green Net 4X40MTR|5|ROLL|185|
57|461|3632|Wood Auger Drill Bit - 25MMX600MM|5|pcs|55|
57|462|3620|National External Texture Stucco 18ltr|8|drum|136|
57|463|3633|TRAANSPORTATION|1|NOS|80|
58|437|3634|JOTUN ACRYLIC EMULSION PRIMER 18LTR|4|drum|120|
58|438|3621|Texture Roller 9|5|pcs|12|
58|439|3622|Texture Roller 4|6|pcs|8|
58|440|3635|JOTUN PVA PRIMER 18LT|4|drum|74|
58|441|3642|Jotun Hardtop xp white A+B 18ltr|1|drum|830|
59|421|3647|Supply of Diesel Engine Generator Sound Proof 30 KVA|1|NOS|32176|
59|422|3646|Drip Tray for 30 KVA|1|NOS|1200|
60|423|583|BLACK SAND|5|TRIP|300|
61|425|583|BLACK SAND|1|TRIP|300|
62|426|583|BLACK SAND|1|TRIP|300|
63|427|84|3/4 Aggregate|1|TRIP|360|
64|430|3648|CONCRETE C40/20 400KG(34%OPC+66%GGBS)SUP|11|M3|348|
64|431|3519|PUMP 42MTR|1|NOS|600|
65|443|3649|Cement 50KG ULTRATECH|100|pcs|16|
66|445|3644|GI Perimeter Angle 3 Mtr|35|pcs|5.75|
66|446|3599|GYPSUM BOARD RG 12.5MMX1200X2400 KNAUF|35|NOS|23|
66|447|3650|GI CHANNEL 3MTR KNAUF|34|NOS|7.1|
66|448|3651|GI FURRING CHANNEL|73|NOS|12.4|
66|449|3652|GI HANGING WIRE ROLL   KNAUF|3|ROLL|35|
66|450|3653|GI CONNECTION CLIP KNAUF|250|NOS|0.4|
66|451|3654|CEILING WEDGE ANCHOR 6x40mm KNAUF 200PCS|1|PKT|105.1|
66|452|3655|Drywall screw KNAUF T3.5x25mm|1|PKT|24|
66|453|3656|Hammer fixing screw KNAUF 6x40mm|1|PKT|30|
66|454|3608|JOINT TAPE 50MM KNAUF|2|ROLL|13|
67|455|3657|CONCRETE C45/20 420KG(34%OPC+66%GGBS) SU|21|m3|353|
67|456|3519|PUMP 42MTR|1|nos|600|
68|464|3658|Standard 3.0m|23|nos|0.9|
68|465|3659|Standard 2.0m|231|nos|0.7|
68|466|3660|Standard 1.8m|38|nos|0.63|
68|467|3661|Standard 1.3m|196|nos|0.55|
68|468|3662|Ledger 1.8m|430|nos|0.44|
68|469|3663|Ledger 1.6m|60|nos|0.4|
68|470|3664|Ledger 1.3m|625|nos|0.36|
68|471|3028|Ledger 1.2m|85|nos|0.35|
68|472|3665|Ledger 1.0m|225|nos|0.3|
68|473|3026|Ledger 0.9m|80|nos|0.28|
68|474|3666|Ledger 0.6m|120|nos|0.24|
68|475|3667|Adjustable Base/base jack|255|nos|0.45|
68|476|3668|Adjustable "U" Head|315|nos|0.5|
68|477|3507|Cantilever Frame 1.5m|65|nos|1.25|
68|478|3669|M.D Props 3.20 to 5.0m|125|nos|2.5|
68|479|3670|Spigot / Nut & Bolt|235|nos|0.3|
68|480|3671|Swivel Coupler- Forged|340|nos|0.22|
68|481|3010|Bracing Tube 4.0m|170|nos|0.8|
68|482|3672|ALUMINIUM BEAM 1.0m|25|nos|1.5|
68|483|3640|ALUMINIUM BEAM 1.5m|30|nos|2.25|
68|484|3641|ALUMINIUM BEAM 2.0m|35|nos|3|
68|485|3643|Aluminium Beam 2.5m|70|nos|3.75|
68|486|3636|Aluminium Beam 3.0m|30|nos|4.5|
68|487|3637|Aluminium Beam 3.5m|145|nos|5.25|
68|488|3638|Aluminium Beam 4.0m|60|nos|6|
68|489|3639|Aluminium Beam 4.5m|80|nos|6.75|
69|490|3673|GTI Automatic Shadow Trim 15x18x3000mm P|35|NOS|11.5|
70|545|3659|Standard 2.0m|50|nos|0.7|
70|546|3678|Standard 1.5m|23|nos|0.58|
70|547|3661|Standard 1.3m|24|nos|0.55|
70|548|3662|Ledger 1.8m|200|nos|0.44|
70|549|3663|Ledger 1.6m|200|nos|0.4|
70|550|3665|Ledger 1.0m|85|nos|0.3|
70|551|3026|Ledger 0.9m|70|nos|0.28|
70|552|3666|Ledger 0.6m|40|nos|0.24|
70|553|3667|Adjustable Base/base jack|20|nos|0.45|
70|554|3668|Adjustable "U" Head|50|nos|0.5|
70|555|3507|Cantilever Frame 1.5m|40|nos|1.25|
70|556|3669|M.D Props 3.20 to 5.0m|100|nos|2.5|
70|557|3679|M.D Props 3.20 to 6.0m|5|nos|2.75|
70|558|3010|Bracing Tube 4.0m|125|nos|0.8|
70|559|3639|Aluminium Beam 4.5m|25|nos|6.75|
70|560|3643|Aluminium Beam 2.5m|70|nos|3.75|
70|561|3637|Aluminium Beam 3.5m|40|nos|5.25|
70|562|3034|Standard 1.00M|170|nos|0.45|
71|525|3708|Cement 50KG cemex|100|pcs|16|
72|528|3709|PVC UV Laminated Vinyl Sticker Supply and Installation|9.5|sqm|80|
73|529|3516|Black Sand 3M3|3|trips|300|
73|530|3515|3/4 Aggregate 3m3|3|trips|360|
74|566|3718|Supply of PVC vinyl sticker with matt lamination|12|sqm|60|
75|544|3719|Dali Driver 24V 80W|15|pcs|148|
76|565|3722|Knauf False Ceiling Main Channel 0.5mm X 3MTR|100|pcs|7.1|
77|571|3726|Legrand Mallia Senses 13A Switched Socket|20|nos|40|
78|582|3727|Concrete Drymix C20/20|10|M3|325|
79|617|3728|Supply and installation of a steel structure|1|ls|40000|
80|585|3731|Starter Motor|1|pcs|1388.5|
80|586|3732|Service Charges|1|no|300|
81|587|3726|Legrand Mallia Senses 13A Switched Socket|20|nos|30.48|
82|663|3725|Hollow Block 25CM|860|pcs|5.8|
82|664|3724|Hollow Block 10CM|534|pcs|4.4|
83|660|3735|Hollow Block 20CM|1700|pcs|4.8|
83|661|3725|Hollow Block 25CM|1600|pcs|5.8|
83|662|3724|Hollow Block 10CM|1700|pcs|4.4|
84|603|3742|Thermal Block 25CM|1700|NOS|8.9|
85|615|3746|ASSEMBLED DESKTOP SYSTEM|1|pcs|15200|
86|633|3743|Welding Machine|1|pcs|1317.9|STORE
86|634|3744|White Silicon Sealant|8|pcs|10|910
86|635|3741|Plastic Broom|20|pcs|4.7|STORE
86|636|3369|Wire Nail 2.5 Inch|45|kg|4.8|913
86|637|3780|Workers Uniform (Workland)|28|pcs|22|Office
87|638|3781|Road Base 3M3|2|trips|300|
88|641|3783|DELL TOWER QCT1250 CORE I7 DESKTOP|1|pcs|3750|
88|642|3784|PHILIPS 27" LED (Black)|2|pcs|390|
89|665|3792|Anti - Termite Treatmemt For Swimming Pool|1|ls|270|
90|678|3702|Rental Standard 2.5M|150|pcs|0.81|
90|679|3704|Rental Standard 2.0M|30|pcs|0.7|
90|680|3733|Rental Standard 1.0M|10|pcs|0.45|
90|681|3695|Rental Ledger 1.3M|100|pcs|0.36|
90|682|3791|Rental Tube 6.0M|10|pcs|1.2|
90|683|3688|Rental Aluminium Beam 1.5M|20|pcs|2.25|
90|684|3686|Rental Aluminium Beam 3.5m|15|pcs|5.25|
91|675|3794|White Silicon Sealant 240ML/PCS-24PCS/CTN|1|ctn|135|
91|676|3364|Poly Propylene String Wound Filter Cartridge|15|pcs|4|
91|677|3795|Measuring Tape 5.5 MTR X 25MM Raha Plus|5|nos|6|"""
PLANT_LINES = [(341 + k, 3565 + min(k, 33), 1) for k in range(35)]     # the 35 plant lines of 20260131 (906)

# id, ref, site, status, lpo_id, requested_on, notes
REQUESTS = """94|MR-0004|STORE|delivered|0|2026-09-28|Stock for the store, ordered on IC/LPO/20260109
96|MR-0005|915|delivered|0|2026-10-01|
97|MR-0006||delivered|0|2026-10-01|
98|MR-0007||delivered|0|2026-10-03|
103|MR-0012|STORE|delivered|0|2026-10-05|Stock for the store, ordered on IC/LPO/20260123
104|MR-0013||delivered|0|2026-10-06|
105|MR-0014||delivered|0|2026-10-09|
107|MR-0016|906|delivered|0|2026-10-09|
109|MR-0018||delivered|0|2026-10-13|
110|MR-0019|STORE|delivered|49|2026-10-14|Stock for the store, ordered on IC/LPO/20260129
111|MR-0020|STORE|delivered|50|2026-10-14|Stock for the store, ordered on IC/LPO/20260130
112|MR-0021|STORE|delivered|0|2026-10-16|Stock for the store, ordered on IC/LPO/20260134
113|MR-0022|STORE|delivered|0|2026-10-17|Stock for the store, ordered on IC/LPO/20260135
114|MR-0023||delivered|0|2026-10-17|
115|MR-0024|909|delivered|0|2026-10-19|
116|MR-0025|910|delivered|0|2026-10-20|
117|MR-0026||delivered|0|2026-10-20|
118|MR-0027|914|delivered|0|2026-10-21|
119|MR-0028|909|delivered|0|2026-10-21|
120|MR-0029|909|delivered|0|2026-10-21|
121|MR-0030|STORE|delivered|0|2026-10-21|Stock for the store, ordered on IC/LPO/20260140
122|MR-0031|STORE|delivered|0|2026-10-21|Stock for the store, ordered on IC/LPO/20260141
123|MR-0032|STORE|delivered|0|2026-10-21|Stock for the store, ordered on IC/LPO/20260142
124|MR-0033|STORE|delivered|0|2026-10-21|Stock for the store, ordered on IC/LPO/20260143
125|MR-0034|STORE|delivered|0|2026-10-21|Stock for the store, ordered on IC/LPO/20260144
126|MR-0035|STORE|delivered|0|2026-10-22|Stock for the store, ordered on IC/LPO/20260147
127|MR-0036|STORE|partial|0|2026-10-23|Stock for the store, ordered on IC/LPO/20260148
128|MR-0037|STORE|partial|0|2026-10-24|Stock for the store, ordered on IC/LPO/20260150
129|MR-0038|102|ordered|0|2026-10-24|
130|MR-0039|909|delivered|0|2026-10-26|
131|MR-0040|914|partial|0|2026-10-26|
132|MR-0041|915|ordered|0|2026-10-27|
133|MR-0042||delivered|0|2026-10-28|
134|MR-0043||delivered|0|2026-10-28|
135|MR-0044|STORE|delivered|0|2026-10-28|Stock for the store, ordered on IC/LPO/20260161
136|MR-0045|STORE|ordered|0|2026-10-28|Stock for the store, ordered on IC/LPO/20260164
137|MR-0046||delivered|0|2026-10-28|
139|MR-0048|910|delivered|0|2026-10-28|
140|MR-0049|914|partial|0|2026-10-30|
141|MR-0050|914|ordered|87|2026-10-30|Ordered direct on IC/LPO/20260167
142|MR-0051|Office|ordered|88|2026-10-30|Ordered direct on IC/LPO/20260168
144|MR-0053|Store|delivered|0|2026-10-30|
146|MR-0055|926|ordered|0|2026-10-30|
147|MR-0056|102|ordered|89|2026-10-30|Ordered direct on IC/LPO/20260169
148|MR-0057|913|ordered|38|2026-10-02|Ordered direct on IC/LPO/20260118
149|MR-0058|912|ordered|49|2026-10-14|Ordered direct on IC/LPO/20260129
150|MR-0059|913|ordered|50|2026-10-14|Ordered direct on IC/LPO/20260130
151|MR-0060|STORE|delivered|91|2026-10-31|Stock for the store, ordered on IC/LPO/20260171
153|MR-0062|926|ordered|90|2026-10-30|Ordered direct on IC/LPO/20260170"""

# request, line id, item, qty requested, qty received, unit, status, supplier
REQ_LINES = """94|206|1848|46|46|NOS|approved|10
96|208|3449|30|30|pcs|approved|326
97|209|326|20|20|roll|approved|326
98|210|326|30|30|roll|approved|326
98|211|3408|15|15|box|approved|326
103|216|3527|2.88|2.88|TON|approved|115
104|217|3433|10|10|pcs|approved|326
105|218|3370|1|1|set|approved|326
105|219|3371|1|1|set|approved|326
105|220|3258|20|20|roll|approved|326
107|222|3541|2|2|pcs|approved|367
109|225|3376|30|30|kg|approved|13
110|226|3519|100|100|M3|approved|11
110|227|3520|100|100|M3|approved|11
111|228|3519|1|1|NOS|approved|11
111|229|3520|35|35|M3|approved|11
112|230|3469|1|1|NOS|approved|11
112|231|3520|25|25|M3|approved|11
113|232|3528|0.3|0.3|TON|approved|115
114|233|3616|200|200|m|approved|13
114|234|2307|5|5|pcs|approved|13
115|235|3619|4|4|drum|approved|114
115|236|801|4|4|drum|approved|114
115|237|3620|8|8|drum|approved|13
115|238|3621|5|5|pcs|approved|114
115|239|3622|6|6|pcs|approved|114
116|240|3623|1|1|drum|approved|13
117|241|3624|1|1|box|approved|13
117|242|3369|2|2|kg|approved|13
118|243|539|70|70|pcs|approved|31
119|244|539|30|30|pcs|approved|31
120|245|3644|35|35|pcs|approved|114
121|246|583|5|5|TRIP|approved|360
122|247|583|1|1|TRIP|approved|360
123|248|583|1|1|TRIP|approved|360
124|249|84|1|1|TRIP|approved|360
125|250|3519|1|1|NOS|approved|11
126|251|3519|1|1|nos|approved|11
127|252|3028|85|0|pcs|approved|94
127|253|3026|80|0|pcs|approved|94
127|254|3507|65|8|pcs|approved|94
127|255|3640|30|30|pcs|approved|94
127|256|3641|35|35|pcs|approved|94
127|257|3643|70|0|pcs|approved|94
127|258|3636|30|0|pcs|approved|94
127|259|3637|145|0|pcs|approved|94
127|260|3638|60|0|pcs|approved|94
127|261|3639|80|0|pcs|approved|94
128|262|3659|50|0|nos|approved|94
128|263|3661|24|0|nos|approved|94
128|264|3665|85|0|nos|approved|94
128|265|3026|70|0|pcs|approved|94
128|266|3666|40|0|nos|approved|94
128|267|3667|20|0|nos|approved|94
128|268|3668|50|50|nos|approved|94
128|269|3507|40|0|pcs|approved|94
128|270|3669|100|0|nos|approved|94
128|271|3010|125|125|pcs|approved|94
128|272|3639|25|0|pcs|approved|94
128|273|3643|70|0|pcs|approved|94
128|274|3637|40|0|pcs|approved|94
129|275|583|9|0|pcs|rejected|0
129|276|3680|9|0|m3|rejected|0
129|277|539|100|0|pcs|approved|181
129|278|3681|650|0|pcs|rejected|0
129|279|3682|80|0|pcs|rejected|0
130|280|3721|100|100|pcs|approved|114
131|281|3724|534|534|pcs|approved|369
131|282|3725|860|480|pcs|approved|369
132|283|3734|1700|0|pcs|approved|369
132|284|3725|1600|0|pcs|approved|369
132|285|3724|1700|0|pcs|approved|369
132|286|3735|1700|0|pcs|approved|369
133|287|3741|20|20|pcs|approved|25
134|288|3369|45|45|kg|approved|25
135|289|3726|20|20|nos|approved|371
136|290|3742|1700|0|NOS|approved|359
137|291|3743|1|1|pcs|approved|25
139|293|3744|8|8|pcs|approved|25
140|294|555|6|3|m3|approved|360
141|295|3781|2|0|trips|approved|360
142|296|3783|1|0|pcs|approved|16
142|297|3784|2|0|pcs|approved|16
144|303|3364|15|15|pcs|approved|51
144|304|3381|5|5|pcs|approved|51
144|305|3744|10|10|pcs|approved|51
146|307|3692|130|0|pcs|rejected|0
146|308|3704|30|0|pcs|approved|94
146|309|3733|10|0|pcs|approved|94
146|310|3695|100|0|pcs|approved|94
146|311|3697|60|0|pcs|rejected|0
146|312|3791|10|0|pcs|approved|94
146|313|3688|20|0|pcs|approved|94
146|314|3686|15|0|pcs|approved|94
147|315|3792|1|0|ls|approved|373
148|316|3518|116|0|M3|approved|11
149|317|3561|103|0|M3|approved|11
149|318|3519|103|0|M3|approved|11
149|319|3520|103|0|M3|approved|11
150|320|3559|34|0|M3|approved|11
150|321|3519|1|0|NOS|approved|11
150|322|3520|34|0|M3|approved|11
151|323|3794|1|1|ctn|approved|51
151|324|3795|5|5|nos|approved|51"""

# id, kind, item, qty, from, location, request id, owner, reference, date, notes
MOVES = """628|in|3527|2.88|||0|0|MR-0012|2026-10-06|
771|in|3433|10|||0|0|MR-0013|2026-10-12|
772|in|326|20|||0|0|MR-0006|2026-10-12|
773|in|3449|30||919|0|0|MR-0005|2026-10-12|
774|in|3541|2||906|0|0|MR-0016|2026-10-10|
789|in|326|30|||98|0|MR-0007|2026-10-12|Against MR-0007
790|in|3408|15|||98|0|MR-0007|2026-10-12|Against MR-0007
791|in|3258|20|||105|0|MR-0014|2026-10-13|Against MR-0014
792|in|3370|108|||0|0|Added by hand|2026-10-13|
793|in|3371|108|||0|0|Added by hand|2026-10-13|
794|in|3370|1|||105|0|MR-0014|2026-10-13|
795|in|3371|1|||105|0|MR-0014|2026-10-13|
796|in|3539|3|||0|0|Opening stock|2026-10-13|
1091|in|3376|30|||109|0|MR-0018|2026-10-22|
1092|in|3624|1|||117|0|MR-0026|2026-10-22|
1093|in|3369|2|||117|0|MR-0026|2026-10-22|
1094|in|3623|1||910|116|0|MR-0025|2026-10-22|
1095|in|3616|200|||114|0|MR-0023|2026-10-22|
1096|in|2307|5|||114|0|MR-0023|2026-10-22|
1097|in|3624|49|||0|0|Added by hand|2026-10-22|
1098|in|2307|1|||0|0|Added by hand|2026-10-22|
1099|in|3369|28|||0|0|Added by hand|2026-10-22|
1114|in|3519|100|||110|0|MR-0019|2026-10-23|Against MR-0019
1115|in|3520|100|||110|0|MR-0019|2026-10-23|Against MR-0019
1116|in|3519|1|||111|0|MR-0020|2026-10-23|Against MR-0020
1117|in|3520|35|||111|0|MR-0020|2026-10-23|Against MR-0020
1118|in|3620|8||909|115|0|MR-0024|2026-10-23|
1160|in|583|1|||122|0|MR-0031|2026-10-24|Against MR-0031
1161|in|583|1|||123|0|MR-0032|2026-10-24|Against MR-0032
1162|in|3619|4||909|115|0|MR-0024|2026-10-24|Against MR-0024
1163|in|801|4||909|115|0|MR-0024|2026-10-24|Against MR-0024
1164|in|3621|5||909|115|0|MR-0024|2026-10-24|Against MR-0024
1165|in|3622|6||909|115|0|MR-0024|2026-10-24|Against MR-0024
1166|in|84|1|||124|0|MR-0033|2026-10-24|Against MR-0033
1167|in|583|5|||121|0|MR-0030|2026-10-24|Against MR-0030
1168|in|3519|1|||125|0|MR-0034|2026-10-24|Against MR-0034
1169|in|3528|0.3|||113|0|MR-0022|2026-10-24|Against MR-0022
1170|in|3519|1|||126|0|MR-0035|2026-10-24|Against MR-0035
1171|in|3469|1|||112|0|MR-0021|2026-10-24|Against MR-0021
1172|in|3520|25|||112|0|MR-0021|2026-10-24|Against MR-0021
1283|in|539|70||914|118|0|MR-0027|2026-10-24|Against MR-0027
1284|in|539|30||915|119|0|MR-0028|2026-10-24|Against MR-0028
1285|in|3644|35||909|120|0|MR-0029|2026-10-22|Against MR-0029
1349|in|3721|100||909|130|0|DER-25-20661|2026-10-27|FOR FALSE CEILING WORK
1448|in|3726|20|||135|0|MR-0044|2026-10-29|Against MR-0044
1450|in|3743|1|||137|0|DN00003232|2026-10-29|RECEIVED
1451|in|3744|8||910|139|0|DN00003232|2026-10-29|Against MR-0048
1452|in|3741|20|||133|0|DN00003232|2026-10-29|Against MR-0042
1453|in|3369|45|||134|0|DN00003232|2026-10-29|913 & 919 SLAB SHUTTERING WORK
1486|in|555|3||914|140|0|4381|2026-10-30|1 TRIP REACHED
1512|in|3364|15|||144|0|192589|2026-10-31|
1513|in|3381|5|||144|0|192589|2026-10-31|
1514|in|3724|534||914|131|0|BC1/12377/2026|2026-10-29|HOLLOW BLOCK 25CM BALANCE - 380
1515|in|3725|480||914|131|0|BC1/12377/2026|2026-10-29|HOLLOW BLOCK 25CM BALANCE - 380
1516|in|3744|10|||144|0|MR-0053|2026-10-31|
1517|in|3794|1|||151|0|MR-0060|2026-10-31|Against MR-0060
1518|in|3795|5|||151|0|MR-0060|2026-10-31|Against MR-0060"""

# hire-ins and returns from Desarch (owner 94): id, kind, item, qty, location, request id, reference, date
HIRE = """1012|in|3038|230|914|0|399106|2026-06-16
1013|in|3036|230|914|0|399106|2026-06-16
1014|in|3414|405|914|0|399106|2026-06-16
1015|in|3413|430|914|0|399106|2026-06-16
1016|in|3416|135|914|0|399106|2026-06-16
1017|in|3028|30|914|0|399106|2026-06-16
1018|in|3027|355|914|0|399106|2026-06-16
1019|in|3415|5|914|0|399106|2026-06-16
1020|in|3419|230|914|0|399106|2026-06-16
1061|in|3026|40|914|0|399106|2026-06-16
1062|in|3091|255|914|0|399106|2026-06-16
1063|in|3636|5|914|0|399106|2026-06-16
1064|in|3637|90|914|0|399106|2026-06-16
1065|in|3069|40|914|0|399106|2026-06-16
1066|in|3639|50|914|0|399106|2026-06-16
1067|in|3617|230|914|0|399106|2026-06-16
1068|in|3618|230|914|0|399106|2026-06-16
1069|in|3175|137|914|0|399152|2026-06-17
1070|in|1832|315|914|0|399152|2026-06-17
1071|in|3428|160|914|0|399152|2026-06-17
1072|in|3640|35|914|0|399152|2026-06-17
1073|in|3641|35|914|0|399152|2026-06-17
1156|in|3674|50|913|0|401118|2026-09-05
1157|in|3675|100|913|0|401118|2026-09-05
1158|in|3676|30|913|0|401118|2026-09-05
1159|in|3677|35|913|0|401118|2026-09-05
1174|in|3683|69|913|0|401141|2026-09-07
1175|in|3684|115|913|0|401141|2026-09-07
1176|in|3675|50|913|0|401141|2026-09-07
1177|in|3685|55|913|0|401141|2026-09-07
1178|in|3686|25|913|0|401141|2026-09-07
1179|in|3687|15|913|0|401141|2026-09-07
1180|in|3674|50|913|0|401141|2026-09-07
1181|in|3688|50|913|0|401141|2026-09-07
1182|in|3689|10|913|0|401141|2026-09-07
1183|in|3690|330|913|0|400830|2026-08-21
1184|in|3691|80|913|0|400830|2026-08-21
1185|hire_return|3690|328|913|0|RN-0001|2026-10-24
1186|in|3692|57|913|0|401105|2026-09-05
1187|in|3693|305|913|0|401105|2026-09-05
1188|in|3694|60|913|0|401105|2026-09-05
1189|in|3695|80|913|0|401105|2026-09-05
1190|in|3696|145|913|0|401105|2026-09-05
1191|in|3697|75|913|0|401105|2026-09-05
1192|in|3698|10|913|0|401105|2026-09-05
1193|in|3684|100|913|0|401105|2026-09-05
1194|in|3674|50|913|0|401105|2026-09-05
1195|in|3699|10|913|0|401251|2026-09-10
1196|in|3685|20|913|0|401251|2026-09-10
1197|in|3687|4|913|0|401251|2026-09-10
1198|in|3689|4|913|0|401251|2026-09-10
1199|in|3683|8|913|0|401165|2026-09-08
1200|in|3699|211|913|0|401165|2026-09-08
1201|in|3701|145|913|0|401165|2026-09-08
1202|in|3700|290|913|0|401165|2026-09-08
1203|in|3688|15|913|0|401165|2026-09-08
1204|in|3702|149|912|0|399032|2026-06-11
1213|in|3684|185|912|0|399032|2026-06-11
1234|in|3710|77|912|0|399987|2026-07-20
1243|in|3712|100|912|0|400045|2026-07-21
1244|in|3713|100|912|0|400045|2026-07-21
1257|in|3712|395|912|0|401064|2026-09-03
1258|in|3713|395|912|0|401064|2026-09-03
1276|hire_return|3692|182|912|0|RN-0002|2026-10-24
1281|hire_return|3674|60|912|0|RN-0003|2026-10-24
1293|hire_return|3691|80|913|0|RN-0006|2026-10-26
1295|in|3704|50|913|0|402370|2026-10-26
1296|in|3715|23|913|0|402370|2026-10-26
1297|in|3720|24|913|0|402370|2026-10-26
1298|in|3693|200|913|0|402370|2026-10-26
1299|in|3694|200|913|0|402370|2026-10-26
1300|in|3696|85|913|0|402370|2026-10-26
1301|in|3697|70|913|0|402370|2026-10-26
1302|in|3698|40|913|0|402370|2026-10-26
1303|in|3684|20|913|0|402370|2026-10-26
1304|in|3699|50|913|0|402370|2026-10-26
1305|in|3710|99|913|0|402370|2026-10-26
1306|in|3723|5|913|0|402370|2026-10-26
1324|hire_return|3674|148|913|0|RN-0007|2026-10-27
1325|hire_return|3701|100|913|0|RN-0007|2026-10-27
1326|in|3706|125|913|0|402385|2026-10-26
1327|in|3675|25|913|0|402385|2026-10-26
1328|in|3677|70|913|0|402385|2026-10-26
1329|in|3686|40|913|0|402385|2026-10-26
1330|in|3733|170|913|0|402408|2026-10-27
1331|in|3711|40|913|0|402408|2026-10-27
1372|in|3692|23|919|0|402417|2026-10-27
1373|in|3704|231|919|0|402417|2026-10-27
1374|in|3693|230|919|0|402417|2026-10-27
1375|in|3720|85|919|0|402417|2026-10-27
1376|in|3694|60|919|0|402417|2026-10-27
1377|in|3695|325|919|0|402417|2026-10-27
1378|in|3698|120|919|0|402417|2026-10-27
1379|in|3712|235|919|0|402417|2026-10-27
1380|in|3713|235|919|0|402417|2026-10-27
1381|in|3749|38|919|0|402417|2026-10-27
1382|in|3720|111|919|0|402409|2026-10-27
1383|in|3693|200|919|0|402409|2026-10-27
1384|in|3695|300|919|0|402409|2026-10-27
1385|in|3697|80|919|0|402409|2026-10-27
1386|in|3684|255|919|0|402409|2026-10-27
1387|in|3705|85|919|0|402422|2026-10-27
1388|in|3696|225|919|0|402422|2026-10-27
1389|in|3699|220|919|0|402422|2026-10-27
1390|in|3711|57|919|0|402422|2026-10-27
1391|in|3710|50|919|0|402422|2026-10-27
1392|in|3677|70|919|0|402422|2026-10-27
1393|in|3710|50|919|0|402423|2026-10-27
1394|in|3676|30|919|0|402423|2026-10-27
1395|in|3686|145|919|0|402423|2026-10-27
1396|in|3685|60|919|0|402423|2026-10-27
1397|in|3675|80|919|0|402423|2026-10-27
1398|in|3700|340|919|0|402423|2026-10-27
1472|in|3699|95|919|128|402445|2026-10-28
1473|in|3711|8|919|127|402445|2026-10-28
1474|in|3710|25|919|0|402445|2026-10-28
1475|in|3689|25|919|0|402445|2026-10-28
1476|in|3688|30|919|127|402445|2026-10-28
1477|in|3687|35|919|127|402445|2026-10-28
1519|in|3706|170|919|128|402503|2026-10-30"""

SITES = ["102", "104", "901", "902", "903", "904", "905", "906", "907", "908", "909", "910", "911", "912", "913", "914",
         "915", "916", "917", "918", "919", "920", "921", "922", "923", "924", "925", "926", "927", "Office", "Store"]


def rows(block):
    return [r.split("|") for r in block.strip().splitlines()]


def build(path, src="/tmp/claude-0/full.db"):
    shutil.copy(src, path)
    # the app's own start-up adds the new columns and tables (as the deploy does)
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{path}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
    subprocess.run([sys.executable, "-c", "import main; main._add_missing_columns()"], cwd=os.path.join(ROOT, "app"), env=env,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = sqlite3.connect(path)
    for t in ("lpo_receipts", "rental_maps", "purchase_order_lines", "purchase_orders", "material_request_lines", "material_requests",
              "store_movements", "hire_return_lines", "hire_returns", "store_items", "suppliers"):
        c.execute(f"DELETE FROM {t}")
    for code in SITES:
        if not c.execute("SELECT 1 FROM sites WHERE lower(code)=lower(?)", (code,)).fetchone():
            c.execute("INSERT INTO sites (code, active) VALUES (?, 1)", (code,))
    for i, n in SUPPLIERS.items():
        c.execute("INSERT INTO suppliers (id, name, name_key, active) VALUES (?,?,?,1)", (i, n, "".join(ch for ch in n.lower() if ch.isalnum())))
    for i, code, n, u, t in rows(ITEMS):
        c.execute("INSERT INTO store_items (id, code, name, unit, item_type, active) VALUES (?,?,?,?,?,1)", (int(i), code, n, u, t))
    for i in PLANT_ITEMS:
        c.execute("INSERT INTO store_items (id, code, name, unit, item_type, active) VALUES (?,?,?,?,?,1)", (i, f"ITM{i - 6}", f"Plant {i}", "nos", "consumable"))
    for i, no, ref, d, sup, rq, loc, st, rl, comb, disc in rows(ORDERS):
        c.execute("""INSERT INTO purchase_orders (id, po_no, ref, order_date, supplier_id, supplier_name, request_id, project_location, status,
                     request_line_ids, combined, discount_pct, round_off, tax_pct, zoho_status, zoho_id, terms, cancel_reason)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,5,'sent','purchaseorder:x','Due on Receipt',?)""",
                  (int(i), int(no), ref, d, int(sup), SUPPLIERS[int(sup)], int(rq) or None, loc, st, rl, int(comb), float(disc),
                   "Site says material no longer needed" if st == "cancelled" else ""))
    for o, i, it, d, q, u, r, ct in rows(LINES):
        c.execute("INSERT INTO purchase_order_lines (id, order_id, item_id, description, qty, unit, rate, tax_pct, cost_to) VALUES (?,?,?,?,?,?,?,5,?)",
                  (int(i), int(o), int(it), d, float(q), u, float(r), ct))
    for i, it, q in PLANT_LINES:
        c.execute("INSERT INTO purchase_order_lines (id, order_id, item_id, description, qty, unit, rate, tax_pct) VALUES (?,?,?,?,?,?,?,5)",
                  (i, 51, it, f"Plant line {i}", q, "nos", 100.0))
    for i, ref, site, st, lpo, on, notes in rows(REQUESTS):
        c.execute("INSERT INTO material_requests (id, ref, site, status, lpo_id, requested_on, notes, requested_by, urgency, office_remark) VALUES (?,?,?,?,?,?,?,'','normal','')",
                  (int(i), ref, site, st, int(lpo) or None, on, notes))
    for rq, i, it, q, g, u, st, sup in rows(REQ_LINES):
        c.execute("""INSERT INTO material_request_lines (id, request_id, item_id, description, qty_requested, qty_approved, qty_received, unit,
                     status, supplier_id, est_cost, notes, purpose) VALUES (?,?,?,'',?,?,?,?,?,?,0,'','')""",
                  (int(i), int(rq), int(it), float(q), float(q), float(g), u, st, int(sup) or None))
    for i, k, it, q, fr, loc, rq, ow, ref, d, notes in rows(MOVES):
        c.execute("""INSERT INTO store_movements (id, item_id, kind, qty, from_location, location, request_id, owner_id, reference, moved_on, notes,
                     supplier, unit_cost, incharge, condition) VALUES (?,?,?,?,?,?,?,?,?,?,?,'',0,'','')""",
                  (int(i), int(it), k, float(q), fr, loc, int(rq) or None, int(ow) or None, ref, d, notes))
    for i, k, it, q, loc, rq, ref, d in rows(HIRE):
        c.execute("""INSERT INTO store_movements (id, item_id, kind, qty, from_location, location, request_id, owner_id, reference, moved_on, notes,
                     supplier, unit_cost, incharge, condition) VALUES (?,?,?,?,?,?,?,94,?,?,'','Desarch Building Contracting L.l.c',0,'','')""",
                  (int(i), int(it), k, float(q), loc if k == "hire_return" else "", loc if k == "in" else "", int(rq) or None, ref, d))
    c.commit()
    c.close()


if __name__ == "__main__":
    build(sys.argv[1])
    print("replica written:", sys.argv[1])
