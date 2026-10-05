import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---- browser helpers ---------------------------------------------------------
# M43 gave the browser Fusion's folder anatomy (Origin / Bodies / Sketches /
# Construction), so feature nodes are no longer direct children of the root.
# Tests should walk the tree instead of hard-coding positions.

def tree_texts(win):
    """Every browser node label, depth-first."""
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            out.append(ch.text(0))
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out


def feature_rows(win):
    """The feature nodes in document order, wherever the folders put them."""
    from PySide6.QtCore import Qt
    out = []

    def walk(node):
        for i in range(node.childCount()):
            ch = node.child(i)
            role = ch.data(0, Qt.UserRole)
            if role and role[0] == "feature":
                out.append(ch)
            walk(ch)
    walk(win.rail.tree.invisibleRootItem())
    return out
