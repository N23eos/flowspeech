"""Shared AppKit building blocks styled to the macOS HIG.

The settings and onboarding windows are built from these so they read like
native System Settings panes: system fonts and semantic label colors, Auto
Layout via NSStackView/NSGridView (no hand-placed rectangles), grouped NSBox
sections, standard push buttons, and SF Symbol status glyphs.

Everything here is main-thread AppKit; callers already are.
"""

import objc
from Foundation import NSObject

from AppKit import (
    NSBox,
    NSButton,
    NSColor,
    NSFont,
    NSGridView,
    NSImage,
    NSImageView,
    NSLayoutConstraint,
    NSStackView,
    NSTextField,
    NSView,
)

# Auto Layout / stack enums — imported when available, with the documented
# numeric fallbacks so a slim PyObjC build still works.
try:
    from AppKit import (
        NSGridCellPlacementTrailing,
        NSLayoutAttributeLeading,
        NSUserInterfaceLayoutOrientationHorizontal,
        NSUserInterfaceLayoutOrientationVertical,
    )
except ImportError:  # pragma: no cover - depends on the PyObjC build
    NSUserInterfaceLayoutOrientationHorizontal = 0
    NSUserInterfaceLayoutOrientationVertical = 1
    NSLayoutAttributeLeading = 5
    NSGridCellPlacementTrailing = 3

# System Settings-ish rhythm.
MARGIN = 20
SPACING = 10
SECTION_SPACING = 18

# NSFont weights (constants live in AppKit but names vary across builds).
_WEIGHT_SEMIBOLD = 0.3
_WEIGHT_REGULAR = 0.0


# --- Text ------------------------------------------------------------------

def label(text: str) -> NSTextField:
    """A plain, selectable body label in the primary label color."""
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.systemFontOfSize_(13))
    field.setTextColor_(NSColor.labelColor())
    field.setSelectable_(True)
    return field


def title(text: str) -> NSTextField:
    """A semibold section/heading label."""
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.systemFontOfSize_weight_(15, _WEIGHT_SEMIBOLD))
    field.setTextColor_(NSColor.labelColor())
    return field


def secondary(text: str, *, size: float = 11) -> NSTextField:
    """Muted helper text (captions, hints) in the secondary label color."""
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.systemFontOfSize_(size))
    field.setTextColor_(NSColor.secondaryLabelColor())
    return field


def wrapping(field: NSTextField, max_width: float) -> NSTextField:
    """Let a label wrap to multiple lines within `max_width`."""
    field.setLineBreakMode_(0)  # NSLineBreakByWordWrapping
    field.cell().setWraps_(True)
    field.setPreferredMaxLayoutWidth_(max_width)
    field.setMaximumNumberOfLines_(0)
    return field


# --- Controls --------------------------------------------------------------

_targets = []  # keep ObjC action targets alive (controls hold weak refs)


class _Target(NSObject):
    def initWithHandler_(self, fn):
        self = objc.super(_Target, self).init()
        if self is None:
            return None
        self._fn = fn
        return self

    def fire_(self, sender):
        self._fn(sender)


def on_action(control, handler) -> None:
    """Wire a Python callable to any NSControl's action."""
    target = _Target.alloc().initWithHandler_(handler)
    control.setTarget_(target)
    control.setAction_("fire:")
    _targets.append(target)


def push_button(text: str, handler=None, *, default: bool = False) -> NSButton:
    """A standard rounded push button (the default one gets Return + accent)."""
    button = NSButton.buttonWithTitle_target_action_(text, None, None)
    button.setBezelStyle_(1)  # NSBezelStyleRounded
    if default:
        button.setKeyEquivalent_("\r")
    if handler is not None:
        on_action(button, handler)
    return button


def symbol_view(name: str, *, color=None, point_size: float = 15) -> NSImageView:
    """An NSImageView showing an SF Symbol (falls back to an empty view)."""
    view = NSImageView.alloc().init()
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is not None:
        view.setImage_(image)
    view.setContentTintColor_(color or NSColor.secondaryLabelColor())
    view.setTranslatesAutoresizingMaskIntoConstraints_(False)
    NSLayoutConstraint.activateConstraints_([
        view.widthAnchor().constraintEqualToConstant_(point_size + 6),
        view.heightAnchor().constraintEqualToConstant_(point_size + 6),
    ])
    return view


# --- Layout ----------------------------------------------------------------

def vstack(views, *, spacing: float = SPACING, align=None, fill: bool = False) -> NSStackView:
    """Vertical stack. With fill=True every child is stretched to the stack's
    width (relative, so it adapts to whatever container it's pinned into)."""
    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setAlignment_(align if align is not None else NSLayoutAttributeLeading)
    stack.setSpacing_(spacing)
    stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
    for view in views:
        stack.addArrangedSubview_(view)
        if fill:
            NSLayoutConstraint.activateConstraints_([
                view.widthAnchor().constraintEqualToAnchor_(stack.widthAnchor()),
            ])
    return stack


def hstack(views, *, spacing: float = SPACING) -> NSStackView:
    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    stack.setSpacing_(spacing)
    stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
    for view in views:
        stack.addArrangedSubview_(view)
    return stack


def form(rows) -> NSGridView:
    """A two-column form: right-aligned labels, left-aligned controls.

    `rows` is a list of (label_text_or_view, control_view). Strings become
    secondary-colored labels, matching a native settings form.
    """
    grid_rows = []
    for left, right in rows:
        left_view = secondary(left, size=13) if isinstance(left, str) else left
        grid_rows.append([left_view, right])
    grid = NSGridView.gridViewWithViews_(grid_rows)
    grid.setRowSpacing_(10)
    grid.setColumnSpacing_(12)
    grid.columnAtIndex_(0).setXPlacement_(NSGridCellPlacementTrailing)
    grid.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return grid


def section(title_text: str, body: NSView) -> NSStackView:
    """A titled group: a semibold heading above its content, tightly spaced."""
    return vstack([title(title_text), body], spacing=8)


def spacer() -> NSView:
    """A flexible gap for horizontal stacks — pushes what follows to the edge."""
    view = NSView.alloc().init()
    view.setTranslatesAutoresizingMaskIntoConstraints_(False)
    view.setContentHuggingPriority_forOrientation_(1, 0)  # low, horizontal
    return view


def divider() -> NSBox:
    """A thin horizontal separator, like NSBox separator style."""
    box = NSBox.alloc().init()
    box.setBoxType_(2)  # NSBoxSeparator
    box.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return box


def fill_width(view: NSView, container: NSView) -> None:
    """Constrain `view` to span the container's width (for stack children)."""
    NSLayoutConstraint.activateConstraints_([
        view.leadingAnchor().constraintEqualToAnchor_(container.leadingAnchor()),
        view.trailingAnchor().constraintEqualToAnchor_(container.trailingAnchor()),
    ])


def pin_header_body(container: NSView, header: NSView, body: NSView,
                    inset: float = MARGIN) -> None:
    """Header pinned to the top; body fills the rest to the bottom edge."""
    for view in (header, body):
        container.addSubview_(view)
        view.setTranslatesAutoresizingMaskIntoConstraints_(False)
    NSLayoutConstraint.activateConstraints_([
        header.topAnchor().constraintEqualToAnchor_constant_(
            container.topAnchor(), inset),
        header.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.trailingAnchor().constraintEqualToAnchor_constant_(
            header.trailingAnchor(), inset),
        body.topAnchor().constraintEqualToAnchor_constant_(
            header.bottomAnchor(), SPACING),
        body.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.trailingAnchor().constraintEqualToAnchor_constant_(
            body.trailingAnchor(), inset),
        container.bottomAnchor().constraintEqualToAnchor_constant_(
            body.bottomAnchor(), inset),
    ])


def pin_column(container: NSView, header: NSView, body: NSView, footer: NSView,
               inset: float = MARGIN) -> None:
    """Header at top, footer at bottom, body stretching between them."""
    for view in (header, body, footer):
        container.addSubview_(view)
        view.setTranslatesAutoresizingMaskIntoConstraints_(False)
    NSLayoutConstraint.activateConstraints_([
        header.topAnchor().constraintEqualToAnchor_constant_(
            container.topAnchor(), inset),
        header.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.trailingAnchor().constraintEqualToAnchor_constant_(
            header.trailingAnchor(), inset),
        body.topAnchor().constraintEqualToAnchor_constant_(
            header.bottomAnchor(), SPACING),
        body.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.trailingAnchor().constraintEqualToAnchor_constant_(
            body.trailingAnchor(), inset),
        footer.topAnchor().constraintEqualToAnchor_constant_(
            body.bottomAnchor(), SPACING + 2),
        footer.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.bottomAnchor().constraintEqualToAnchor_constant_(
            footer.bottomAnchor(), inset),
    ])


def pin(view: NSView, container: NSView, inset: float = MARGIN) -> None:
    """Pin `view` to fill `container` with a uniform inset (Auto Layout)."""
    container.addSubview_(view)
    view.setTranslatesAutoresizingMaskIntoConstraints_(False)
    NSLayoutConstraint.activateConstraints_([
        view.topAnchor().constraintEqualToAnchor_constant_(
            container.topAnchor(), inset),
        view.leadingAnchor().constraintEqualToAnchor_constant_(
            container.leadingAnchor(), inset),
        container.trailingAnchor().constraintEqualToAnchor_constant_(
            view.trailingAnchor(), inset),
        container.bottomAnchor().constraintGreaterThanOrEqualToAnchor_constant_(
            view.bottomAnchor(), inset),
    ])
