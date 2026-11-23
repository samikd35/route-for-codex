# Local Markdown tracker

Route tracks work under `.scratch/`. Each feature has its own directory.

| Item | Location |
| --- | --- |
| Feature spec, when written | `.scratch/<feature>/spec.md` |
| Implementation ticket | `.scratch/<feature>/issues/<NN>-<slug>.md` |

To file a ticket, use the next number for that feature, starting at `01`. Give it a title, a `Status:` line using a [triage label](triage-labels.md), a `Blocked by:` line for ticket dependencies, and checkboxes for acceptance criteria. Append updates under `## Comments`.

To fetch or update a ticket, open its file. Refer to tickets by feature and number, such as `relay/01`. To list them from the project root, run `rg --files --hidden .scratch -g '**/issues/*.md' | sort`.
