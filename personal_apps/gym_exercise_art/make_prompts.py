"""Writes PROMPTS.md: one ChatGPT image prompt per movement of the exercise list.

One picture per movement, not per entry: variants differ in equipment, and their
names already say which. Each prompt draws the variant the lifters log most (the
dev DB's copy of their logs, 2026-09-23) or, where they log none, the list's first
-- `why` says which. A movement without a scene here stops the script, so a
movement added to features/gym/library.py gets its prompt before its picture.

Run from personal_apps:  python gym_exercise_art/make_prompts.py
It rewrites PROMPTS.md and prints which pictures raw/ still lacks.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
sys.path.insert(0, os.path.dirname(HERE))
from features.gym.library import BY_KEY, LIBRARY  # noqa: E402

PICTURE_TYPES = ('.png', '.webp', '.jpg', '.jpeg')

STYLE = (
    'Use the attached reference image for the style and draw a new illustration exactly like '
    'it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, '
    'white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 '
    'background, square 1:1, the whole person and all equipment in frame with generous margin.\n'
    'Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in '
    '#291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the '
    'working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.'
)
SIDES = {
    'both': 'Both sides of the body move together, mirror-symmetric.',
    'one': 'One-sided exercise: only the working side moves as described; the other side stays '
           'relaxed.',
    'split': 'The legs are in the split stance described; the arms mirror each other.',
    'twist': 'The torso turns to one side as described.',
    None: '',
}
RULES = (
    'Natural proportions, hands with five fingers, grips closed around handles and bars.\n'
    'No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, '
    'no mirrors, no other people.'
)

MOST_LOGGED = 'the variant you log most'
FIRST = "the list's first variant"


def scene(english, key, what, view, muscle, check, sides='both', why=FIRST):
    return dict(english=english, key=key, what=what, view=view, muscle=muscle, check=check,
                sides=sides, why=why)


SCENES = {
    'Bankdrücken': scene(
        'dumbbell bench press', 'dumbbell_bench_press',
        "He lies on his back on a flat bench, feet flat on the floor, pressing a dumbbell in each "
        "hand. Middle of the rep: upper arms at about 45 degrees from the torso, forearms vertical, "
        "the dumbbells level with each other a little above chest height.",
        "Side view from slightly above and toward his feet, so the chest, both dumbbells and the "
        "whole bench are visible.",
        'the chest (pectorals)',
        "The bench is flat, a padded top on a sturdy frame; each dumbbell has the same heads on "
        "both ends, the handle in the palm.",
        why=MOST_LOGGED),
    'Schrägbankdrücken': scene(
        'incline barbell bench press', 'barbell_incline_bench_press',
        "He lies on an incline bench with the backrest at about 35 degrees, feet flat on the "
        "floor, pressing a loaded barbell with an overhand grip a little wider than his shoulders. "
        "Middle of the rep: the bar halfway between the upper chest and locked-out arms.",
        "Side view, slightly from the front, so the upper chest, the barbell and the bench with its "
        "uprights are visible.",
        'the upper chest',
        "The backrest is inclined and the seat flat; two uprights with bar hooks stand behind his "
        "head; the bar is straight and level, the same plates on both ends, moving above the upper "
        "chest, not the face."),
    'Negativbankdrücken': scene(
        'decline barbell bench press', 'barbell_decline_bench_press',
        "He lies on a decline bench with his head lower than his hips, knees bent and his lower "
        "legs hooked under the padded foot rollers, pressing a loaded barbell with an overhand grip "
        "a little wider than his shoulders. Middle of the rep: the bar halfway between the lower "
        "chest and locked-out arms.",
        "Side view, so the decline, the leg rollers, the barbell and the uprights at the head end "
        "are visible.",
        'the lower chest',
        "The head end of the bench is the low end and carries the bar uprights; the bar is "
        "straight and level, the same plates on both ends, moving above the lower chest."),
    'Floor Press': scene(
        'barbell floor press', 'barbell_floor_press',
        "He lies on his back directly on the floor, knees bent and feet flat, pressing a loaded "
        "barbell with an overhand grip a little wider than his shoulders. Middle of the rep: the "
        "bar halfway up above his chest, elbows a little above the floor.",
        "Side view from slightly above, so his whole body on the floor and the barbell are visible.",
        'the chest (pectorals)',
        "There is no bench; at the bottom only the backs of the upper arms touch the floor; the bar "
        "is straight and level, the same plates on both ends."),
    'Fliegende': scene(
        'dumbbell fly', 'dumbbell_fly',
        "He lies on his back on a flat bench, feet flat on the floor, a dumbbell in each hand, arms "
        "spread wide to the sides with a slight, fixed bend in the elbows, palms facing each other. "
        "Middle of the rep: the dumbbells halfway between chest level and meeting above the chest, "
        "as if hugging a big barrel.",
        "View from the foot end of the bench and slightly above, so the chest and both open arms "
        "are visible.",
        'the chest (pectorals)',
        "The arms move in a wide arc with the elbow bend unchanged; both dumbbells at the same "
        "height."),
    'Überzüge': scene(
        'dumbbell pullover', 'dumbbell_pullover',
        "He lies on his back along a flat bench, head at one end, feet flat on the floor, holding "
        "one dumbbell with both hands cupped under its upper end. Middle of the rep: arms nearly "
        "straight, the dumbbell lowered in an arc behind his head to about bench height.",
        "Side view, so the arc from above the chest to behind the head reads clearly.",
        'the chest and the lats (the wide muscles on the sides of the back)',
        "One single dumbbell, held upright by both hands; the elbows stay almost straight; the "
        "dumbbell passes behind the head, never over the face."),
    'Brustpresse': scene(
        'seated chest press machine', 'machine_chest_press',
        "He sits upright on a chest press machine with a weight stack, back flat against the "
        "backrest, feet flat on the floor, gripping the two horizontal handles at chest height. "
        "Middle of the rep: arms pushed forward halfway to straight.",
        "Three-quarter front view from slightly to one side, like the reference, so the seat, "
        "backrest, both press arms, the handles and the weight stack are visible.",
        'the chest (pectorals)',
        "The handles start beside the chest and move straight forward; the press arms connect to "
        "the weight stack, which has a selector pin."),
    'Butterfly': scene(
        'machine chest fly (pec deck)', 'machine_fly',
        "He sits upright on a pec deck machine with a weight stack, back flat against the back pad, "
        "feet flat on the floor, upper arms parallel to the floor, elbows slightly bent, hands "
        "gripping the two vertical handles. Middle of the rep: both handles swung halfway toward "
        "each other in front of the chest.",
        "Three-quarter front view from slightly to one side, so the seat, back pad, both swing "
        "arms, both handles and the weight stack are visible.",
        'the chest (pectorals)',
        "Each swing arm pivots on a vertical axis above his shoulder, the arms connect to the "
        "weight stack, the stack has a selector pin, the seat height puts the handles at chest "
        "level, and both handles are the same distance from the chest.",
        why=MOST_LOGGED),
    'Kreuzheben': scene(
        'conventional barbell deadlift', 'barbell_deadlift',
        "He stands with feet hip-width apart, gripping a loaded barbell overhand just outside his "
        "legs, arms straight, back flat. Middle of the lift: the bar has left the floor and is just "
        "above his knees, hips and shoulders rising together.",
        'Side view.',
        'the lower back and the glutes',
        "The back is straight and flat, never rounded; the bar stays against the legs, above the "
        "middle of the feet; full-size plates, the same on both ends."),
    'Rack Pulls': scene(
        'barbell rack pull', 'barbell_rack_pull',
        "He stands inside a power rack; a loaded barbell rests on the rack's safety pins at knee "
        "height. Start of the rep: hips hinged back, back flat, arms straight, gripping the bar "
        "overhand just outside his legs, about to pull it off the pins.",
        "Side view, slightly from the front, so the rack's uprights and the safety pins under the "
        "bar are visible.",
        'the upper and the lower back',
        "The bar rests on two horizontal safety pins that pass through the rack's uprights at knee "
        "height; the back is flat; the same plates on both ends."),
    'Rudern': scene(
        'seated row machine', 'machine_row',
        "He sits on a seated row machine with a weight stack, chest against the chest pad, feet on "
        "the foot rests, gripping the two handles in front of him. Middle of the rep: elbows pulled "
        "halfway back past his sides, shoulder blades squeezing together.",
        "Three-quarter rear view from one side, so his back, the handles and the weight stack are "
        "visible.",
        'the middle back and the lats',
        "The chest stays on the pad; the handles move straight back toward his torso; the weight "
        "stack has a selector pin.",
        why=MOST_LOGGED),
    'Shrugs': scene(
        'barbell shrug', 'barbell_shrug',
        "He stands tall holding a loaded barbell in front of his thighs with an overhand grip, arms "
        "straight. Top of the rep: shoulders pulled straight up toward his ears.",
        'Three-quarter front view.',
        'the upper trapezius (between the neck and the shoulders)',
        "The elbows stay straight; the shoulders move straight up, not rolled; the bar hangs at "
        "the thighs with the same plates on both ends."),
    'Latzug': scene(
        'plate-loaded lat pulldown machine', 'plate_lat_pulldown',
        "He sits on a plate-loaded iso-lateral lat pulldown machine, thighs locked under the knee "
        "pad, gripping the two handles above him. Middle of the rep: elbows pulled halfway down "
        "toward his sides, chest up.",
        "Three-quarter rear view from one side, so his back, both lever arms with their weight "
        "plates and the knee pad are visible.",
        'the lats (the wide muscles on the sides of the upper back)',
        "Two separate lever arms, one per hand, each with a plate horn carrying weight plates; the "
        "handles come down in an arc from above and in front; both sides at the same height.",
        why=MOST_LOGGED),
    'Rückenstrecker': scene(
        'lower back extension machine', 'machine_back_extension',
        "He sits in a lower-back extension machine with a weight stack, hips against the seat, "
        "feet on the footplate, the upper back pad across his shoulder blades, arms crossed over "
        "his chest. Middle of the rep: pushing the pad back, torso halfway from leaning forward to "
        "upright.",
        'Side view, slightly from behind.',
        'the lower back (the muscles along the spine)',
        "The pad sits across the upper back, not the neck; the legs stay still; the weight stack "
        "has a selector pin."),
    'High Row': scene(
        'plate-loaded high row machine', 'plate_high_row',
        "He sits on a plate-loaded iso-lateral high row machine, thighs under the knee pad, facing "
        "the machine, gripping two handles that start high in front of him. Middle of the rep: "
        "pulling the handles down and back toward his shoulders, elbows moving down and back.",
        "Three-quarter rear view from one side, so his back, both lever arms and their weight "
        "plates are visible.",
        'the upper back and the lats',
        "Two separate lever arms, one per hand, each with a plate horn carrying weight plates; the "
        "pull goes down and back on a diagonal; both sides at the same height."),
    'Schulterdrücken': scene(
        'standing barbell overhead press', 'barbell_overhead_press',
        "He stands tall, feet hip-width apart, pressing a loaded barbell overhead with an overhand "
        "grip just wider than his shoulders. Middle of the rep: the bar just above his head, arms "
        "halfway to straight, head moved slightly back out of the bar's path.",
        'Three-quarter front view.',
        'the front shoulders (front deltoids)',
        "He stands, no bench; the bar moves straight up over the middle of the feet, level, the "
        "same plates on both ends; wrists stacked above the elbows.",
        why=MOST_LOGGED),
    'Aufrechtes Rudern': scene(
        'barbell upright row', 'barbell_upright_row',
        "He stands tall holding a barbell in front of his thighs with an overhand grip about "
        "shoulder-width. Middle of the rep: pulling the bar straight up close to his body to chest "
        "height, elbows leading, out to the sides and above the hands.",
        'Three-quarter front view.',
        'the side shoulders (side deltoids) and the upper trapezius',
        "The bar stays close to the body; the elbows are higher than the wrists; the bar is level "
        "with the same plates on both ends."),
    'Arnold Press': scene(
        'dumbbell Arnold press', 'arnold_press',
        "He sits on a bench with an upright backrest, a dumbbell in each hand. Middle of the rep: "
        "the dumbbells at head height, palms turning from facing him to facing forward as he "
        "presses them up.",
        'Three-quarter front view.',
        'the front and side shoulders (deltoids)',
        "The backrest is upright; both dumbbells at the same height and the same turn."),
    'Seitheben': scene(
        'seated lateral raise machine', 'machine_lateral_raise',
        "He sits upright on a lateral raise machine with a weight stack, the outsides of his upper "
        "arms against the two padded levers beside him, hands on their grips. Top of the rep: "
        "upper arms raised out to the sides to shoulder height, lifting the pads.",
        "Front view, slightly from one side, so both raised arms, the pads and the weight stack are "
        "visible.",
        'the side shoulders (side deltoids)',
        "Each padded lever pivots level with his shoulder; the arms rise to the sides, not "
        "forward; both arms at the same height; the weight stack has a selector pin.",
        why=MOST_LOGGED),
    'Frontheben': scene(
        'one-arm cable front raise', 'cable_front_raise_one_arm',
        "He stands with his back to a cable tower, the pulley at its lowest point, holding a "
        "single D-handle in his right hand; the cable runs from the low pulley past his leg to the "
        "hand. Top of the rep: the right arm raised straight forward to shoulder height, elbow "
        "nearly straight; the left arm relaxed at his side.",
        "Three-quarter front view from his right side, so the raised arm, the cable and the cable "
        "tower are visible.",
        'the front of the right shoulder (front deltoid)',
        "The cable runs in a straight line from the low pulley to the handle; only the right arm "
        "rises, forward, not to the side.",
        sides='one', why='your Front Raises (cable, one arm)'),
    'Vorgebeugtes Seitheben': scene(
        'bent-over dumbbell rear delt fly', 'dumbbell_rear_delt_fly',
        "He stands with knees slightly bent and torso hinged forward almost parallel to the floor, "
        "back flat, a dumbbell in each hand. Top of the rep: arms raised out to the sides to "
        "shoulder height, elbows slightly bent, like spreading wings.",
        "Three-quarter rear view from slightly above, so his back and both raised arms are "
        "visible.",
        'the rear shoulders (rear deltoids)',
        "The back stays flat; the arms move out to the sides in an arc; both dumbbells at the same "
        "height."),
    'Face Pulls': scene(
        'cable face pull', 'cable_face_pull',
        "He stands facing a cable tower with the pulley at head height, holding a rope attachment "
        "with both hands. End of the rep: the rope pulled to his face, its two ends split apart "
        "beside his ears, elbows high and out to the sides.",
        "Three-quarter rear view from one side, so his upper back, the rope and the cable tower are "
        "visible.",
        'the rear shoulders (rear deltoids) and the upper back',
        "The rope hangs from one cable at head height; the elbows are at shoulder height; the "
        "cable runs in a straight line from the pulley to the rope."),
    'Reverse Butterfly': scene(
        'reverse pec deck (rear delt machine)', 'machine_rear_delt_fly',
        "He sits facing a pec deck machine with a weight stack, chest against the pad, gripping "
        "the two handles in front of him with straight arms at shoulder height. Middle of the rep: "
        "both arms swung halfway out and back to the sides.",
        "Three-quarter rear view from one side, so his back, both swing arms and the weight stack "
        "are visible.",
        'the rear shoulders (rear deltoids)',
        "He faces the chest pad, the reverse of the chest fly; each swing arm pivots on a vertical "
        "axis in line with his shoulder; both arms at the same angle; the weight stack has a "
        "selector pin.",
        why=MOST_LOGGED),
    'Außenrotation': scene(
        'cable external rotation', 'cable_external_rotation',
        "He stands side-on to a cable tower with the pulley at elbow height, holding a single "
        "D-handle in the hand farther from the tower, that elbow bent 90 degrees and tucked against "
        "his side. Middle of the rep: the forearm rotated outward, away from his belly, like "
        "opening a door, the upper arm still against his body.",
        "Three-quarter view from behind the working shoulder and slightly above, so the forearm's "
        "turn, the cable and the tower are visible.",
        'the rotator cuff at the back of the working shoulder',
        "The elbow stays bent at 90 degrees and pinned to his side; the cable runs level from the "
        "pulley to the handle; only the forearm swings.",
        sides='one'),
    'Schulterpresse': scene(
        'seated shoulder press machine', 'machine_shoulder_press',
        "He sits upright on a shoulder press machine with a weight stack, back against the "
        "backrest, gripping the two handles beside his shoulders. Middle of the rep: pressing the "
        "handles up, arms halfway to straight above his head.",
        "Three-quarter front view from slightly to one side, so the seat, backrest, press arms, "
        "handles and weight stack are visible.",
        'the front shoulders (front deltoids)',
        "The handles start at shoulder height and move up; both at the same height; the weight "
        "stack has a selector pin."),
    'Bizepscurls': scene(
        'dumbbell biceps curl', 'dumbbell_curl',
        "He stands tall with a dumbbell in each hand, palms facing forward, upper arms still at "
        "his sides. Middle of the rep: both forearms curled up halfway, about 90 degrees at the "
        "elbow.",
        'Three-quarter front view.',
        'the biceps',
        "The upper arms stay vertical against the body; only the elbows bend; both dumbbells at "
        "the same height.",
        why=MOST_LOGGED),
    'Scottcurls': scene(
        'preacher curl machine', 'machine_preacher_curl',
        "He sits on a preacher curl machine with a weight stack, the backs of his upper arms on the "
        "sloped arm pad, gripping the handles of the curl lever palms up. Middle of the rep: "
        "forearms curled up halfway, about 90 degrees at the elbow.",
        "Side view, slightly from the front, so the sloped arm pad, the curl lever and the weight "
        "stack are visible.",
        'the biceps',
        "The upper arms lie flat on the sloped pad; the lever's pivot lines up with his elbows; "
        "the weight stack has a selector pin.",
        why=MOST_LOGGED),
    'Hammercurls': scene(
        'dumbbell hammer curl', 'dumbbell_hammer_curl',
        "He stands tall with a dumbbell in each hand, palms facing his body as if holding hammers, "
        "upper arms still at his sides. Middle of the rep: both forearms curled up halfway, thumbs "
        "on top.",
        'Three-quarter front view.',
        'the biceps and the upper forearms',
        "The palms face each other the whole way; the upper arms stay against the body; both "
        "dumbbells at the same height.",
        why=MOST_LOGGED),
    'Konzentrationscurls': scene(
        'dumbbell concentration curl', 'dumbbell_concentration_curl',
        "He sits on the end of a flat bench, legs apart, leaning forward, the back of his right "
        "upper arm braced against the inside of his right thigh, a dumbbell in the right hand; the "
        "left hand rests on the left knee. Middle of the rep: the right forearm curled up halfway "
        "toward the shoulder.",
        'Three-quarter front view from his right side.',
        'the right biceps',
        "The right elbow stays against the inner thigh; only that forearm moves.",
        sides='one'),
    'Schrägbankcurls': scene(
        'incline dumbbell curl', 'dumbbell_incline_curl',
        "He sits leaning back on an incline bench set at about 50 degrees, arms hanging straight "
        "down behind the line of his torso, a dumbbell in each hand, palms forward. Middle of the "
        "rep: both forearms curled up halfway.",
        'Side view, slightly from the front.',
        'the biceps',
        "The upper arms hang straight down behind the torso and stay still; only the elbows bend; "
        "both dumbbells at the same height."),
    'Bayesian Curls': scene(
        'Bayesian cable curl', 'cable_bayesian_curl',
        "He stands facing away from a cable tower, the pulley at its lowest point, left foot "
        "forward, holding a single D-handle in his right hand; the cable pulls his right arm back "
        "behind his body. Middle of the rep: the right forearm curled up halfway while the upper "
        "arm stays angled back behind the torso.",
        "Side view from his right side, so the arm behind the body, the cable and the tower are "
        "visible.",
        'the right biceps',
        "The cable runs in a straight line from the low pulley behind him to the handle; the upper "
        "arm stays behind the torso; only the right forearm moves.",
        sides='one'),
    'French Press': scene(
        'EZ-bar skull crusher', 'ez_skull_crusher',
        "He lies on his back on a flat bench, feet flat on the floor, holding an EZ curl bar (the "
        "zigzag bar) with a narrow overhand grip, upper arms pointing straight up. Middle of the "
        "rep: forearms lowered halfway, the bar just above his forehead, elbows bent about 90 "
        "degrees.",
        'Side view.',
        'the triceps (the backs of the upper arms)',
        "The upper arms stay vertical and still; only the elbows bend; the bar has the zigzag EZ "
        "shape with small plates."),
    'Trizepsstrecken über Kopf': scene(
        'overhead cable triceps extension', 'cable_overhead_extension',
        "He stands facing away from a cable tower in a split stance, leaning slightly forward, "
        "holding a rope attachment with both hands behind his head; the cable comes from a pulley "
        "set high behind him. Middle of the rep: forearms extending forward and up halfway, elbows "
        "pointing forward beside his head.",
        "Side view, so the cable, the rope behind his head and his arms are visible.",
        'the triceps (the backs of the upper arms)',
        "The upper arms stay beside the head, pointing forward; only the elbows open; the cable "
        "runs in a straight line from the pulley to the rope.",
        why=MOST_LOGGED),
    'Trizeps-Kickbacks': scene(
        'dumbbell triceps kickback', 'dumbbell_triceps_kickback',
        "He leans forward with his left knee and left hand on a flat bench, back flat and level, a "
        "dumbbell in his right hand, the right upper arm held level alongside his torso. End of "
        "the rep: the right forearm extended straight back so the whole arm is straight.",
        'Side view from his right side.',
        'the right triceps (the back of the upper arm)',
        "The right upper arm stays level against his side; only the elbow opens; the left hand and "
        "knee rest on the bench.",
        sides='one'),
    'Trizepsdrücken': scene(
        'cable triceps pushdown with a bar', 'cable_pushdown',
        "He stands upright facing a cable tower with the pulley at the top, gripping a short bar "
        "attachment overhand, elbows pinned to his sides. Middle of the rep: forearms pushed down "
        "halfway, from chest height toward his thighs.",
        "Three-quarter rear view from one side, so the backs of his upper arms, the bar, the cable "
        "and the tower are visible.",
        'the triceps (the backs of the upper arms)',
        "The cable runs straight up from the middle of the bar to the top pulley; the elbows stay "
        "at his sides; only the forearms move.",
        why=MOST_LOGGED),
    'Dips': scene(
        'seated dip machine', 'machine_dip',
        "He sits upright on a seated dip machine with a weight stack, back against the backrest, "
        "gripping the two handles beside his hips. Middle of the rep: pushing the handles down, "
        "arms halfway to straight.",
        "Three-quarter rear view from one side, so the backs of his arms, the handles and the "
        "weight stack are visible.",
        'the triceps (the backs of the upper arms)',
        "The handles are at his sides and move down; both at the same height; the weight stack has "
        "a selector pin."),
    'Trizepsstrecken': scene(
        'triceps extension machine', 'machine_triceps_extension',
        "He sits on a triceps extension machine with a weight stack, the backs of his upper arms on "
        "the sloped arm pad, hands on the lever's handles. Middle of the rep: forearms pushed "
        "forward and down halfway, elbows opening.",
        "Side view, slightly from behind, so the arm pad, the lever and the weight stack are "
        "visible.",
        'the triceps (the backs of the upper arms)',
        "The upper arms lie on the pad; the lever's pivot lines up with his elbows; the weight "
        "stack has a selector pin."),
    'Kniebeugen': scene(
        'barbell back squat', 'barbell_squat',
        "He stands with a loaded barbell across his upper back, hands gripping the bar beside his "
        "shoulders, feet shoulder-width apart. Middle of the rep: squatting halfway down, chest "
        "up, knees over the toes.",
        'Three-quarter front view from one side.',
        'the front thighs (quadriceps) and the glutes',
        "The bar rests on the upper back, not the neck; the back stays straight; heels flat; the "
        "bar level with the same plates on both ends."),
    'Frontkniebeugen': scene(
        'barbell front squat', 'barbell_front_squat',
        "He holds a loaded barbell across the front of his shoulders, fingertips under the bar and "
        "elbows pointing forward and high, feet shoulder-width apart. Middle of the rep: squatting "
        "halfway down, torso upright.",
        'Three-quarter front view from one side.',
        'the front thighs (quadriceps)',
        "The bar rests on the front of the shoulders; the elbows stay high; heels flat; the bar "
        "level with the same plates on both ends."),
    'Ausfallschritte': scene(
        'barbell lunge', 'barbell_lunge',
        "He holds a loaded barbell across his upper back in a long lunge: right foot forward and "
        "flat, left foot back on its toes. Bottom of the rep: both knees bent about 90 degrees, the "
        "back knee just above the floor, torso upright.",
        'Side view.',
        'the front thighs (quadriceps) and the glutes',
        "The front knee stays over the front foot; the back knee points down; the bar rests on the "
        "upper back, level, the same plates on both ends.",
        sides='split'),
    'Rumänisches Kreuzheben': scene(
        'barbell Romanian deadlift', 'barbell_romanian_deadlift',
        "He stands holding a loaded barbell in front of his thighs with an overhand grip, knees "
        "slightly bent. Middle of the rep: hips pushed far back and torso hinged forward, back "
        "flat, the bar slid down the thighs to just below the knees.",
        'Side view.',
        'the hamstrings (the backs of the thighs) and the glutes',
        "The back is flat, never rounded; the knee bend stays small and fixed; the bar stays close "
        "to the legs; the same plates on both ends."),
    'Good Mornings': scene(
        'barbell good morning', 'barbell_good_morning',
        "He stands with a loaded barbell across his upper back, hands gripping the bar, knees "
        "slightly bent. Middle of the rep: hips pushed back and torso hinged forward about 45 "
        "degrees, back flat.",
        'Side view.',
        'the hamstrings and the lower back',
        "The bar stays on the upper back; the back is flat; the knee bend is small; the same "
        "plates on both ends."),
    'Goblet Squat': scene(
        'dumbbell goblet squat', 'dumbbell_goblet_squat',
        "He holds one dumbbell upright against his chest, both hands cupped under its top end, "
        "feet a little wider than shoulder-width. Bottom of the rep: squatting deep, elbows inside "
        "the knees, torso upright.",
        'Three-quarter front view.',
        'the front thighs (quadriceps) and the glutes',
        "One single dumbbell held upright at the chest; heels flat; knees over the toes."),
    'Bulgarische Kniebeugen': scene(
        'dumbbell Bulgarian split squat', 'dumbbell_bulgarian_split_squat',
        "He stands in a long split stance, the top of his left foot resting on a flat bench behind "
        "him, a dumbbell in each hand hanging at his sides. Bottom of the rep: the right knee bent "
        "about 90 degrees, the left knee lowered toward the floor, torso upright.",
        'Side view.',
        'the front thigh (quadriceps) and the glute of the front, right leg',
        "Only the top of the rear foot rests on the bench; the front foot is flat and far enough "
        "forward that the knee stays above it; both dumbbells hang straight down.",
        sides='split'),
    'Step-ups': scene(
        'dumbbell step-up', 'dumbbell_step_up',
        "He holds a dumbbell in each hand at his sides and steps up onto a sturdy flat box: right "
        "foot planted flat on top, left leg pushing off the floor. Middle of the rep: the right leg "
        "halfway to straight, lifting his body.",
        'Side view.',
        'the front thigh (quadriceps) and the glute of the right leg',
        "The whole right foot is on the box, which is about knee height; both dumbbells hang "
        "straight down.",
        sides='split'),
    'Beinstrecker': scene(
        'leg extension machine', 'machine_leg_extension',
        "He sits upright on a leg extension machine with a weight stack, back against the "
        "backrest, hands on the side grips, the padded roller in front of his lower shins. Top of "
        "the rep: both legs extended almost straight, lifting the roller.",
        'Side view, slightly from the front.',
        'the front thighs (quadriceps)',
        "The roller sits on the front of the lower shins, above the ankles; the lever's pivot "
        "lines up with his knees; the weight stack has a selector pin."),
    'Beinbeuger': scene(
        'lying leg curl machine', 'machine_leg_curl_lying',
        "He lies face down on a lying leg curl machine with a weight stack, hips on the bench, "
        "hands on the front grips, the padded roller behind his ankles. Middle of the rep: both "
        "heels curled up halfway toward his glutes.",
        'Side view from slightly above.',
        'the hamstrings (the backs of the thighs)',
        "The roller sits on the back of the lower legs, above the heels; the lever's pivot lines up "
        "with his knees; the hips stay down on the bench; the weight stack has a selector pin.",
        why='the lying variant, the clearest picture of the movement'),
    'Beinpresse': scene(
        'seated leg press machine', 'machine_leg_press',
        "He sits in a seated leg press machine with a weight stack, back against the reclined "
        "backrest, hands on the side grips, both feet flat on the footplate at shoulder width. "
        "Middle of the rep: knees bent about 90 degrees, pushing the footplate away.",
        'Side view.',
        'the front thighs (quadriceps) and the glutes',
        "Both feet flat on the footplate; the knees in line with the feet; the weight stack has a "
        "selector pin."),
    'Adduktoren': scene(
        'hip adductor machine', 'machine_adductor',
        "He sits upright on a hip adductor machine with a weight stack, back against the backrest, "
        "the insides of his knees against the two padded leg levers, which start spread wide. "
        "Middle of the rep: squeezing the legs halfway together.",
        'Front view, slightly from above.',
        'the inner thighs (adductors)',
        "The pads press on the inside of the knees; both legs move the same amount; the weight "
        "stack has a selector pin."),
    'Hackenschmidt': scene(
        'plate-loaded hack squat machine', 'plate_hack_squat',
        "He stands on the angled footplate of a plate-loaded hack squat machine, back flat against "
        "the sliding back pad, shoulders under the shoulder pads, hands on the handles. Middle of "
        "the rep: squatting halfway down along the machine's rails.",
        'Side view.',
        'the front thighs (quadriceps)',
        "The sled with back and shoulder pads slides on two diagonal rails; weight plates sit on "
        "the sled's horns on both sides; feet flat on the angled platform."),
    'Pendulum Squat': scene(
        'plate-loaded pendulum squat machine', 'plate_pendulum_squat',
        "He stands on the platform of a pendulum squat machine, back against the back pad, "
        "shoulders under the shoulder pads, hands on the handles; the pads hang from one long lever "
        "that swings in an arc, with weight plates on its horn. Middle of the rep: squatting "
        "halfway down, the lever swinging down and back.",
        'Side view.',
        'the front thighs (quadriceps)',
        "The back and shoulder pads hang from one long lever that pivots at the top rear of the "
        "frame; the plates are loaded on that lever; feet flat on the platform."),
    'Belt Squat': scene(
        'plate-loaded belt squat machine', 'plate_belt_squat',
        "He stands on the raised platform of a belt squat machine, a padded belt around his hips "
        "connected by a strap to the lever below, hands resting on the front handles. Middle of "
        "the rep: squatting halfway down, torso upright.",
        'Side view.',
        'the front thighs (quadriceps) and the glutes',
        "The load hangs from the hip belt, nothing on his shoulders; the strap runs straight down "
        "to the lever, whose plate horn carries weight plates."),
    'Hip Thrust': scene(
        'barbell hip thrust', 'barbell_hip_thrust',
        "His upper back rests across the edge of a flat bench, feet flat on the floor, a padded, "
        "loaded barbell across his hips held in place by both hands. Top of the rep: hips pushed "
        "up so his torso and thighs form a straight line, shins vertical.",
        'Side view.',
        'the glutes',
        "Only the upper back touches the bench; the bar sits on the hip crease with a pad; the "
        "same plates on both ends."),
    'Glute Bridge': scene(
        'barbell glute bridge', 'barbell_glute_bridge',
        "He lies on his back on the floor, knees bent and feet flat, a padded, loaded barbell "
        "across his hips held by both hands. Top of the rep: hips lifted so shoulders, hips and "
        "knees form a straight line.",
        'Side view.',
        'the glutes',
        "The shoulders stay on the floor, no bench; the bar sits on the hip crease with a pad; the "
        "same plates on both ends."),
    'Glute-Kickbacks': scene(
        'cable glute kickback', 'cable_glute_kickback',
        "He stands facing a cable tower with the pulley at its lowest point, holding the frame "
        "with both hands, torso leaning slightly forward, an ankle strap on his right ankle "
        "attached to the cable. Top of the rep: the right leg kicked straight back and up behind "
        "him, the left leg slightly bent.",
        'Side view from his right side.',
        'the right glute',
        "The cable runs in a straight line from the low pulley to the ankle strap; the back stays "
        "flat; only the right leg moves.",
        sides='one'),
    'Abduktoren': scene(
        'hip abductor machine', 'machine_abductor',
        "He sits upright on a hip abductor machine with a weight stack, back against the backrest, "
        "the outsides of his knees against the two padded leg levers, which start together. "
        "Middle of the rep: pushing the legs halfway apart.",
        'Front view, slightly from above.',
        'the outer hips (the upper outer sides of the hips)',
        "The pads press on the outside of the knees; both legs move the same amount; the weight "
        "stack has a selector pin."),
    'Abduktion': scene(
        'standing cable hip abduction', 'cable_abduction',
        "He stands side-on to a cable tower with the pulley at its lowest point, holding the frame "
        "with his left hand, an ankle strap on his right ankle, the one farther from the tower. "
        "Top of the rep: the right leg raised straight out to the side, away from the tower, the "
        "cable crossing in front of his left ankle.",
        'Front view.',
        'the outer right hip',
        "The cable runs in a straight line from the low pulley to the ankle strap; the torso stays "
        "upright; only the right leg moves, sideways.",
        sides='one'),
    'Pull-Through': scene(
        'cable pull-through', 'cable_pull_through',
        "He stands facing away from a cable tower with the pulley at its lowest point, the rope "
        "attachment passing between his legs, gripping the rope with both hands. Middle of the "
        "rep: hips hinged back and torso forward, arms straight between his legs, about to drive "
        "the hips forward.",
        'Side view.',
        'the glutes and the hamstrings',
        "The cable runs from the low pulley behind him between his legs to the rope in his hands; "
        "the back is flat; the arms stay straight."),
    'Swings': scene(
        'kettlebell swing', 'kettlebell_swing',
        "He stands with feet a little wider than shoulder-width, swinging one kettlebell with both "
        "hands. Top of the swing: hips fully extended, standing tall, arms straight out in front "
        "at chest height with the kettlebell floating level.",
        'Side view.',
        'the glutes and the hamstrings',
        "One kettlebell held by its handle with both hands; the arms stay straight; the drive "
        "comes from the hips, not a squat."),
    'Wadenheben': scene(
        'standing calf raise machine', 'machine_standing_calf_raise',
        "He stands in a standing calf raise machine with a weight stack, shoulders under the "
        "padded shoulder yokes, the balls of his feet on the edge of the step block, heels hanging "
        "free. Top of the rep: rising high onto his toes, legs straight.",
        'Side view, slightly from behind.',
        'the calves',
        "Only the balls of the feet are on the block; the knees stay straight; the shoulder pads "
        "connect to the weight stack, which has a selector pin."),
    'Crunches': scene(
        'kneeling cable crunch', 'cable_crunch',
        "He kneels facing a cable tower with the pulley at the top, holding a rope attachment with "
        "both hands beside his head. Middle of the rep: curling his torso down, rounding the spine, "
        "elbows moving toward his thighs.",
        'Side view.',
        'the abs',
        "The hips stay still and high over the knees; the movement is the spine curling; the cable "
        "runs from the top pulley to the rope at his head."),
    'Rumpfrotation': scene(
        'torso rotation machine', 'machine_torso_rotation',
        "He sits on a rotary torso machine with a weight stack, legs held between the knee pads, "
        "chest against the chest pad, hands on the handles. Middle of the rep: rotating his torso "
        "to one side against the resistance, hips staying still.",
        'Three-quarter front view.',
        'the obliques (the sides of the waist)',
        "The lower body stays locked in place; only the torso turns; the weight stack has a "
        "selector pin.",
        sides='twist'),
    'Holzhacker': scene(
        'cable woodchopper', 'cable_woodchopper',
        "He stands side-on to a cable tower with the pulley at the top, feet wide, holding one "
        "D-handle with both hands above the shoulder nearest the tower. Middle of the rep: pulling "
        "the handle diagonally down across his body toward the opposite hip, rotating the torso, "
        "arms nearly straight.",
        'Three-quarter front view.',
        'the obliques and the abs',
        "Both hands on one handle; the cable runs in a straight line from the high pulley to the "
        "hands; the back foot pivots with the turn.",
        sides='twist'),
    'Pallof Press': scene(
        'cable Pallof press', 'cable_pallof_press',
        "He stands side-on to a cable tower with the pulley at chest height, feet shoulder-width "
        "apart, holding one D-handle with both hands at his chest. Middle of the rep: pressing the "
        "handle straight out in front of his chest, arms extended, resisting the cable's pull.",
        'Three-quarter front view.',
        'the abs and the obliques',
        "The cable runs level from the pulley to his hands; the torso stays square to the front, "
        "not turned; both hands on one handle.",
        sides=None),
    'Seitbeugen': scene(
        'dumbbell side bend', 'dumbbell_side_bend',
        "He stands tall holding one dumbbell in his right hand at his side, the left hand behind "
        "his head. Middle of the rep: bending sideways at the waist to the right, the dumbbell "
        "sliding down the outside of the right leg toward the knee.",
        'Front view.',
        'the obliques (the sides of the waist)',
        "One dumbbell only; the torso bends straight to the side, not forward; the hips stay "
        "still.",
        sides='one'),
    'Handgelenkcurls': scene(
        'barbell wrist curl', 'barbell_wrist_curl',
        "He sits on the end of a flat bench, forearms resting on his thighs, palms up, wrists just "
        "past his knees, holding a light barbell. Top of the rep: wrists curled up, lifting the "
        "bar with the hands alone.",
        "Side view, slightly from the front, close enough that the wrists and forearms read "
        "clearly.",
        'the forearms',
        "The forearms stay flat on the thighs; only the wrists move; the bar is light with small "
        "plates."),
    'Reverse Curls': scene(
        'EZ-bar reverse curl', 'ez_reverse_curl',
        "He stands tall holding an EZ curl bar (the zigzag bar) with an overhand grip, palms "
        "facing down, upper arms still at his sides. Middle of the rep: forearms curled up "
        "halfway, knuckles facing forward and up.",
        'Three-quarter front view.',
        'the tops of the forearms and the biceps',
        "The grip is overhand, palms down; the upper arms stay against the body; the bar has the "
        "zigzag EZ shape with small plates."),
}

HEADER = """# Gym exercise pictures: ChatGPT prompts

One picture per movement, {count} in all; the variants of a movement share its
picture. Written by `make_prompts.py` from `features/gym/library.py`. Rerun it
after the list changes (`python gym_exercise_art/make_prompts.py`, from
`personal_apps`); it also reports which pictures are still missing.

## How to do it

1. In ChatGPT, attach `raw/reference.webp` (the approved Butterfly) and paste one
   prompt from below.
2. Check the picture before saving it: the right machine or equipment, both sides
   even unless the prompt says one-sided, the orange on the right muscle, no text
   anywhere. If something is off, tell ChatGPT what to fix, or regenerate.
3. Download it and save it under its name from the list, in
   `{raw}`
   PNG, WEBP and JPG all work: keep the name, the ending may differ. Git ignores
   this folder, so nothing gets committed by accident.
4. Any order, over as many days as you like. Staying in one chat keeps the style
   closest; in a new chat, attach the reference again.
5. When all {count} are saved, tell Claude: the names get checked, the pictures
   shrunk to small web files, and the app work starts with a mockup round.

Each picture shows the variant you log most, or the list's first variant where you
log none. To show another variant, change the prompt's Exercise and Scene lines
before pasting it.

`butterfly.webp` is already saved: it is the reference itself. Its two handles are
not quite the same distance from the chest; redo 08 if that bothers you.

## Checklist

| # | Movement | Save as | Picture shows | Saved |
|---|---|---|---|---|
"""


def slug(movement):
    text = movement.lower()
    for umlaut, spelled in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        text = text.replace(umlaut, spelled)
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def prompt(s):
    lines = [STYLE, '', f'Exercise: {s["english"]}.', f'Scene: {s["what"]}',
             f'View: {s["view"]}', f'Highlight in #C2410C: {s["muscle"]}.']
    if SIDES[s['sides']]:
        lines.append(SIDES[s['sides']])
    lines += [f'Must be mechanically correct: {s["check"]}', RULES]
    return '\n'.join(lines)


def saved(name):
    return any(os.path.exists(os.path.join(RAW, name + ext)) for ext in PICTURE_TYPES)


def main():
    movements = list(dict.fromkeys(entry.movement for entry in LIBRARY))
    unmatched = sorted(set(movements) ^ set(SCENES))
    if unmatched:
        sys.exit(f'movements without a scene, or scenes without a movement: {unmatched}')
    for movement, s in SCENES.items():
        assert BY_KEY[s['key']].movement == movement, (movement, s['key'])
    files = {movement: slug(movement) for movement in movements}
    assert len(set(files.values())) == len(files), 'two movements share a file name'

    have = {movement for movement in movements if saved(files[movement])}
    out = [HEADER.format(count=len(movements), raw=RAW).rstrip('\n')]
    for number, movement in enumerate(movements, 1):
        s = SCENES[movement]
        out.append(f'| {number:02} | {movement} | `{files[movement]}.png` | '
                   f'{BY_KEY[s["key"]].name}: {s["why"]} | {"yes" if movement in have else ""} |')
    out += ['', '## Prompts']
    for number, movement in enumerate(movements, 1):
        s = SCENES[movement]
        out += ['', f'### {number:02} · {movement} → `{files[movement]}.png`', '',
                f'Shows {BY_KEY[s["key"]].name}: {s["why"]}.', '', '```text', prompt(s), '```']
    with open(os.path.join(HERE, 'PROMPTS.md'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(out) + '\n')

    print(f'{len(have)} of {len(movements)} saved in raw/')
    missing = [files[movement] for movement in movements if movement not in have]
    if missing:
        print('missing:', ' '.join(missing))


if __name__ == '__main__':
    main()
