# Spatial Network Evidence Lab

An offline validator for a synthetic movement network. It checks coordinate ranges, unique graph identifiers, missing endpoints, route edge continuity and a straight-line lower bound for each declared edge distance. A canonical SHA-256 digest binds the fixture to the output; input row order does not change the digest.

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B audit.py samples/network.json
```

This is an AI-built portfolio exercise using invented map points and routes. It does not use employer or customer location data, perform route optimization, prove real map accuracy, or represent past GIS work.
