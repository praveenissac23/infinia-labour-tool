"""A copy of the live rental records the 01 Nov 2026 rental stock correction touches (deploy/fix_rentals_2026_11_01.py),
read from the live database (read-only, 01 Nov 2026) with their real ids, laid over the purchasing replica
(tests/purchasing_fix_replica.py - a copy of the full test database with the live purchasing records).

    python3 tests/rental_fix_replica.py /path/to/copy.db

Overlaid: every material that ever held rental stock, every 'Rental ...' or Rental-typed material, every material
on an LPO of Najm Al Ofuq or Desarch (110 materials, as they are on live today), every stock movement of those
materials (267), the Najm LPOs 20260103 / 20260109 and every line of the five Najm / Desarch LPOs. Payroll and
everything else in the copy is left as it is."""
import os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import purchasing_fix_replica as R

DESARCH = "Desarch Building Contracting L.l.c"
NAJM = "Najm Al Ofuq Scaffolding Tr. L.l.c"

# id|code|name|unit|type|active|rental_supplier|category   (live, 01/11/2026)
ITEMS = """1017|ITM1014|Subcon Power Float|pcs|rental|1||
1022|ITM1019|GRP Lining Work - Subcontractor - Supply & Application|pcs|rental|1||
1081|ITM1078|Bob Cat Monthly|pcs|rental|1||
1105|ITM1102|Shovel Hourly|pcs|rental|0||
1117|ITM1114|Hire Of Crawler Crane|pcs|rental|1||
1203|ITM1200|Scaffold Hiring - Bracing Tube 1.5M|pcs|rental|1||
1832|ITM1829|Swivel Clamp|pcs|asset|1||
1848|ITM1845|Universal Clamp|pcs|consumable|1||
3010|ITM3007|Bracing Tube 4.0M|pcs|consumable|1||
3026|ITM3023|Ledger 0.9M|pcs|asset|1||
3027|ITM3024|Ledger 1.00M|pcs|asset|1||
3028|ITM3025|Ledger 1.2M|pcs|asset|1||
3034|ITM3031|Standard 1.00M|pcs|asset|1||
3036|ITM3033|Standard 1.50M|pcs|asset|1||
3038|ITM3035|Standard 2.00M|pcs|asset|1||
3069|ITM3066|Aluminium Beams 4.0M|pcs|consumable|1||
3091|ITM3088|U-Head Jack|pcs|asset|1||
3175|ITM3172|Prop 5.0M|pcs|asset|1||
3413|ITM3407|Ledger 1.60M|pcs|asset|1||
3414|ITM3408|Ledger 1.8 M|pcs|asset|1||
3415|ITM3409|Ledger 0.6 M|pcs|asset|1||
3416|ITM3410|Ledger 1.3 M|pcs|asset|1||
3419|ITM3413|Adjustable Base Jack|pcs|asset|1||
3428|ITM3422|Scaffolding Tube 4mtr|pcs|asset|1||
3477|ITM3471|Universal Angle Tie Bracket|NOS|consumable|1||
3478|ITM3472|Connecting Pin with Revit Pin|NOS|consumable|1||
3496|ITM3490|Cuplock Standard (1.30 M)|NOS|consumable|0||
3497|ITM3491|Cuplock Standard (1.50 M)|NOS|consumable|0||
3498|ITM3492|Cuplock Standard (1.80 M)|NOS|consumable|0||
3499|ITM3493|Cuplock Standard (2.50 M)|NOS|consumable|0||
3500|ITM3494|Cuplock Standard (3.00 M)|NOS|consumable|0||
3501|ITM3495|Cuplock Ledger (0.90 M)|NOS|consumable|1||
3502|ITM3496|Cuplock Ledger (1.20 M)|NOS|consumable|1||
3503|ITM3497|Cuplock Ledger (1.60 M)|NOS|consumable|1||
3504|ITM3498|Adjustable Base Jacks Hollow|NOS|consumable|0||
3505|ITM3499|Adjustable U-Head Jacks Hollow|NOS|consumable|0||
3506|ITM3500|Spigot Connector|NOS|consumable|1||
3507|ITM3501|Cantilever Frame 1.5M|pcs|asset|1||
3508|ITM3502|Scaffolding Tube 3 MM (2.00 M)|NOS|consumable|1||
3509|ITM3503|Scaffolding Tube 3 MM (6.00 M)|NOS|consumable|1||
3510|ITM3504|Forged Swivel Coupler|NOS|consumable|1||
3511|ITM3505|Light Duty Steel Props (3.90 M)|NOS|consumable|1||
3512|ITM3506|Aluminium Beem 3.50 mtr|NOS|consumable|1||
3513|ITM3507|Aluminium Beem 4.50 mtr|NOS|consumable|1||
3617|ITM3611|Spigot Pin|pcs|asset|1||
3618|ITM3612|Spigot Pin Nut/Bolt|pcs|asset|1||
3636|ITM3630|Aluminium Beam 3.0M|pcs|asset|1||
3637|ITM3631|Aluminium Beam 3.5M|pcs|asset|1||
3638|ITM3632|Aluminium Beam 4.0M|pcs|asset|1||
3639|ITM3633|Aluminium Beam 4.5M|pcs|asset|1||
3640|ITM3634|Aluminium Beam 1.5M|pcs|asset|1||
3641|ITM3635|Aluminium Beam 2.0M|pcs|asset|1||
3643|ITM3637|Aluminium Beam 2.5M|pcs|asset|1||
3658|ITM3652|Standard 3.0m|nos|consumable|0||
3659|ITM3653|Standard 2.0m|nos|consumable|1||
3660|ITM3654|Standard 1.8m|nos|consumable|1||
3661|ITM3655|Standard 1.3m|nos|consumable|1||
3662|ITM3656|Ledger 1.8m|nos|consumable|1||
3663|ITM3657|Ledger 1.6m|nos|consumable|1||
3664|ITM3658|Ledger 1.3m|nos|consumable|0||
3665|ITM3659|Ledger 1.0m|nos|consumable|1||
3666|ITM3660|Ledger 0.6m|nos|consumable|1||
3667|ITM3661|Adjustable Base/base jack|nos|consumable|1||
3668|ITM3662|Adjustable "U" Head|nos|consumable|1||
3669|ITM3663|M.D Props 3.20 to 5.0m|nos|consumable|1||
3670|ITM3664|Spigot / Nut & Bolt|nos|consumable|1||
3671|ITM3665|Swivel Coupler- Forged|nos|consumable|1||
3672|ITM3666|ALUMINIUM BEAM 1.0m|nos|consumable|1||
3674|ITM3668|Rental Prop 4.0M|pcs|asset|1||
3675|ITM3669|Rental Aluminium Beam 4.5M|pcs|asset|1||
3676|ITM3670|Rental Aluminium Beam 3.0M|pcs|asset|1||
3677|ITM3671|Rental Aluminium Beam 2.5M|pcs|asset|1||
3678|ITM3672|Standard 1.5m|nos|consumable|1||
3679|ITM3673|M.D Props 3.20 to 6.0m|nos|consumable|1||
3683|ITM3677|Rental Standard 2.8M|pcs|asset|1||
3684|ITM3678|Rental ADJ Base Jack|pcs|asset|1||
3685|ITM3679|Rental Aluminium Beam 4.0M|pcs|asset|1||
3686|ITM3680|Rental Aluminium Beam 3.5m|pcs|asset|1||
3687|ITM3681|Rental Aluminium Beam 2.0M|pcs|asset|1||
3688|ITM3682|Rental Aluminium Beam 1.5M|pcs|asset|1||
3689|ITM3683|Rental Aluminium Beam 1.0M|pcs|asset|1||
3690|ITM3684|Rental Tie Rode Set 1.5M|pcs|asset|1||
3691|ITM3685|Rental Tie Rode Set 1.0M|pcs|asset|1||
3692|ITM3686|Rental Standard 3.0M|pcs|asset|1||
3693|ITM3687|Rental Ledger 1.8M|pcs|asset|1||
3694|ITM3688|Rental Ledger 1.6M|pcs|asset|1||
3695|ITM3689|Rental Ledger 1.3M|pcs|asset|1||
3696|ITM3690|Rental Ledger 1.0M|pcs|asset|1||
3697|ITM3691|Rental Ledger 0.9M|pcs|asset|1||
3698|ITM3692|Rental Ledger 0.6M|pcs|asset|1||
3699|ITM3693|Rental U-Head Jack|pcs|asset|1||
3700|ITM3694|Rental Swivel Clamp|pcs|asset|1||
3701|ITM3695|Rental Tube 2.5M|pcs|asset|1||
3702|ITM3696|Rental Standard 2.5M|pcs|asset|1||
3703|ITM3697|Rental Standard 2.3M|pcs|asset|1||
3704|ITM3698|Rental Standard 2.0M|pcs|asset|1||
3705|ITM3699|Rental Ledger 1.2M|pcs|asset|1||
3706|ITM3700|Rental Tube 4.0M|pcs|asset|1||
3707|ITM3701|Rental Tube 3.0M|pcs|asset|1||
3710|ITM3704|Rental Prop 5.0M|pcs|asset|1||
3711|ITM3705|Rental Cantilever Frame 1.5M|pcs|asset|1||
3712|ITM3706|Rental Spigot Pin|pcs|asset|1||
3713|ITM3707|Rental Spigot Pin Nut/Bolt|pcs|asset|1||
3714|ITM3708|Rental Tube 1.5M|pcs|asset|1||
3715|ITM3709|Rental Standard 1.5M|pcs|asset|1||
3720|ITM3714|Rental Standard 1.3M|pcs|asset|1||
3723|ITM3717|Rental Prop 6.0M|pcs|asset|1||
3733|ITM3727|Rental Standard 1.0M|pcs|asset|1||
3749|ITM3743|Rental Standard 1.8M|pcs|consumable|1||
3791|ITM3785|Rental Tube 6.0M|pcs|consumable|1||"""

# id|kind|item|qty|from|location|owner|reference|date|request|supplier (D = Desarch, X = another trader)
MOVES = """343|in|3413|97|||0|Opening stock|2026-09-28|0|
344|in|3414|138|||0|Opening stock|2026-09-28|0|
345|in|3415|11|||0|Opening stock|2026-09-28|0|
346|in|3416|4|||0|Opening stock|2026-09-28|0|
349|in|3416|16|||0|Added by hand|2026-09-28|0|
350|in|3038|14|||0|Added by hand|2026-09-28|0|
351|in|3034|1|||0|Added by hand|2026-09-28|0|
354|in|3419|47|||0|Opening stock|2026-09-28|0|
355|in|1832|39|||0|Added by hand|2026-09-28|0|
365|in|3428|4|||0|Opening stock|2026-09-28|0|
367|out|3413|97||910|0||2026-09-26|0|
368|out|3038|14||910|0||2026-09-26|0|
369|out|3419|47||910|0||2026-09-26|0|
370|out|3414|138||910|0||2026-09-26|0|
371|out|3415|11||910|0||2026-09-26|0|
372|out|3416|20||910|0||2026-09-26|0|
373|out|3034|1||910|0||2026-09-26|0|
383|out|1832|39||910|0||2026-09-26|0|
384|transfer|3414|60|910|913|0||2026-09-26|0|
420|out|3428|4||910|0||2026-09-26|0|
545|in|1848|46|||0|MR-0004|2026-10-01|0|X
732|in|3414|16||919|0|Added by hand|2026-10-12|0|
733|in|3413|16||919|0|Added by hand|2026-10-12|0|
734|in|3419|8||919|0|Added by hand|2026-10-12|0|
911|in|1832|100||926|0|Added by hand|2026-10-14|0|
912|in|3419|38||926|0|Added by hand|2026-10-14|0|
914|in|3026|7||926|0|Added by hand|2026-10-14|0|
916|in|3028|19||926|0|Added by hand|2026-10-14|0|
921|in|3414|3||926|0|Added by hand|2026-10-14|0|
922|in|3034|13||926|0|Added by hand|2026-10-14|0|
959|transfer|3413|64|910|913|0||2026-10-15|0|
1000|transfer|3038|14|910|909|0||2026-10-15|0|
1002|transfer|3034|1|910|909|0||2026-10-15|0|
1003|transfer|3414|78|910|909|0||2026-10-15|0|
1004|transfer|3416|20|910|909|0||2026-10-15|0|
1005|transfer|3413|33|910|909|0||2026-10-15|0|
1006|transfer|3415|11|910|909|0||2026-10-15|0|
1007|transfer|3419|47|910|909|0||2026-10-15|0|
1012|in|3038|230||914|94|399106|2026-06-16|0|D
1013|in|3036|230||914|94|399106|2026-06-16|0|D
1014|in|3414|405||914|94|399106|2026-06-16|0|D
1015|in|3413|430||914|94|399106|2026-06-16|0|D
1016|in|3416|135||914|94|399106|2026-06-16|0|D
1017|in|3028|30||914|94|399106|2026-06-16|0|D
1018|in|3027|355||914|94|399106|2026-06-16|0|D
1019|in|3415|5||914|94|399106|2026-06-16|0|D
1020|in|3419|230||914|94|399106|2026-06-16|0|D
1061|in|3026|40||914|94|399106|2026-06-16|0|D
1062|in|3091|255||914|94|399106|2026-06-16|0|D
1063|in|3636|5||914|94|399106|2026-06-16|0|D
1064|in|3637|90||914|94|399106|2026-06-16|0|D
1065|in|3069|40||914|94|399106|2026-06-16|0|D
1066|in|3639|50||914|94|399106|2026-06-16|0|D
1067|in|3617|230||914|94|399106|2026-06-16|0|D
1068|in|3618|230||914|94|399106|2026-06-16|0|D
1069|in|3175|137||914|94|399152|2026-06-17|0|D
1070|in|1832|315||914|94|399152|2026-06-17|0|D
1071|in|3428|160||914|94|399152|2026-06-17|0|D
1072|in|3640|35||914|94|399152|2026-06-17|0|D
1073|in|3641|35||914|94|399152|2026-06-17|0|D
1119|in|3028|22||909|0|Added by hand|2026-10-23|0|
1120|transfer|3028|22|909|919|0||2026-10-17|0|
1121|in|3414|12||909|0|Added by hand|2026-10-23|0|
1122|in|3413|19|||0|Added by hand|2026-10-23|0|
1124|transfer|3414|90|909|919|0||2026-10-23|0|
1125|transfer|3413|33|909|919|0||2026-10-23|0|
1127|out|3413|19||919|0||2026-10-23|0|
1130|in|3413|11||915|0|Added by hand|2026-10-23|0|
1132|in|3414|11||926|0|Added by hand|2026-10-23|0|
1133|in|3416|12||926|0|Added by hand|2026-10-23|0|
1134|in|3416|24||909|0|Added by hand|2026-10-23|0|
1135|in|3414|10||909|0|Added by hand|2026-10-23|0|
1136|transfer|3414|10|909|919|0||2026-10-23|0|
1137|transfer|3416|24|909|919|0||2026-10-23|0|
1152|in|3413|80||919|0|Added by hand|2026-10-24|0|
1153|in|3414|18||919|0|Added by hand|2026-10-24|0|
1156|in|3674|50||913|94|401118|2026-09-05|0|D
1157|in|3675|100||913|94|401118|2026-09-05|0|D
1158|in|3676|30||913|94|401118|2026-09-05|0|D
1159|in|3677|35||913|94|401118|2026-09-05|0|D
1174|in|3683|69||913|94|401141|2026-09-07|0|D
1175|in|3684|115||913|94|401141|2026-09-07|0|D
1176|in|3675|50||913|94|401141|2026-09-07|0|D
1177|in|3685|55||913|94|401141|2026-09-07|0|D
1178|in|3686|25||913|94|401141|2026-09-07|0|D
1179|in|3687|15||913|94|401141|2026-09-07|0|D
1180|in|3674|50||913|94|401141|2026-09-07|0|D
1181|in|3688|50||913|94|401141|2026-09-07|0|D
1182|in|3689|10||913|94|401141|2026-09-07|0|D
1183|in|3690|330||913|94|400830|2026-08-21|0|D
1184|in|3691|80||913|94|400830|2026-08-21|0|D
1185|hire_return|3690|328|913|913|94|RN-0001|2026-10-24|0|D
1186|in|3692|57||913|94|401105|2026-09-05|0|D
1187|in|3693|305||913|94|401105|2026-09-05|0|D
1188|in|3694|60||913|94|401105|2026-09-05|0|D
1189|in|3695|80||913|94|401105|2026-09-05|0|D
1190|in|3696|145||913|94|401105|2026-09-05|0|D
1191|in|3697|75||913|94|401105|2026-09-05|0|D
1192|in|3698|10||913|94|401105|2026-09-05|0|D
1193|in|3684|100||913|94|401105|2026-09-05|0|D
1194|in|3674|50||913|94|401105|2026-09-05|0|D
1195|in|3699|10||913|94|401251|2026-09-10|0|D
1196|in|3685|20||913|94|401251|2026-09-10|0|D
1197|in|3687|4||913|94|401251|2026-09-10|0|D
1198|in|3689|4||913|94|401251|2026-09-10|0|D
1199|in|3683|8||913|94|401165|2026-09-08|0|D
1200|in|3699|211||913|94|401165|2026-09-08|0|D
1201|in|3701|145||913|94|401165|2026-09-08|0|D
1202|in|3700|290||913|94|401165|2026-09-08|0|D
1203|in|3688|15||913|94|401165|2026-09-08|0|D
1204|in|3702|149||912|94|399032|2026-06-11|0|D
1205|in|3703|10||912|94|399032|2026-06-11|0|D
1206|in|3704|35||912|94|399032|2026-06-11|0|D
1207|in|3694|100||912|94|399032|2026-06-11|0|D
1208|in|3705|115||912|94|399032|2026-06-11|0|D
1209|in|3696|125||912|94|399032|2026-06-11|0|D
1210|in|3698|30||912|94|399032|2026-06-11|0|D
1211|in|3706|117||912|94|399032|2026-06-11|0|D
1212|in|3707|8||912|94|399032|2026-06-11|0|D
1213|in|3684|185||912|94|399032|2026-06-11|0|D
1214|in|3700|250||912|94|399032|2026-06-11|0|D
1215|in|3689|10||912|94|399032|2026-06-11|0|D
1216|in|3688|50||912|94|399032|2026-06-11|0|D
1217|in|3687|25||912|94|399032|2026-06-11|0|D
1218|in|3677|80||912|94|399032|2026-06-11|0|D
1219|in|3676|45||912|94|399032|2026-06-11|0|D
1220|in|3686|20||912|94|399032|2026-06-11|0|D
1221|in|3685|20||912|94|399032|2026-06-11|0|D
1222|in|3675|100||912|94|399032|2026-06-11|0|D
1223|in|3674|80||912|94|399145|2026-06-17|0|D
1224|in|3683|16||912|94|399145|2026-06-17|0|D
1225|in|3676|50||912|94|399850|2026-07-14|0|D
1226|in|3692|225||912|94|399987|2026-07-20|0|D
1227|in|3703|40||912|94|399987|2026-07-20|0|D
1228|in|3720|195||912|94|399987|2026-07-20|0|D
1229|in|3705|200||912|94|399987|2026-07-20|0|D
1230|in|3696|150||912|94|399987|2026-07-20|0|D
1231|in|3697|317||912|94|399987|2026-07-20|0|D
1232|in|3698|221||912|94|399987|2026-07-20|0|D
1233|in|3687|50||912|94|399987|2026-07-20|0|D
1234|in|3710|77||912|94|399987|2026-07-20|0|D
1235|in|3705|50||912|94|400045|2026-07-21|0|D
1236|in|3697|153||912|94|400045|2026-07-21|0|D
1237|in|3698|74||912|94|400045|2026-07-21|0|D
1238|in|3711|40||912|94|400045|2026-07-21|0|D
1239|in|3685|10||912|94|400045|2026-07-21|0|D
1240|in|3686|25||912|94|400045|2026-07-21|0|D
1241|in|3676|60||912|94|400045|2026-07-21|0|D
1242|in|3689|20||912|94|400045|2026-07-21|0|D
1243|in|3712|100||912|94|400045|2026-07-21|0|D
1244|in|3713|100||912|94|400045|2026-07-21|0|D
1250|in|3700|100||912|94|400481|2026-08-07|0|D
1251|in|3704|101||912|94|401064|2026-09-03|0|D
1252|in|3715|160||912|94|401064|2026-09-03|0|D
1253|in|3693|300||912|94|401064|2026-09-03|0|D
1254|in|3695|100||912|94|401064|2026-09-03|0|D
1255|in|3696|50||912|94|401064|2026-09-03|0|D
1256|in|3698|100||912|94|401064|2026-09-03|0|D
1257|in|3712|395||912|94|401064|2026-09-03|0|D
1258|in|3713|395||912|94|401064|2026-09-03|0|D
1259|in|3707|225||912|94|401064|2026-09-03|0|D
1260|in|3714|30||912|94|401064|2026-09-03|0|D
1261|in|3675|100||912|94|401064|2026-09-03|0|D
1262|in|3692|100||912|94|401065|2026-09-03|0|D
1263|in|3683|20||912|94|401065|2026-09-03|0|D
1264|in|3704|79||912|94|401065|2026-09-03|0|D
1265|in|3694|40||912|94|401065|2026-09-03|0|D
1266|in|3695|85||912|94|401065|2026-09-03|0|D
1267|in|3684|100||912|94|401065|2026-09-03|0|D
1268|in|3711|20||912|94|401065|2026-09-03|0|D
1269|in|3675|20||912|94|401065|2026-09-03|0|D
1270|in|3685|35||912|94|401065|2026-09-03|0|D
1271|in|3677|50||912|94|401065|2026-09-03|0|D
1272|in|3694|360||912|94|401117|2026-09-05|0|D
1273|in|3696|450||912|94|401117|2026-09-05|0|D
1274|in|3700|400||912|94|401117|2026-09-05|0|D
1275|in|3700|300||912|94|401447|2026-09-18|0|D
1276|hire_return|3692|182|912|912|94|RN-0002|2026-10-24|0|D
1277|hire_return|3685|1|912|912|94|RN-0003|2026-10-24|0|D
1278|hire_return|3675|85|912|912|94|RN-0003|2026-10-24|0|D
1279|hire_return|3696|4|912|912|94|RN-0003|2026-10-24|0|D
1280|hire_return|3694|2|912|912|94|RN-0003|2026-10-24|0|D
1281|hire_return|3674|60|912|912|94|RN-0003|2026-10-24|0|D
1282|hire_return|3704|4|912|912|94|RN-0003|2026-10-24|0|D
1286|hire_return|3698|123|912|912|94|RN-0004|2026-10-26|0|D
1287|hire_return|3697|295|912|912|94|RN-0004|2026-10-26|0|D
1288|hire_return|3696|77|912|912|94|RN-0004|2026-10-26|0|D
1289|hire_return|3694|4|912|912|94|RN-0004|2026-10-26|0|D
1290|hire_return|3720|51|912|912|94|RN-0004|2026-10-26|0|D
1291|hire_return|3703|18|912|912|94|RN-0004|2026-10-26|0|D
1292|hire_return|3702|6|912|912|94|RN-0004|2026-10-26|0|D
1293|hire_return|3691|80|913|913|94|RN-0006|2026-10-26|0|D
1295|in|3704|50||913|94|402370|2026-10-26|0|D
1296|in|3715|23||913|94|402370|2026-10-26|0|D
1297|in|3720|24||913|94|402370|2026-10-26|0|D
1298|in|3693|200||913|94|402370|2026-10-26|0|D
1299|in|3694|200||913|94|402370|2026-10-26|0|D
1300|in|3696|85||913|94|402370|2026-10-26|0|D
1301|in|3697|70||913|94|402370|2026-10-26|0|D
1302|in|3698|40||913|94|402370|2026-10-26|0|D
1303|in|3684|20||913|94|402370|2026-10-26|0|D
1304|in|3699|50||913|94|402370|2026-10-26|0|D
1305|in|3710|99||913|94|402370|2026-10-26|0|D
1306|in|3723|5||913|94|402370|2026-10-26|0|D
1324|hire_return|3674|148|913|913|94|RN-0007|2026-10-27|0|D
1325|hire_return|3701|100|913|913|94|RN-0007|2026-10-27|0|D
1326|in|3706|125||913|94|402385|2026-10-26|0|D
1327|in|3675|25||913|94|402385|2026-10-26|0|D
1328|in|3677|70||913|94|402385|2026-10-26|0|D
1329|in|3686|40||913|94|402385|2026-10-26|0|D
1330|in|3733|170||913|94|402408|2026-10-27|0|D
1331|in|3711|40||913|94|402408|2026-10-27|0|D
1372|in|3692|23||919|94|402417|2026-10-27|0|D
1373|in|3704|231||919|94|402417|2026-10-27|0|D
1374|in|3693|230||919|94|402417|2026-10-27|0|D
1375|in|3720|85||919|94|402417|2026-10-27|0|D
1376|in|3694|60||919|94|402417|2026-10-27|0|D
1377|in|3695|325||919|94|402417|2026-10-27|0|D
1378|in|3698|120||919|94|402417|2026-10-27|0|D
1379|in|3712|235||919|94|402417|2026-10-27|0|D
1380|in|3713|235||919|94|402417|2026-10-27|0|D
1381|in|3749|38||919|94|402417|2026-10-27|0|D
1382|in|3720|111||919|94|402409|2026-10-27|0|D
1383|in|3693|200||919|94|402409|2026-10-27|0|D
1384|in|3695|300||919|94|402409|2026-10-27|0|D
1385|in|3697|80||919|94|402409|2026-10-27|0|D
1386|in|3684|255||919|94|402409|2026-10-27|0|D
1387|in|3705|85||919|94|402422|2026-10-27|0|D
1388|in|3696|225||919|94|402422|2026-10-27|0|D
1389|in|3699|220||919|94|402422|2026-10-27|0|D
1390|in|3711|57||919|94|402422|2026-10-27|0|D
1391|in|3710|50||919|94|402422|2026-10-27|0|D
1392|in|3677|70||919|94|402422|2026-10-27|0|D
1393|in|3710|50||919|94|402423|2026-10-27|0|D
1394|in|3676|30||919|94|402423|2026-10-27|0|D
1395|in|3686|145||919|94|402423|2026-10-27|0|D
1396|in|3685|60||919|94|402423|2026-10-27|0|D
1397|in|3675|80||919|94|402423|2026-10-27|0|D
1398|in|3700|340||919|94|402423|2026-10-27|0|D
1472|in|3699|95||919|94|402445|2026-10-28|128|D
1473|in|3711|8||919|94|402445|2026-10-28|127|D
1474|in|3710|25||919|94|402445|2026-10-28|0|D
1475|in|3689|25||919|94|402445|2026-10-28|0|D
1476|in|3688|30||919|94|402445|2026-10-28|127|D
1477|in|3687|35||919|94|402445|2026-10-28|127|D
1503|in|3419|71||925|0|Added by hand|2026-10-31|0|
1504|in|3091|2||925|0|Added by hand|2026-10-31|0|
1506|in|1832|228||925|0|Added by hand|2026-10-31|0|
1507|in|3028|4||925|0|Added by hand|2026-10-31|0|
1508|in|3414|31||925|0|Added by hand|2026-10-31|0|
1509|in|3027|3||925|0|Added by hand|2026-10-31|0|
1510|in|3416|1||925|0|Added by hand|2026-10-31|0|
1511|in|3413|1||925|0|Added by hand|2026-10-31|0|
1519|in|3706|170||919|94|402503|2026-10-30|128|D
1527|in|3704|30||926|0|402545|2026-10-31|146|D
1528|in|3733|10||926|0|402545|2026-10-31|146|D
1529|in|3695|100||926|0|402545|2026-10-31|146|D
1530|in|3791|10||926|0|402545|2026-10-31|146|D
1531|in|3688|20||926|0|402545|2026-10-31|146|D
1532|in|3686|15||926|0|402545|2026-10-31|146|D
1533|in|3702|150||926|94|402545|2026-10-31|153|D
1534|in|3704|30||926|94|402545|2026-10-31|128|D
1535|in|3733|10||926|94|402545|2026-10-31|0|D
1536|in|3695|100||926|94|402545|2026-10-31|0|D
1537|in|3791|10||926|94|402545|2026-10-31|0|D
1538|in|3688|20||926|94|402545|2026-10-31|0|D
1539|in|3686|15||926|94|402545|2026-10-31|128|D"""

# Najm Al Ofuq's two LPOs (not in the purchasing replica): id|po_no|ref|date|location
NAJM_ORDERS = """23|20260103|IC/LPO/20260103|2026-09-23|910&911 SOBHA HARTLAND
29|20260109|IC/LPO/20260109|2026-09-28|913"""

# every line of the five Najm / Desarch LPOs: order|line|item|description|qty|unit|rate
LINES = """23|153|3496|Cuplock Standard (1.30 M)|3|NOS|21
23|154|3497|Cuplock Standard (1.50 M)|5|NOS|24.5
23|155|3498|Cuplock Standard (1.80 M)|5|NOS|30
23|156|3499|Cuplock Standard (2.50 M)|24|NOS|41
23|157|3500|Cuplock Standard (3.00 M)|56|NOS|50
23|158|3501|Cuplock Ledger (0.90 M)|51|NOS|11.5
23|159|3502|Cuplock Ledger (1.20 M)|100|NOS|14.5
23|160|3503|Cuplock Ledger (1.60 M)|62|NOS|18.5
23|161|3504|Adjustable Base Jacks Hollow|119|NOS|14
23|162|3505|Adjustable U-Head Jacks Hollow|26|NOS|20
23|163|3506|Spigot Connector|400|NOS|3.5
23|164|3507|Cantilever Frame (1.30 M)|3|NOS|60
23|165|3508|Scaffolding Tube 3 MM (2.00 M)|1|NOS|26
23|166|3509|Scaffolding Tube 3 MM (6.00 M)|14|NOS|78
23|167|3510|Forged Swivel Coupler|169|NOS|5
23|168|3511|Light Duty Steel Props (3.90 M)|19|NOS|31
23|169|3512|Aluminium Beem 3.50 mtr|6|NOS|206
23|170|3513|Aluminium Beem 4.50 mtr|2|NOS|265
29|132|1848|Universal Clamp|46|NOS|5.5
29|133|3477|Universal Angle Tie Bracket|28|NOS|100
29|134|3478|Connecting Pin with Revit Pin|51|NOS|10
68|464|3658|Standard 3.0m|23|nos|0.9
68|465|3659|Standard 2.0m|231|nos|0.7
68|466|3660|Standard 1.8m|38|nos|0.63
68|467|3661|Standard 1.3m|196|nos|0.55
68|468|3662|Ledger 1.8m|430|nos|0.44
68|469|3663|Ledger 1.6m|60|nos|0.4
68|470|3664|Ledger 1.3m|625|nos|0.36
68|471|3028|Ledger 1.2m|85|nos|0.35
68|472|3665|Ledger 1.0m|225|nos|0.3
68|473|3026|Ledger 0.9m|80|nos|0.28
68|474|3666|Ledger 0.6m|120|nos|0.24
68|475|3667|Adjustable Base/base jack|255|nos|0.45
68|476|3668|Adjustable "U" Head|315|nos|0.5
68|477|3507|Cantilever Frame 1.5m|65|nos|1.25
68|478|3669|M.D Props 3.20 to 5.0m|125|nos|2.5
68|479|3670|Spigot / Nut & Bolt|235|nos|0.3
68|480|3671|Swivel Coupler- Forged|340|nos|0.22
68|481|3010|Bracing Tube 4.0m|170|nos|0.8
68|482|3672|ALUMINIUM BEAM 1.0m|25|nos|1.5
68|483|3640|ALUMINIUM BEAM 1.5m|30|nos|2.25
68|484|3641|ALUMINIUM BEAM 2.0m|35|nos|3
68|485|3643|Aluminium Beam 2.5m|70|nos|3.75
68|486|3636|Aluminium Beam 3.0m|30|nos|4.5
68|487|3637|Aluminium Beam 3.5m|145|nos|5.25
68|488|3638|Aluminium Beam 4.0m|60|nos|6
68|489|3639|Aluminium Beam 4.5m|80|nos|6.75
70|545|3659|Standard 2.0m|50|nos|0.7
70|546|3678|Standard 1.5m|23|nos|0.58
70|547|3661|Standard 1.3m|24|nos|0.55
70|548|3662|Ledger 1.8m|200|nos|0.44
70|549|3663|Ledger 1.6m|200|nos|0.4
70|550|3665|Ledger 1.0m|85|nos|0.3
70|551|3026|Ledger 0.9m|70|nos|0.28
70|552|3666|Ledger 0.6m|40|nos|0.24
70|553|3667|Adjustable Base/base jack|20|nos|0.45
70|554|3668|Adjustable "U" Head|50|nos|0.5
70|555|3507|Cantilever Frame 1.5m|40|nos|1.25
70|556|3669|M.D Props 3.20 to 5.0m|100|nos|2.5
70|557|3679|M.D Props 3.20 to 6.0m|5|nos|2.75
70|558|3010|Bracing Tube 4.0m|125|nos|0.8
70|559|3639|Aluminium Beam 4.5m|25|nos|6.75
70|560|3643|Aluminium Beam 2.5m|70|nos|3.75
70|561|3637|Aluminium Beam 3.5m|40|nos|5.25
70|562|3034|Standard 1.00M|170|nos|0.45
90|678|3702|Rental Standard 2.5M|150|pcs|0.81
90|679|3704|Rental Standard 2.0M|30|pcs|0.7
90|680|3733|Rental Standard 1.0M|10|pcs|0.45
90|681|3695|Rental Ledger 1.3M|100|pcs|0.36
90|682|3791|Rental Tube 6.0M|10|pcs|1.2
90|683|3688|Rental Aluminium Beam 1.5M|20|pcs|2.25
90|684|3686|Rental Aluminium Beam 3.5m|15|pcs|5.25"""


def build(path, src="/tmp/claude-0/full.db"):
    R.build(path, src)
    c = sqlite3.connect(path)
    c.execute("UPDATE suppliers SET name=? WHERE id=10", (NAJM,))
    items = R.rows(ITEMS)
    ids = [int(r[0]) for r in items]
    q = ",".join("?" * len(ids))
    for i, code, n, u, t, act, rs, cat in items:
        c.execute("DELETE FROM store_items WHERE code=? AND id<>?", (code, int(i)))
        c.execute("""INSERT OR REPLACE INTO store_items (id, code, name, unit, item_type, active, rental_supplier, category,
                     reorder_level, rental_rate, rental_period, est_price, est_source, notes)
                     VALUES (?,?,?,?,?,?,?,?,0,0,'day',0,'','')""", (int(i), code, n, u, t, int(act), rs, cat))
    mv = R.rows(MOVES)
    c.execute(f"DELETE FROM store_movements WHERE item_id IN ({q})", ids)
    c.execute(f"DELETE FROM store_movements WHERE id IN ({','.join('?' * len(mv))})", [int(r[0]) for r in mv])
    for i, k, it, qty, fr, loc, ow, ref, d, rq, sup in mv:
        supplier = DESARCH if sup == "D" else (NAJM if sup == "X" else "")
        notes = "Against MR-0055" if (sup == "D" and ow == "0") else ""
        c.execute("""INSERT INTO store_movements (id, item_id, kind, qty, from_location, location, request_id, owner_id, reference,
                     moved_on, notes, supplier, unit_cost, incharge, condition) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,'','')""",
                  (int(i), int(it), k, float(qty), fr, loc, int(rq) or None, int(ow) or None, ref, d, notes, supplier))
    for i, no, ref, d, loc in R.rows(NAJM_ORDERS):
        c.execute("DELETE FROM purchase_orders WHERE id=? OR ref=?", (int(i), ref))
        c.execute("""INSERT INTO purchase_orders (id, po_no, ref, order_date, supplier_id, supplier_name, project_location, status,
                     request_line_ids, combined, discount_pct, round_off, tax_pct, zoho_status, zoho_id, terms, cancel_reason)
                     VALUES (?,?,?,?,10,?,?,'issued','',0,0,0,5,'sent','purchaseorder:x','Due on Receipt','')""",
                  (int(i), int(no), ref, d, NAJM, loc))
    for o, i, it, d, qty, u, r in R.rows(LINES):
        c.execute("DELETE FROM purchase_order_lines WHERE id=?", (int(i),))
        c.execute("INSERT INTO purchase_order_lines (id, order_id, item_id, description, qty, unit, rate, tax_pct, cost_to) VALUES (?,?,?,?,?,?,?,5,'')",
                  (int(i), int(o), int(it), d, float(qty), u, float(r)))
    c.commit()
    c.close()


if __name__ == "__main__":
    build(sys.argv[1])
    print("replica written:", sys.argv[1])
