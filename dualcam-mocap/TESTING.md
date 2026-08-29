# Testing

Core geometry test:

```bash
cd dualcam-mocap
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q tests/test_triangulation.py
```

The synthetic test uses a known stereo baseline and projects a known 3D point into both cameras, then verifies the triangulator reconstructs the original point.

Hardware smoke-test order:

1. Run stereo calibration and confirm a plausible physical baseline.
2. Start GPU server and verify ports 8765/8766 bind.
3. Start camera client and watch capture skew / send FPS.
4. Confirm GPU server reports tracked point count and processing time.
5. Connect Blender and verify `MOCAP_*` debug empties.
6. Create `MOCAP_DRIVER`.
7. Bind the production armature only after the driver skeleton is correct.
