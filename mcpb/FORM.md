# The desktop extension form, answered

The actual form is much shorter than the remote-server submission. Six fields.
Paste these. `SUBMISSION.md` still holds the long-form copy, which you will need
if you ever list the remote server at `api.misata.studio/mcp`.

---

### MCP Server Description (50 words max)

47 words.

```
Misata generates realistic multi-table test data from a description. You declare what must be true: exact totals, group shares, parent aggregates that reconcile with child rows, keys that never cross a tenant. The engine solves for rows satisfying every declaration, and an independent verifier proves it held.
```

### Desktop Extension GitHub Link

```
https://github.com/rasinmuhammed/misata
```

Public, and `mcpb/` is on the default branch with the manifest, the README, the
icon, the packer and the built bundle. A reviewer who opens the link can see
exactly what is inside the file they were sent.

### Primary Party Confirmation

**Yes.** You own Misata. The server does not proxy anyone else's API; it runs
your own open source software locally.

### .mcpb file

`mcpb/misata.mcpb` (211 KB). Rebuild any time with:

```bash
python mcpb/pack.py
```

It refuses to build a bundle the directory would reject: the manifest version
must match the installed package, the declared tools must match what the server
actually registers, and the icon must exist.

### Terms & Conditions

Yours to read and accept. I have not agreed to anything on your behalf.

### Feedback (optional)

Worth filling in. It costs nothing, it is read by the people who build the
format, and both of these came out of actually shipping this bundle rather than
from a wish list.

```
Two notes from packaging a Python server.

The manifest declares a runtime version but cannot declare the pip extras the
server needs. Ours lives behind `misata[mcp]`, so a plain `pip install misata`
produces a package whose entry point exists and then dies on ImportError the
moment it launches. Nothing in the bundle format expresses that dependency and
nothing checks it at install time, so the first person to discover it is the
user, looking at a traceback naming a package they never asked for. We only
caught it by installing our own published release into an empty virtualenv and
following our own README. A declared install command, or an install-time probe
that starts the server once and reports the exit, would catch a whole class of
this before it reaches anyone.

Second, the icon is one asset shown on both light and dark surfaces. A mark on
a transparent background has to choose which one it reads well against and lose
contrast on the other. Either a second slot for a dark-mode variant, or a
documented backdrop that icons are guaranteed to sit on, would settle it.
```
