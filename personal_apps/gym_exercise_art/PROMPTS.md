# Gym exercise pictures: ChatGPT prompts

One picture per movement, 67 in all; the variants of a movement share its
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
   `C:\Users\michi\Desktop\CodingStuff\personal_apps\gym_exercise_art\raw`
   PNG, WEBP and JPG all work: keep the name, the ending may differ. Git ignores
   this folder, so nothing gets committed by accident.
4. Any order, over as many days as you like. Staying in one chat keeps the style
   closest; in a new chat, attach the reference again.
5. When all 67 are saved, tell Claude: the names get checked, the pictures
   shrunk to small web files, and the app work starts with a mockup round.

Each picture shows the variant you log most, or the list's first variant where you
log none. To show another variant, change the prompt's Exercise and Scene lines
before pasting it.

`butterfly.webp` is already saved: it is the reference itself. Its two handles are
not quite the same distance from the chest; redo 08 if that bothers you.

## Checklist

| # | Movement | Save as | Picture shows | Saved |
|---|---|---|---|---|
| 01 | Bankdrücken | `bankdruecken.png` | Bankdrücken (Kurzhantel): the variant you log most |  |
| 02 | Schrägbankdrücken | `schraegbankdruecken.png` | Schrägbankdrücken (Langhantel): the list's first variant |  |
| 03 | Negativbankdrücken | `negativbankdruecken.png` | Negativbankdrücken (Langhantel): the list's first variant |  |
| 04 | Floor Press | `floor-press.png` | Floor Press (Langhantel): the list's first variant |  |
| 05 | Fliegende | `fliegende.png` | Fliegende (Kurzhantel): the list's first variant |  |
| 06 | Überzüge | `ueberzuege.png` | Überzüge (Kurzhantel): the list's first variant |  |
| 07 | Brustpresse | `brustpresse.png` | Brustpresse (Maschine): the list's first variant |  |
| 08 | Butterfly | `butterfly.png` | Butterfly (Maschine): the variant you log most | yes |
| 09 | Kreuzheben | `kreuzheben.png` | Kreuzheben (Langhantel): the list's first variant |  |
| 10 | Rack Pulls | `rack-pulls.png` | Rack Pulls (Langhantel): the list's first variant |  |
| 11 | Rudern | `rudern.png` | Rudern (Maschine): the variant you log most |  |
| 12 | Shrugs | `shrugs.png` | Shrugs (Langhantel): the list's first variant |  |
| 13 | Latzug | `latzug.png` | Latzug (Maschine, Scheiben): the variant you log most |  |
| 14 | Rückenstrecker | `rueckenstrecker.png` | Rückenstrecker (Maschine): the list's first variant |  |
| 15 | High Row | `high-row.png` | High Row (Maschine, Scheiben): the list's first variant |  |
| 16 | Schulterdrücken | `schulterdruecken.png` | Schulterdrücken (Langhantel, stehend): the variant you log most |  |
| 17 | Aufrechtes Rudern | `aufrechtes-rudern.png` | Aufrechtes Rudern (Langhantel): the list's first variant |  |
| 18 | Arnold Press | `arnold-press.png` | Arnold Press (Kurzhantel): the list's first variant |  |
| 19 | Seitheben | `seitheben.png` | Seitheben (Maschine): the variant you log most |  |
| 20 | Frontheben | `frontheben.png` | Frontheben (Kabel, einarmig): your Front Raises (cable, one arm) |  |
| 21 | Vorgebeugtes Seitheben | `vorgebeugtes-seitheben.png` | Vorgebeugtes Seitheben (Kurzhantel): the list's first variant |  |
| 22 | Face Pulls | `face-pulls.png` | Face Pulls (Kabel): the list's first variant |  |
| 23 | Reverse Butterfly | `reverse-butterfly.png` | Reverse Butterfly (Maschine): the variant you log most |  |
| 24 | Außenrotation | `aussenrotation.png` | Außenrotation (Kabel): the list's first variant |  |
| 25 | Schulterpresse | `schulterpresse.png` | Schulterpresse (Maschine): the list's first variant |  |
| 26 | Bizepscurls | `bizepscurls.png` | Bizepscurls (Kurzhantel): the variant you log most |  |
| 27 | Scottcurls | `scottcurls.png` | Scottcurls (Maschine): the variant you log most |  |
| 28 | Hammercurls | `hammercurls.png` | Hammercurls (Kurzhantel): the variant you log most |  |
| 29 | Konzentrationscurls | `konzentrationscurls.png` | Konzentrationscurls (Kurzhantel): the list's first variant |  |
| 30 | Schrägbankcurls | `schraegbankcurls.png` | Schrägbankcurls (Kurzhantel): the list's first variant |  |
| 31 | Bayesian Curls | `bayesian-curls.png` | Bayesian Curls (Kabel): the list's first variant |  |
| 32 | French Press | `french-press.png` | French Press (SZ-Stange): the list's first variant |  |
| 33 | Trizepsstrecken über Kopf | `trizepsstrecken-ueber-kopf.png` | Trizepsstrecken über Kopf (Kabel): the variant you log most |  |
| 34 | Trizeps-Kickbacks | `trizeps-kickbacks.png` | Trizeps-Kickbacks (Kurzhantel): the list's first variant |  |
| 35 | Trizepsdrücken | `trizepsdruecken.png` | Trizepsdrücken (Kabel, Stange): the variant you log most |  |
| 36 | Dips | `dips.png` | Dips (Maschine): the list's first variant |  |
| 37 | Trizepsstrecken | `trizepsstrecken.png` | Trizepsstrecken (Maschine): the list's first variant |  |
| 38 | Kniebeugen | `kniebeugen.png` | Kniebeugen (Langhantel): the list's first variant |  |
| 39 | Frontkniebeugen | `frontkniebeugen.png` | Frontkniebeugen (Langhantel): the list's first variant |  |
| 40 | Ausfallschritte | `ausfallschritte.png` | Ausfallschritte (Langhantel): the list's first variant |  |
| 41 | Rumänisches Kreuzheben | `rumaenisches-kreuzheben.png` | Rumänisches Kreuzheben (Langhantel): the list's first variant |  |
| 42 | Good Mornings | `good-mornings.png` | Good Mornings (Langhantel): the list's first variant |  |
| 43 | Goblet Squat | `goblet-squat.png` | Goblet Squat (Kurzhantel): the list's first variant |  |
| 44 | Bulgarische Kniebeugen | `bulgarische-kniebeugen.png` | Bulgarische Kniebeugen (Kurzhantel): the list's first variant |  |
| 45 | Step-ups | `step-ups.png` | Step-ups (Kurzhantel): the list's first variant |  |
| 46 | Beinstrecker | `beinstrecker.png` | Beinstrecker (Maschine): the list's first variant |  |
| 47 | Beinbeuger | `beinbeuger.png` | Beinbeuger (Maschine, liegend): the lying variant, the clearest picture of the movement |  |
| 48 | Beinpresse | `beinpresse.png` | Beinpresse (Maschine): the list's first variant |  |
| 49 | Adduktoren | `adduktoren.png` | Adduktoren (Maschine): the list's first variant |  |
| 50 | Hackenschmidt | `hackenschmidt.png` | Hackenschmidt (Maschine, Scheiben): the list's first variant |  |
| 51 | Pendulum Squat | `pendulum-squat.png` | Pendulum Squat (Maschine, Scheiben): the list's first variant |  |
| 52 | Belt Squat | `belt-squat.png` | Belt Squat (Maschine, Scheiben): the list's first variant |  |
| 53 | Hip Thrust | `hip-thrust.png` | Hip Thrust (Langhantel): the list's first variant |  |
| 54 | Glute Bridge | `glute-bridge.png` | Glute Bridge (Langhantel): the list's first variant |  |
| 55 | Glute-Kickbacks | `glute-kickbacks.png` | Glute-Kickbacks (Kabel): the list's first variant |  |
| 56 | Abduktoren | `abduktoren.png` | Abduktoren (Maschine): the list's first variant |  |
| 57 | Abduktion | `abduktion.png` | Abduktion (Kabel): the list's first variant |  |
| 58 | Pull-Through | `pull-through.png` | Pull-Through (Kabel): the list's first variant |  |
| 59 | Swings | `swings.png` | Swings (Kettlebell): the list's first variant |  |
| 60 | Wadenheben | `wadenheben.png` | Wadenheben (Maschine, stehend): the list's first variant |  |
| 61 | Crunches | `crunches.png` | Crunches (Kabel): the list's first variant |  |
| 62 | Rumpfrotation | `rumpfrotation.png` | Rumpfrotation (Maschine): the list's first variant |  |
| 63 | Holzhacker | `holzhacker.png` | Holzhacker (Kabel): the list's first variant |  |
| 64 | Pallof Press | `pallof-press.png` | Pallof Press (Kabel): the list's first variant |  |
| 65 | Seitbeugen | `seitbeugen.png` | Seitbeugen (Kurzhantel): the list's first variant |  |
| 66 | Handgelenkcurls | `handgelenkcurls.png` | Handgelenkcurls (Langhantel): the list's first variant |  |
| 67 | Reverse Curls | `reverse-curls.png` | Reverse Curls (SZ-Stange): the list's first variant |  |

## Prompts

### 01 · Bankdrücken → `bankdruecken.png`

Shows Bankdrücken (Kurzhantel): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell bench press.
Scene: He lies on his back on a flat bench, feet flat on the floor, pressing a dumbbell in each hand. Middle of the rep: upper arms at about 45 degrees from the torso, forearms vertical, the dumbbells level with each other a little above chest height.
View: Side view from slightly above and toward his feet, so the chest, both dumbbells and the whole bench are visible.
Highlight in #C2410C: the chest (pectorals).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bench is flat, a padded top on a sturdy frame; each dumbbell has the same heads on both ends, the handle in the palm.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 02 · Schrägbankdrücken → `schraegbankdruecken.png`

Shows Schrägbankdrücken (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: incline barbell bench press.
Scene: He lies on an incline bench with the backrest at about 35 degrees, feet flat on the floor, pressing a loaded barbell with an overhand grip a little wider than his shoulders. Middle of the rep: the bar halfway between the upper chest and locked-out arms.
View: Side view, slightly from the front, so the upper chest, the barbell and the bench with its uprights are visible.
Highlight in #C2410C: the upper chest.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The backrest is inclined and the seat flat; two uprights with bar hooks stand behind his head; the bar is straight and level, the same plates on both ends, moving above the upper chest, not the face.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 03 · Negativbankdrücken → `negativbankdruecken.png`

Shows Negativbankdrücken (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: decline barbell bench press.
Scene: He lies on a decline bench with his head lower than his hips, knees bent and his lower legs hooked under the padded foot rollers, pressing a loaded barbell with an overhand grip a little wider than his shoulders. Middle of the rep: the bar halfway between the lower chest and locked-out arms.
View: Side view, so the decline, the leg rollers, the barbell and the uprights at the head end are visible.
Highlight in #C2410C: the lower chest.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The head end of the bench is the low end and carries the bar uprights; the bar is straight and level, the same plates on both ends, moving above the lower chest.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 04 · Floor Press → `floor-press.png`

Shows Floor Press (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell floor press.
Scene: He lies on his back directly on the floor, knees bent and feet flat, pressing a loaded barbell with an overhand grip a little wider than his shoulders. Middle of the rep: the bar halfway up above his chest, elbows a little above the floor.
View: Side view from slightly above, so his whole body on the floor and the barbell are visible.
Highlight in #C2410C: the chest (pectorals).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: There is no bench; at the bottom only the backs of the upper arms touch the floor; the bar is straight and level, the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 05 · Fliegende → `fliegende.png`

Shows Fliegende (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell fly.
Scene: He lies on his back on a flat bench, feet flat on the floor, a dumbbell in each hand, arms spread wide to the sides with a slight, fixed bend in the elbows, palms facing each other. Middle of the rep: the dumbbells halfway between chest level and meeting above the chest, as if hugging a big barrel.
View: View from the foot end of the bench and slightly above, so the chest and both open arms are visible.
Highlight in #C2410C: the chest (pectorals).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The arms move in a wide arc with the elbow bend unchanged; both dumbbells at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 06 · Überzüge → `ueberzuege.png`

Shows Überzüge (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell pullover.
Scene: He lies on his back along a flat bench, head at one end, feet flat on the floor, holding one dumbbell with both hands cupped under its upper end. Middle of the rep: arms nearly straight, the dumbbell lowered in an arc behind his head to about bench height.
View: Side view, so the arc from above the chest to behind the head reads clearly.
Highlight in #C2410C: the chest and the lats (the wide muscles on the sides of the back).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: One single dumbbell, held upright by both hands; the elbows stay almost straight; the dumbbell passes behind the head, never over the face.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 07 · Brustpresse → `brustpresse.png`

Shows Brustpresse (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated chest press machine.
Scene: He sits upright on a chest press machine with a weight stack, back flat against the backrest, feet flat on the floor, gripping the two horizontal handles at chest height. Middle of the rep: arms pushed forward halfway to straight.
View: Three-quarter front view from slightly to one side, like the reference, so the seat, backrest, both press arms, the handles and the weight stack are visible.
Highlight in #C2410C: the chest (pectorals).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The handles start beside the chest and move straight forward; the press arms connect to the weight stack, which has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 08 · Butterfly → `butterfly.png`

Shows Butterfly (Maschine): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: machine chest fly (pec deck).
Scene: He sits upright on a pec deck machine with a weight stack, back flat against the back pad, feet flat on the floor, upper arms parallel to the floor, elbows slightly bent, hands gripping the two vertical handles. Middle of the rep: both handles swung halfway toward each other in front of the chest.
View: Three-quarter front view from slightly to one side, so the seat, back pad, both swing arms, both handles and the weight stack are visible.
Highlight in #C2410C: the chest (pectorals).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Each swing arm pivots on a vertical axis above his shoulder, the arms connect to the weight stack, the stack has a selector pin, the seat height puts the handles at chest level, and both handles are the same distance from the chest.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 09 · Kreuzheben → `kreuzheben.png`

Shows Kreuzheben (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: conventional barbell deadlift.
Scene: He stands with feet hip-width apart, gripping a loaded barbell overhand just outside his legs, arms straight, back flat. Middle of the lift: the bar has left the floor and is just above his knees, hips and shoulders rising together.
View: Side view.
Highlight in #C2410C: the lower back and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The back is straight and flat, never rounded; the bar stays against the legs, above the middle of the feet; full-size plates, the same on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 10 · Rack Pulls → `rack-pulls.png`

Shows Rack Pulls (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell rack pull.
Scene: He stands inside a power rack; a loaded barbell rests on the rack's safety pins at knee height. Start of the rep: hips hinged back, back flat, arms straight, gripping the bar overhand just outside his legs, about to pull it off the pins.
View: Side view, slightly from the front, so the rack's uprights and the safety pins under the bar are visible.
Highlight in #C2410C: the upper and the lower back.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bar rests on two horizontal safety pins that pass through the rack's uprights at knee height; the back is flat; the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 11 · Rudern → `rudern.png`

Shows Rudern (Maschine): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated row machine.
Scene: He sits on a seated row machine with a weight stack, chest against the chest pad, feet on the foot rests, gripping the two handles in front of him. Middle of the rep: elbows pulled halfway back past his sides, shoulder blades squeezing together.
View: Three-quarter rear view from one side, so his back, the handles and the weight stack are visible.
Highlight in #C2410C: the middle back and the lats.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The chest stays on the pad; the handles move straight back toward his torso; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 12 · Shrugs → `shrugs.png`

Shows Shrugs (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell shrug.
Scene: He stands tall holding a loaded barbell in front of his thighs with an overhand grip, arms straight. Top of the rep: shoulders pulled straight up toward his ears.
View: Three-quarter front view.
Highlight in #C2410C: the upper trapezius (between the neck and the shoulders).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The elbows stay straight; the shoulders move straight up, not rolled; the bar hangs at the thighs with the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 13 · Latzug → `latzug.png`

Shows Latzug (Maschine, Scheiben): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: plate-loaded lat pulldown machine.
Scene: He sits on a plate-loaded iso-lateral lat pulldown machine, thighs locked under the knee pad, gripping the two handles above him. Middle of the rep: elbows pulled halfway down toward his sides, chest up.
View: Three-quarter rear view from one side, so his back, both lever arms with their weight plates and the knee pad are visible.
Highlight in #C2410C: the lats (the wide muscles on the sides of the upper back).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Two separate lever arms, one per hand, each with a plate horn carrying weight plates; the handles come down in an arc from above and in front; both sides at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 14 · Rückenstrecker → `rueckenstrecker.png`

Shows Rückenstrecker (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: lower back extension machine.
Scene: He sits in a lower-back extension machine with a weight stack, hips against the seat, feet on the footplate, the upper back pad across his shoulder blades, arms crossed over his chest. Middle of the rep: pushing the pad back, torso halfway from leaning forward to upright.
View: Side view, slightly from behind.
Highlight in #C2410C: the lower back (the muscles along the spine).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The pad sits across the upper back, not the neck; the legs stay still; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 15 · High Row → `high-row.png`

Shows High Row (Maschine, Scheiben): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: plate-loaded high row machine.
Scene: He sits on a plate-loaded iso-lateral high row machine, thighs under the knee pad, facing the machine, gripping two handles that start high in front of him. Middle of the rep: pulling the handles down and back toward his shoulders, elbows moving down and back.
View: Three-quarter rear view from one side, so his back, both lever arms and their weight plates are visible.
Highlight in #C2410C: the upper back and the lats.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Two separate lever arms, one per hand, each with a plate horn carrying weight plates; the pull goes down and back on a diagonal; both sides at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 16 · Schulterdrücken → `schulterdruecken.png`

Shows Schulterdrücken (Langhantel, stehend): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: standing barbell overhead press.
Scene: He stands tall, feet hip-width apart, pressing a loaded barbell overhead with an overhand grip just wider than his shoulders. Middle of the rep: the bar just above his head, arms halfway to straight, head moved slightly back out of the bar's path.
View: Three-quarter front view.
Highlight in #C2410C: the front shoulders (front deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: He stands, no bench; the bar moves straight up over the middle of the feet, level, the same plates on both ends; wrists stacked above the elbows.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 17 · Aufrechtes Rudern → `aufrechtes-rudern.png`

Shows Aufrechtes Rudern (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell upright row.
Scene: He stands tall holding a barbell in front of his thighs with an overhand grip about shoulder-width. Middle of the rep: pulling the bar straight up close to his body to chest height, elbows leading, out to the sides and above the hands.
View: Three-quarter front view.
Highlight in #C2410C: the side shoulders (side deltoids) and the upper trapezius.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bar stays close to the body; the elbows are higher than the wrists; the bar is level with the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 18 · Arnold Press → `arnold-press.png`

Shows Arnold Press (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell Arnold press.
Scene: He sits on a bench with an upright backrest, a dumbbell in each hand. Middle of the rep: the dumbbells at head height, palms turning from facing him to facing forward as he presses them up.
View: Three-quarter front view.
Highlight in #C2410C: the front and side shoulders (deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The backrest is upright; both dumbbells at the same height and the same turn.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 19 · Seitheben → `seitheben.png`

Shows Seitheben (Maschine): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated lateral raise machine.
Scene: He sits upright on a lateral raise machine with a weight stack, the outsides of his upper arms against the two padded levers beside him, hands on their grips. Top of the rep: upper arms raised out to the sides to shoulder height, lifting the pads.
View: Front view, slightly from one side, so both raised arms, the pads and the weight stack are visible.
Highlight in #C2410C: the side shoulders (side deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Each padded lever pivots level with his shoulder; the arms rise to the sides, not forward; both arms at the same height; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 20 · Frontheben → `frontheben.png`

Shows Frontheben (Kabel, einarmig): your Front Raises (cable, one arm).

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: one-arm cable front raise.
Scene: He stands with his back to a cable tower, the pulley at its lowest point, holding a single D-handle in his right hand; the cable runs from the low pulley past his leg to the hand. Top of the rep: the right arm raised straight forward to shoulder height, elbow nearly straight; the left arm relaxed at his side.
View: Three-quarter front view from his right side, so the raised arm, the cable and the cable tower are visible.
Highlight in #C2410C: the front of the right shoulder (front deltoid).
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The cable runs in a straight line from the low pulley to the handle; only the right arm rises, forward, not to the side.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 21 · Vorgebeugtes Seitheben → `vorgebeugtes-seitheben.png`

Shows Vorgebeugtes Seitheben (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: bent-over dumbbell rear delt fly.
Scene: He stands with knees slightly bent and torso hinged forward almost parallel to the floor, back flat, a dumbbell in each hand. Top of the rep: arms raised out to the sides to shoulder height, elbows slightly bent, like spreading wings.
View: Three-quarter rear view from slightly above, so his back and both raised arms are visible.
Highlight in #C2410C: the rear shoulders (rear deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The back stays flat; the arms move out to the sides in an arc; both dumbbells at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 22 · Face Pulls → `face-pulls.png`

Shows Face Pulls (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable face pull.
Scene: He stands facing a cable tower with the pulley at head height, holding a rope attachment with both hands. End of the rep: the rope pulled to his face, its two ends split apart beside his ears, elbows high and out to the sides.
View: Three-quarter rear view from one side, so his upper back, the rope and the cable tower are visible.
Highlight in #C2410C: the rear shoulders (rear deltoids) and the upper back.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The rope hangs from one cable at head height; the elbows are at shoulder height; the cable runs in a straight line from the pulley to the rope.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 23 · Reverse Butterfly → `reverse-butterfly.png`

Shows Reverse Butterfly (Maschine): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: reverse pec deck (rear delt machine).
Scene: He sits facing a pec deck machine with a weight stack, chest against the pad, gripping the two handles in front of him with straight arms at shoulder height. Middle of the rep: both arms swung halfway out and back to the sides.
View: Three-quarter rear view from one side, so his back, both swing arms and the weight stack are visible.
Highlight in #C2410C: the rear shoulders (rear deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: He faces the chest pad, the reverse of the chest fly; each swing arm pivots on a vertical axis in line with his shoulder; both arms at the same angle; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 24 · Außenrotation → `aussenrotation.png`

Shows Außenrotation (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable external rotation.
Scene: He stands side-on to a cable tower with the pulley at elbow height, holding a single D-handle in the hand farther from the tower, that elbow bent 90 degrees and tucked against his side. Middle of the rep: the forearm rotated outward, away from his belly, like opening a door, the upper arm still against his body.
View: Three-quarter view from behind the working shoulder and slightly above, so the forearm's turn, the cable and the tower are visible.
Highlight in #C2410C: the rotator cuff at the back of the working shoulder.
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The elbow stays bent at 90 degrees and pinned to his side; the cable runs level from the pulley to the handle; only the forearm swings.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 25 · Schulterpresse → `schulterpresse.png`

Shows Schulterpresse (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated shoulder press machine.
Scene: He sits upright on a shoulder press machine with a weight stack, back against the backrest, gripping the two handles beside his shoulders. Middle of the rep: pressing the handles up, arms halfway to straight above his head.
View: Three-quarter front view from slightly to one side, so the seat, backrest, press arms, handles and weight stack are visible.
Highlight in #C2410C: the front shoulders (front deltoids).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The handles start at shoulder height and move up; both at the same height; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 26 · Bizepscurls → `bizepscurls.png`

Shows Bizepscurls (Kurzhantel): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell biceps curl.
Scene: He stands tall with a dumbbell in each hand, palms facing forward, upper arms still at his sides. Middle of the rep: both forearms curled up halfway, about 90 degrees at the elbow.
View: Three-quarter front view.
Highlight in #C2410C: the biceps.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms stay vertical against the body; only the elbows bend; both dumbbells at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 27 · Scottcurls → `scottcurls.png`

Shows Scottcurls (Maschine): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: preacher curl machine.
Scene: He sits on a preacher curl machine with a weight stack, the backs of his upper arms on the sloped arm pad, gripping the handles of the curl lever palms up. Middle of the rep: forearms curled up halfway, about 90 degrees at the elbow.
View: Side view, slightly from the front, so the sloped arm pad, the curl lever and the weight stack are visible.
Highlight in #C2410C: the biceps.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms lie flat on the sloped pad; the lever's pivot lines up with his elbows; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 28 · Hammercurls → `hammercurls.png`

Shows Hammercurls (Kurzhantel): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell hammer curl.
Scene: He stands tall with a dumbbell in each hand, palms facing his body as if holding hammers, upper arms still at his sides. Middle of the rep: both forearms curled up halfway, thumbs on top.
View: Three-quarter front view.
Highlight in #C2410C: the biceps and the upper forearms.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The palms face each other the whole way; the upper arms stay against the body; both dumbbells at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 29 · Konzentrationscurls → `konzentrationscurls.png`

Shows Konzentrationscurls (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell concentration curl.
Scene: He sits on the end of a flat bench, legs apart, leaning forward, the back of his right upper arm braced against the inside of his right thigh, a dumbbell in the right hand; the left hand rests on the left knee. Middle of the rep: the right forearm curled up halfway toward the shoulder.
View: Three-quarter front view from his right side.
Highlight in #C2410C: the right biceps.
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The right elbow stays against the inner thigh; only that forearm moves.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 30 · Schrägbankcurls → `schraegbankcurls.png`

Shows Schrägbankcurls (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: incline dumbbell curl.
Scene: He sits leaning back on an incline bench set at about 50 degrees, arms hanging straight down behind the line of his torso, a dumbbell in each hand, palms forward. Middle of the rep: both forearms curled up halfway.
View: Side view, slightly from the front.
Highlight in #C2410C: the biceps.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms hang straight down behind the torso and stay still; only the elbows bend; both dumbbells at the same height.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 31 · Bayesian Curls → `bayesian-curls.png`

Shows Bayesian Curls (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: Bayesian cable curl.
Scene: He stands facing away from a cable tower, the pulley at its lowest point, left foot forward, holding a single D-handle in his right hand; the cable pulls his right arm back behind his body. Middle of the rep: the right forearm curled up halfway while the upper arm stays angled back behind the torso.
View: Side view from his right side, so the arm behind the body, the cable and the tower are visible.
Highlight in #C2410C: the right biceps.
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The cable runs in a straight line from the low pulley behind him to the handle; the upper arm stays behind the torso; only the right forearm moves.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 32 · French Press → `french-press.png`

Shows French Press (SZ-Stange): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: EZ-bar skull crusher.
Scene: He lies on his back on a flat bench, feet flat on the floor, holding an EZ curl bar (the zigzag bar) with a narrow overhand grip, upper arms pointing straight up. Middle of the rep: forearms lowered halfway, the bar just above his forehead, elbows bent about 90 degrees.
View: Side view.
Highlight in #C2410C: the triceps (the backs of the upper arms).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms stay vertical and still; only the elbows bend; the bar has the zigzag EZ shape with small plates.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 33 · Trizepsstrecken über Kopf → `trizepsstrecken-ueber-kopf.png`

Shows Trizepsstrecken über Kopf (Kabel): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: overhead cable triceps extension.
Scene: He stands facing away from a cable tower in a split stance, leaning slightly forward, holding a rope attachment with both hands behind his head; the cable comes from a pulley set high behind him. Middle of the rep: forearms extending forward and up halfway, elbows pointing forward beside his head.
View: Side view, so the cable, the rope behind his head and his arms are visible.
Highlight in #C2410C: the triceps (the backs of the upper arms).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms stay beside the head, pointing forward; only the elbows open; the cable runs in a straight line from the pulley to the rope.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 34 · Trizeps-Kickbacks → `trizeps-kickbacks.png`

Shows Trizeps-Kickbacks (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell triceps kickback.
Scene: He leans forward with his left knee and left hand on a flat bench, back flat and level, a dumbbell in his right hand, the right upper arm held level alongside his torso. End of the rep: the right forearm extended straight back so the whole arm is straight.
View: Side view from his right side.
Highlight in #C2410C: the right triceps (the back of the upper arm).
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The right upper arm stays level against his side; only the elbow opens; the left hand and knee rest on the bench.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 35 · Trizepsdrücken → `trizepsdruecken.png`

Shows Trizepsdrücken (Kabel, Stange): the variant you log most.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable triceps pushdown with a bar.
Scene: He stands upright facing a cable tower with the pulley at the top, gripping a short bar attachment overhand, elbows pinned to his sides. Middle of the rep: forearms pushed down halfway, from chest height toward his thighs.
View: Three-quarter rear view from one side, so the backs of his upper arms, the bar, the cable and the tower are visible.
Highlight in #C2410C: the triceps (the backs of the upper arms).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The cable runs straight up from the middle of the bar to the top pulley; the elbows stay at his sides; only the forearms move.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 36 · Dips → `dips.png`

Shows Dips (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated dip machine.
Scene: He sits upright on a seated dip machine with a weight stack, back against the backrest, gripping the two handles beside his hips. Middle of the rep: pushing the handles down, arms halfway to straight.
View: Three-quarter rear view from one side, so the backs of his arms, the handles and the weight stack are visible.
Highlight in #C2410C: the triceps (the backs of the upper arms).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The handles are at his sides and move down; both at the same height; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 37 · Trizepsstrecken → `trizepsstrecken.png`

Shows Trizepsstrecken (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: triceps extension machine.
Scene: He sits on a triceps extension machine with a weight stack, the backs of his upper arms on the sloped arm pad, hands on the lever's handles. Middle of the rep: forearms pushed forward and down halfway, elbows opening.
View: Side view, slightly from behind, so the arm pad, the lever and the weight stack are visible.
Highlight in #C2410C: the triceps (the backs of the upper arms).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The upper arms lie on the pad; the lever's pivot lines up with his elbows; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 38 · Kniebeugen → `kniebeugen.png`

Shows Kniebeugen (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell back squat.
Scene: He stands with a loaded barbell across his upper back, hands gripping the bar beside his shoulders, feet shoulder-width apart. Middle of the rep: squatting halfway down, chest up, knees over the toes.
View: Three-quarter front view from one side.
Highlight in #C2410C: the front thighs (quadriceps) and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bar rests on the upper back, not the neck; the back stays straight; heels flat; the bar level with the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 39 · Frontkniebeugen → `frontkniebeugen.png`

Shows Frontkniebeugen (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell front squat.
Scene: He holds a loaded barbell across the front of his shoulders, fingertips under the bar and elbows pointing forward and high, feet shoulder-width apart. Middle of the rep: squatting halfway down, torso upright.
View: Three-quarter front view from one side.
Highlight in #C2410C: the front thighs (quadriceps).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bar rests on the front of the shoulders; the elbows stay high; heels flat; the bar level with the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 40 · Ausfallschritte → `ausfallschritte.png`

Shows Ausfallschritte (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell lunge.
Scene: He holds a loaded barbell across his upper back in a long lunge: right foot forward and flat, left foot back on its toes. Bottom of the rep: both knees bent about 90 degrees, the back knee just above the floor, torso upright.
View: Side view.
Highlight in #C2410C: the front thighs (quadriceps) and the glutes.
The legs are in the split stance described; the arms mirror each other.
Must be mechanically correct: The front knee stays over the front foot; the back knee points down; the bar rests on the upper back, level, the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 41 · Rumänisches Kreuzheben → `rumaenisches-kreuzheben.png`

Shows Rumänisches Kreuzheben (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell Romanian deadlift.
Scene: He stands holding a loaded barbell in front of his thighs with an overhand grip, knees slightly bent. Middle of the rep: hips pushed far back and torso hinged forward, back flat, the bar slid down the thighs to just below the knees.
View: Side view.
Highlight in #C2410C: the hamstrings (the backs of the thighs) and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The back is flat, never rounded; the knee bend stays small and fixed; the bar stays close to the legs; the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 42 · Good Mornings → `good-mornings.png`

Shows Good Mornings (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell good morning.
Scene: He stands with a loaded barbell across his upper back, hands gripping the bar, knees slightly bent. Middle of the rep: hips pushed back and torso hinged forward about 45 degrees, back flat.
View: Side view.
Highlight in #C2410C: the hamstrings and the lower back.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The bar stays on the upper back; the back is flat; the knee bend is small; the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 43 · Goblet Squat → `goblet-squat.png`

Shows Goblet Squat (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell goblet squat.
Scene: He holds one dumbbell upright against his chest, both hands cupped under its top end, feet a little wider than shoulder-width. Bottom of the rep: squatting deep, elbows inside the knees, torso upright.
View: Three-quarter front view.
Highlight in #C2410C: the front thighs (quadriceps) and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: One single dumbbell held upright at the chest; heels flat; knees over the toes.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 44 · Bulgarische Kniebeugen → `bulgarische-kniebeugen.png`

Shows Bulgarische Kniebeugen (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell Bulgarian split squat.
Scene: He stands in a long split stance, the top of his left foot resting on a flat bench behind him, a dumbbell in each hand hanging at his sides. Bottom of the rep: the right knee bent about 90 degrees, the left knee lowered toward the floor, torso upright.
View: Side view.
Highlight in #C2410C: the front thigh (quadriceps) and the glute of the front, right leg.
The legs are in the split stance described; the arms mirror each other.
Must be mechanically correct: Only the top of the rear foot rests on the bench; the front foot is flat and far enough forward that the knee stays above it; both dumbbells hang straight down.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 45 · Step-ups → `step-ups.png`

Shows Step-ups (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell step-up.
Scene: He holds a dumbbell in each hand at his sides and steps up onto a sturdy flat box: right foot planted flat on top, left leg pushing off the floor. Middle of the rep: the right leg halfway to straight, lifting his body.
View: Side view.
Highlight in #C2410C: the front thigh (quadriceps) and the glute of the right leg.
The legs are in the split stance described; the arms mirror each other.
Must be mechanically correct: The whole right foot is on the box, which is about knee height; both dumbbells hang straight down.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 46 · Beinstrecker → `beinstrecker.png`

Shows Beinstrecker (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: leg extension machine.
Scene: He sits upright on a leg extension machine with a weight stack, back against the backrest, hands on the side grips, the padded roller in front of his lower shins. Top of the rep: both legs extended almost straight, lifting the roller.
View: Side view, slightly from the front.
Highlight in #C2410C: the front thighs (quadriceps).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The roller sits on the front of the lower shins, above the ankles; the lever's pivot lines up with his knees; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 47 · Beinbeuger → `beinbeuger.png`

Shows Beinbeuger (Maschine, liegend): the lying variant, the clearest picture of the movement.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: lying leg curl machine.
Scene: He lies face down on a lying leg curl machine with a weight stack, hips on the bench, hands on the front grips, the padded roller behind his ankles. Middle of the rep: both heels curled up halfway toward his glutes.
View: Side view from slightly above.
Highlight in #C2410C: the hamstrings (the backs of the thighs).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The roller sits on the back of the lower legs, above the heels; the lever's pivot lines up with his knees; the hips stay down on the bench; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 48 · Beinpresse → `beinpresse.png`

Shows Beinpresse (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: seated leg press machine.
Scene: He sits in a seated leg press machine with a weight stack, back against the reclined backrest, hands on the side grips, both feet flat on the footplate at shoulder width. Middle of the rep: knees bent about 90 degrees, pushing the footplate away.
View: Side view.
Highlight in #C2410C: the front thighs (quadriceps) and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Both feet flat on the footplate; the knees in line with the feet; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 49 · Adduktoren → `adduktoren.png`

Shows Adduktoren (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: hip adductor machine.
Scene: He sits upright on a hip adductor machine with a weight stack, back against the backrest, the insides of his knees against the two padded leg levers, which start spread wide. Middle of the rep: squeezing the legs halfway together.
View: Front view, slightly from above.
Highlight in #C2410C: the inner thighs (adductors).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The pads press on the inside of the knees; both legs move the same amount; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 50 · Hackenschmidt → `hackenschmidt.png`

Shows Hackenschmidt (Maschine, Scheiben): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: plate-loaded hack squat machine.
Scene: He stands on the angled footplate of a plate-loaded hack squat machine, back flat against the sliding back pad, shoulders under the shoulder pads, hands on the handles. Middle of the rep: squatting halfway down along the machine's rails.
View: Side view.
Highlight in #C2410C: the front thighs (quadriceps).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The sled with back and shoulder pads slides on two diagonal rails; weight plates sit on the sled's horns on both sides; feet flat on the angled platform.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 51 · Pendulum Squat → `pendulum-squat.png`

Shows Pendulum Squat (Maschine, Scheiben): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: plate-loaded pendulum squat machine.
Scene: He stands on the platform of a pendulum squat machine, back against the back pad, shoulders under the shoulder pads, hands on the handles; the pads hang from one long lever that swings in an arc, with weight plates on its horn. Middle of the rep: squatting halfway down, the lever swinging down and back.
View: Side view.
Highlight in #C2410C: the front thighs (quadriceps).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The back and shoulder pads hang from one long lever that pivots at the top rear of the frame; the plates are loaded on that lever; feet flat on the platform.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 52 · Belt Squat → `belt-squat.png`

Shows Belt Squat (Maschine, Scheiben): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: plate-loaded belt squat machine.
Scene: He stands on the raised platform of a belt squat machine, a padded belt around his hips connected by a strap to the lever below, hands resting on the front handles. Middle of the rep: squatting halfway down, torso upright.
View: Side view.
Highlight in #C2410C: the front thighs (quadriceps) and the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The load hangs from the hip belt, nothing on his shoulders; the strap runs straight down to the lever, whose plate horn carries weight plates.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 53 · Hip Thrust → `hip-thrust.png`

Shows Hip Thrust (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell hip thrust.
Scene: His upper back rests across the edge of a flat bench, feet flat on the floor, a padded, loaded barbell across his hips held in place by both hands. Top of the rep: hips pushed up so his torso and thighs form a straight line, shins vertical.
View: Side view.
Highlight in #C2410C: the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Only the upper back touches the bench; the bar sits on the hip crease with a pad; the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 54 · Glute Bridge → `glute-bridge.png`

Shows Glute Bridge (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell glute bridge.
Scene: He lies on his back on the floor, knees bent and feet flat, a padded, loaded barbell across his hips held by both hands. Top of the rep: hips lifted so shoulders, hips and knees form a straight line.
View: Side view.
Highlight in #C2410C: the glutes.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The shoulders stay on the floor, no bench; the bar sits on the hip crease with a pad; the same plates on both ends.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 55 · Glute-Kickbacks → `glute-kickbacks.png`

Shows Glute-Kickbacks (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable glute kickback.
Scene: He stands facing a cable tower with the pulley at its lowest point, holding the frame with both hands, torso leaning slightly forward, an ankle strap on his right ankle attached to the cable. Top of the rep: the right leg kicked straight back and up behind him, the left leg slightly bent.
View: Side view from his right side.
Highlight in #C2410C: the right glute.
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The cable runs in a straight line from the low pulley to the ankle strap; the back stays flat; only the right leg moves.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 56 · Abduktoren → `abduktoren.png`

Shows Abduktoren (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: hip abductor machine.
Scene: He sits upright on a hip abductor machine with a weight stack, back against the backrest, the outsides of his knees against the two padded leg levers, which start together. Middle of the rep: pushing the legs halfway apart.
View: Front view, slightly from above.
Highlight in #C2410C: the outer hips (the upper outer sides of the hips).
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The pads press on the outside of the knees; both legs move the same amount; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 57 · Abduktion → `abduktion.png`

Shows Abduktion (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: standing cable hip abduction.
Scene: He stands side-on to a cable tower with the pulley at its lowest point, holding the frame with his left hand, an ankle strap on his right ankle, the one farther from the tower. Top of the rep: the right leg raised straight out to the side, away from the tower, the cable crossing in front of his left ankle.
View: Front view.
Highlight in #C2410C: the outer right hip.
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: The cable runs in a straight line from the low pulley to the ankle strap; the torso stays upright; only the right leg moves, sideways.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 58 · Pull-Through → `pull-through.png`

Shows Pull-Through (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable pull-through.
Scene: He stands facing away from a cable tower with the pulley at its lowest point, the rope attachment passing between his legs, gripping the rope with both hands. Middle of the rep: hips hinged back and torso forward, arms straight between his legs, about to drive the hips forward.
View: Side view.
Highlight in #C2410C: the glutes and the hamstrings.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The cable runs from the low pulley behind him between his legs to the rope in his hands; the back is flat; the arms stay straight.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 59 · Swings → `swings.png`

Shows Swings (Kettlebell): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: kettlebell swing.
Scene: He stands with feet a little wider than shoulder-width, swinging one kettlebell with both hands. Top of the swing: hips fully extended, standing tall, arms straight out in front at chest height with the kettlebell floating level.
View: Side view.
Highlight in #C2410C: the glutes and the hamstrings.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: One kettlebell held by its handle with both hands; the arms stay straight; the drive comes from the hips, not a squat.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 60 · Wadenheben → `wadenheben.png`

Shows Wadenheben (Maschine, stehend): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: standing calf raise machine.
Scene: He stands in a standing calf raise machine with a weight stack, shoulders under the padded shoulder yokes, the balls of his feet on the edge of the step block, heels hanging free. Top of the rep: rising high onto his toes, legs straight.
View: Side view, slightly from behind.
Highlight in #C2410C: the calves.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: Only the balls of the feet are on the block; the knees stay straight; the shoulder pads connect to the weight stack, which has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 61 · Crunches → `crunches.png`

Shows Crunches (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: kneeling cable crunch.
Scene: He kneels facing a cable tower with the pulley at the top, holding a rope attachment with both hands beside his head. Middle of the rep: curling his torso down, rounding the spine, elbows moving toward his thighs.
View: Side view.
Highlight in #C2410C: the abs.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The hips stay still and high over the knees; the movement is the spine curling; the cable runs from the top pulley to the rope at his head.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 62 · Rumpfrotation → `rumpfrotation.png`

Shows Rumpfrotation (Maschine): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: torso rotation machine.
Scene: He sits on a rotary torso machine with a weight stack, legs held between the knee pads, chest against the chest pad, hands on the handles. Middle of the rep: rotating his torso to one side against the resistance, hips staying still.
View: Three-quarter front view.
Highlight in #C2410C: the obliques (the sides of the waist).
The torso turns to one side as described.
Must be mechanically correct: The lower body stays locked in place; only the torso turns; the weight stack has a selector pin.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 63 · Holzhacker → `holzhacker.png`

Shows Holzhacker (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable woodchopper.
Scene: He stands side-on to a cable tower with the pulley at the top, feet wide, holding one D-handle with both hands above the shoulder nearest the tower. Middle of the rep: pulling the handle diagonally down across his body toward the opposite hip, rotating the torso, arms nearly straight.
View: Three-quarter front view.
Highlight in #C2410C: the obliques and the abs.
The torso turns to one side as described.
Must be mechanically correct: Both hands on one handle; the cable runs in a straight line from the high pulley to the hands; the back foot pivots with the turn.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 64 · Pallof Press → `pallof-press.png`

Shows Pallof Press (Kabel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: cable Pallof press.
Scene: He stands side-on to a cable tower with the pulley at chest height, feet shoulder-width apart, holding one D-handle with both hands at his chest. Middle of the rep: pressing the handle straight out in front of his chest, arms extended, resisting the cable's pull.
View: Three-quarter front view.
Highlight in #C2410C: the abs and the obliques.
Must be mechanically correct: The cable runs level from the pulley to his hands; the torso stays square to the front, not turned; both hands on one handle.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 65 · Seitbeugen → `seitbeugen.png`

Shows Seitbeugen (Kurzhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: dumbbell side bend.
Scene: He stands tall holding one dumbbell in his right hand at his side, the left hand behind his head. Middle of the rep: bending sideways at the waist to the right, the dumbbell sliding down the outside of the right leg toward the knee.
View: Front view.
Highlight in #C2410C: the obliques (the sides of the waist).
One-sided exercise: only the working side moves as described; the other side stays relaxed.
Must be mechanically correct: One dumbbell only; the torso bends straight to the side, not forward; the hips stay still.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 66 · Handgelenkcurls → `handgelenkcurls.png`

Shows Handgelenkcurls (Langhantel): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: barbell wrist curl.
Scene: He sits on the end of a flat bench, forearms resting on his thighs, palms up, wrists just past his knees, holding a light barbell. Top of the rep: wrists curled up, lifting the bar with the hands alone.
View: Side view, slightly from the front, close enough that the wrists and forearms read clearly.
Highlight in #C2410C: the forearms.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The forearms stay flat on the thighs; only the wrists move; the bar is light with small plates.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```

### 67 · Reverse Curls → `reverse-curls.png`

Shows Reverse Curls (SZ-Stange): the list's first variant.

```text
Use the attached reference image for the style and draw a new illustration exactly like it: the same flat vector look, outlines and soft shading, the same lifter (short dark hair, white t-shirt, lavender shorts, white socks, lavender sneakers), the same solid #EEE5F3 background, square 1:1, the whole person and all equipment in frame with generous margin.
Colours only: equipment (machines, benches, bars, dumbbells, plates, cables, handles) in #291238 and #634674; skin and clothes in muted neutrals (#DACAE3, #C2ABCF, white); the working muscle highlighted in #C2410C as a simple flat shape over the body or shirt.

Exercise: EZ-bar reverse curl.
Scene: He stands tall holding an EZ curl bar (the zigzag bar) with an overhand grip, palms facing down, upper arms still at his sides. Middle of the rep: forearms curled up halfway, knuckles facing forward and up.
View: Three-quarter front view.
Highlight in #C2410C: the tops of the forearms and the biceps.
Both sides of the body move together, mirror-symmetric.
Must be mechanically correct: The grip is overhand, palms down; the upper arms stay against the body; the bar has the zigzag EZ shape with small plates.
Natural proportions, hands with five fingers, grips closed around handles and bars.
No text, no numbers, no labels, no logos, no watermark, no arrows, no gym background, no mirrors, no other people.
```
