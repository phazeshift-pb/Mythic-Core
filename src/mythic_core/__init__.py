"""Shared building blocks for Mythic TTRPG tools (character manager, DM tools, ...).

* :mod:`mythic_core.characteristics` - characteristic codes and lookups
* :mod:`mythic_core.dice` - dice expressions such as ``4D10+12`` and rolling them
* :mod:`mythic_core.models` - shared Pydantic models (armor ratings, energy shields, ...)
* :mod:`mythic_core.rules` - pure rule functions (modifiers, wounds, initiative, ...)
* :mod:`mythic_core.data` - the bundled rules JSON and helpers to load it

Nothing here imports Qt, so every app (and its tests) can use it.
"""

__version__ = "0.1.0"
