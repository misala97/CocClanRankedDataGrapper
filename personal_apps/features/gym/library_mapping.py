"""Which library entry each production exercise becomes -- G2's input.

Read off the read-only production audit of 2026-09-23 and approved by the
owner the same day. Both lifters use the same 21 names (u3's 20 were copied
from u1's by shared sessions), so one table covers both. The owner's calls:
Front Raises were done one-handed on the cable, the Military Press standing
with the Langhantel, and the cable curl needs no entry per attachment. Once
G2 has run, this module goes.
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

# Words in the old names that marked one gym's machine, not the exercise.
# The list drops them (one entry per kind of machine), so search need not
# find them.
GYM_MARKERS = ('Good', 'Hauptbahnhof')
