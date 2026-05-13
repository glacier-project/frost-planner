import matplotlib

# Force a non-interactive backend so the visualization tests can run on
# headless environments (CI, tox sandboxes, Docker images) where no
# display server is available.
matplotlib.use("Agg", force=True)
