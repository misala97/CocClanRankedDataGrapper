# Empty on purpose. Its mere presence at coc_stats/ makes pytest treat this
# directory as the rootdir and adds it to sys.path (default rootdir/importmode
# behaviour), so `from features...` / `from services...` imports inside
# tests/ resolve exactly as they do when the app itself runs with cwd=coc_stats.
