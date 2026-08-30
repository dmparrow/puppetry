# Four-actor Blender test scene

This helper builds a repeatable four-character scene for exercising actor identity and retargeting.

The default characters are:

1. Warrior
2. Wizard
3. Ranger
4. Monk

They are sourced from the Quaternius **RPG Character Pack**, which contains six rigged, animated and textured fantasy characters and is published under CC0.

Official pack page:

https://quaternius.com/packs/rpgcharacters.html

## 1. Get the asset pack

Try the helper first:

```bash
cd dualcam-mocap
chmod +x blender_test/fetch_quaternius_rpg.sh
./blender_test/fetch_quaternius_rpg.sh
```

Quaternius may route the download through a browser/itch-style page rather than expose a stable direct ZIP URL. If automatic discovery cannot produce a direct ZIP, download the pack from the official page and rerun:

```bash
./blender_test/fetch_quaternius_rpg.sh \
  assets/quaternius-rpg \
  ~/Downloads/RPGCharacterPack.zip
```

The extracted assets are intentionally ignored by Git.

## 2. Build the scene

With Blender available on PATH:

```bash
blender --background \
  --python blender_test/setup_quaternius_scene.py \
  -- \
  --pack-dir assets/quaternius-rpg/extracted \
  --output mocap_four_actor_test.blend
```

The builder recursively searches FBX/glTF/GLB files for the requested character names, imports the four characters, clears bundled animation, lays them out in a row and saves the `.blend`.

Each detected armature receives custom properties:

```text
mocap_actor_id = 1..4
mocap_label = Warrior/Wizard/Ranger/Monk
mocap_test_actor = true
```

Those properties are deliberately aligned with the multi-actor mocap plan so the Blender add-on can bind incoming actor IDs to an existing character rig without changing the test scene.

## Alternate characters

If filenames differ, or you want another four from the pack:

```bash
blender --background \
  --python blender_test/setup_quaternius_scene.py \
  -- \
  --pack-dir assets/quaternius-rpg/extracted \
  --actors Warrior Wizard Monk Cleric \
  --output mocap_four_actor_test.blend
```

## Expected scene

```text
Actor 1 — Warrior
Actor 2 — Wizard
Actor 3 — Ranger
Actor 4 — Monk
```

Each character is parented below a `MOCAP_TEST_ACTOR_<id>_<name>` root object and its main armature is renamed to `MOCAP_ACTOR_<id>_<name>_ARMATURE`.

The next multi-actor Blender patch should use `mocap_actor_id` directly when selecting which incoming skeleton drives each armature.
