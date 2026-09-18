# Rules for this repo

1. **Run the full QA Team AI agent review on a batched cadence, not per
   push.** Consult/use the dedicated QA Team AI agent to test accumulated
   changes together, roughly every 1-2 days (or before a deploy/release),
   rather than before every individual push. See SESSION-NOTES.md in
   SelfEat-main for which session is currently the QA Team. Between full
   QA cycles, every push still needs the cheap baseline check — boot the
   app against a local SQLite dev DB and smoke-test the changed
   endpoint(s) with curl. Don't push code that fails even that baseline
   check.
