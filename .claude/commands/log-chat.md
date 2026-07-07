# /log-chat — record a conversation outcome (N6)

**Input:** a contact name + what happened.

**Do:** update that Contact's row — `messaged_date`, `responded`, a tight `chat_notes`
summary, and a concrete `next_step`. If they offered something (an opening, an intro,
an async Q&A), capture it — referencing what a contact offered first is fair game later;
unsolicited asks are not.

The deterministic writer is `relay.flow.log_chat(name, responded=…, notes=…,
next_step=…, messaged_date=…)` (also the `relay log` CLI) — it resolves the name
against the Contacts tab, appends notes rather than overwriting, and fails loudly on
an unknown or ambiguous name. Use it instead of editing rows by hand.

Keep notes factual and short. Don't speculate about what wasn't said.
