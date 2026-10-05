import os

# Hard isolation for the desktop session (user's Hyprland must never see a
# test window or XWayland wake-up): force Qt offscreen, drop the gtk3
# platform theme (it reaches for X settings/XWayland from inside Qt
# processes — that was thrashing the compositor), and remove every display
# handle so even an accidental fallback (wayland client, GLX/X11, GTK)
# fails inside the test process instead of reaching the session.
# The real app is launched separately with its normal environment.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("QT_QPA_PLATFORMTHEME", None)
os.environ.pop("WAYLAND_DISPLAY", None)
os.environ.pop("DISPLAY", None)


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
