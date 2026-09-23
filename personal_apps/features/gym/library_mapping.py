"""Which library entry each production exercise becomes -- G2's input.

Read off the read-only production audit of 2026-09-23. Both lifters use the
same 21 names (u3's 20 were copied from u1's by shared sessions), so one table
covers both. Owner approval pending: OPEN holds the calls only the owner can
make. Once G2 has run, this module goes.
"""

PRODUCTION_2026_09 = {
    'Bench Press (Dumbbell)': 'dumbbell_bench_press',
    'Biceps Curl (Rotating)': 'dumbbell_curl',
    'Bizeps SZ Kabel': 'cable_curl',
    'Chest Fly (Machine)': 'machine_fly',
    'Chest Press (Machine, Lying)': 'plate_bench_press',
    'Front Raises': 'cable_front_raise_one_arm',
    'Hammer Curl (Dumbbell)': 'dumbbell_hammer_curl',
    'Hammer Curl (Kabel)': 'cable_hammer_curl',
    'Lat Pulldown (Single Arm, Hauptbahnhof)': 'plate_lat_pulldown',
    'Lat Pulldown Kabelzug': 'cable_lat_pulldown',
    'Later Raise Iso': 'plate_lateral_raise',
    'Lateral Raise (Machine, Good)': 'machine_lateral_raise',
    'Military Press': 'barbell_overhead_press',
    'Preacher Curl (Machine, Good)': 'plate_preacher_curl',
    'Preacher Curl Bilateral': 'machine_preacher_curl',
    'Reverse Fly (Machine)': 'machine_rear_delt_fly',
    'Seated Row (Machine, Good)': 'machine_row',
    'T Bar Row (Lying)': 'tbar_row_chest_supported',
    'T Bar Row (Standing)': 'tbar_row',
    'Triceps Extension (Cable, Overhead)': 'cable_overhead_extension',
    'Triceps Pushdown (Cable, EZ Bar)': 'cable_pushdown',
}

OPEN = {
    'Front Raises': 'One arm on the cable (u1 logs it per side with a 5..50 stack), '
                    'both hands on one handle (u3 logs it as a total), or dumbbells?',
    'Military Press': 'Standing or seated?',
    'Bizeps SZ Kabel': 'Cable curl with the SZ attachment: the list has one cable curl, '
                       'with no entry per attachment. Fine?',
}
